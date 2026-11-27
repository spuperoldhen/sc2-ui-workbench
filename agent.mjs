import {execFileSync,spawn} from "node:child_process";
import {existsSync} from "node:fs";
import {access,open,readFile,mkdir,unlink} from "node:fs/promises";
import {homedir} from "node:os";
import {dirname,join,resolve} from "node:path";
import {pathToFileURL,fileURLToPath} from "node:url";

const directory = dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.SC2_WORKBENCH_PORT || 9226);
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error("调试端口无效。");
const json = async (path)=>JSON.parse((await readFile(path,"utf8")).replace(/^\ufeff/,""));
const print = (value)=>console.log(JSON.stringify(value,null,2));

async function launch() {
  const candidates = [process.env.SC2_WORKBENCH_CHROME,
    ...[process.env["ProgramFiles(x86)"],process.env.ProgramFiles,process.env.LOCALAPPDATA].filter(Boolean)
      .flatMap((base)=>[join(base,"Microsoft","Edge","Application","msedge.exe"),join(base,"Google","Chrome","Application","chrome.exe")])
  ].filter(Boolean);
  let browser;
  for (const candidate of candidates) {
    try { await access(candidate); browser = candidate; break; } catch { /* Try the next installed browser. */ }
  }
  if (!browser) throw new Error("找不到 Edge 或 Chrome。请在 SC2_WORKBENCH_CHROME 指定浏览器的完整路径。");
  const profile = join(process.env.LOCALAPPDATA || homedir(),"SC2WorkbenchCollaboration",String(port));
  await mkdir(profile,{recursive:true});
  const url = pathToFileURL(join(directory,"index.html"));
  url.searchParams.set("agentCollab","1");
  const child = spawn(browser,[
    "--remote-debugging-address=127.0.0.1","--remote-debugging-port="+port,
    "--user-data-dir="+profile,"--no-first-run",url.href
  ],{detached:true,stdio:"ignore"});
  await new Promise((ready,fail)=>{ child.once("spawn",ready); child.once("error",fail); });
  child.unref();
  console.log("已启动 Agent 协作工作台。");
}

async function connect() {
  const response = await fetch("http://127.0.0.1:"+port+"/json/list",{signal:AbortSignal.timeout(5000)});
  if (!response.ok) throw new Error("无法读取工作台标签页。");
  const expected = pathToFileURL(join(directory,"index.html"));
  const tabs = (await response.json()).filter((tab)=>{
    if (tab.type!=="page") return false;
    const url = new URL(tab.url);
    return url.protocol===expected.protocol && url.pathname===expected.pathname &&
      url.searchParams.get("agentCollab")==="1" &&
      (!process.env.SC2_WORKBENCH_TAB_ID || tab.id===process.env.SC2_WORKBENCH_TAB_ID);
  });
  if (tabs.length!==1) throw new Error("请只打开一个此目录的 Agent 协作标签页。");
  const endpoint = new URL(tabs[0].webSocketDebuggerUrl);
  if (endpoint.protocol!=="ws:" || !["127.0.0.1","localhost"].includes(endpoint.hostname) || Number(endpoint.port)!==port) {
    throw new Error("工作台的本机调试地址不匹配。");
  }
  const socket = new WebSocket(endpoint);
  let nextId = 1;
  const pending = new Map();
  socket.addEventListener("message",(event)=>{
    const reply = JSON.parse(event.data);
    const callback = pending.get(reply.id);
    if (!callback) return;
    pending.delete(reply.id);
    if (reply.error) callback.reject(new Error(reply.error.message));
    else if (reply.result?.exceptionDetails) {
      const {exception,text} = reply.result.exceptionDetails;
      callback.reject(new Error(exception?.description || text));
    } else callback.resolve(reply.result);
  });
  socket.addEventListener("close",()=>{
    for (const {reject} of pending.values()) reject(new Error("工作台连接已关闭。"));
    pending.clear();
  });
  await new Promise((ready,fail)=>{
    const timeout = setTimeout(()=>{ socket.close(); fail(new Error("连接工作台超时。")); },5000);
    socket.addEventListener("open",()=>{clearTimeout(timeout);ready();},{once:true});
    socket.addEventListener("error",()=>{clearTimeout(timeout);fail(new Error("无法连接工作台。"));},{once:true});
  });
  function send(method,params) {
    return new Promise((resolve,reject)=>{
      const id = nextId++;
      pending.set(id,{resolve,reject});
      socket.send(JSON.stringify({id,method,params}));
    });
  }
  async function evaluate(method,args=[],returnByValue=true) {
    const expression = "window.SC2WorkbenchCollaboration["+JSON.stringify(method)+"](..."+JSON.stringify(args)+")";
    const {result} = await send("Runtime.evaluate",{expression,awaitPromise:true,returnByValue});
    return returnByValue ? result.value : result.objectId;
  }
  return {send,evaluate,close:()=>socket.close()};
}

async function saveApproved(api,id,path) {
  const output = resolve(path);
  const stream = await open(output,"wx");
  let objectId, complete = false;
  try {
    objectId = await api.evaluate("exportApproved",[id],false);
    const call = async (functionDeclaration,args=[])=>{
      const {result} = await api.send("Runtime.callFunctionOn",{
        functionDeclaration,objectId,arguments:args.map((value)=>({value})),awaitPromise:true,returnByValue:true
      });
      return result.value;
    };
    const metadata = await call("function(){return {size:this.archive.size,target:this.target,kind:this.kind,diagnostics:this.diagnostics};}");
    for (let offset=0;offset<metadata.size;offset+=65536) {
      const data = await call(`async function(offset){
        const buffer=await this.archive.slice(offset,offset+65536).arrayBuffer();
        const bytes=new Uint8Array(buffer);
        let value="";
        for(const byte of bytes)value+=String.fromCharCode(byte);
        return btoa(value);
      }`,[offset]);
      await stream.writeFile(Buffer.from(data,"base64"));
    }
    complete = true;
    return {...metadata,archive:output};
  } finally {
    await stream.close();
    if (!complete) await unlink(output).catch(()=>{});
    if (objectId) await api.send("Runtime.releaseObject",{objectId}).catch(()=>{});
  }
}

async function waitApproved(api,id) {
  while (true) {
    const state = await api.evaluate("getState",[false]);
    if (state.paused || state.review?.id!==id) throw new Error("定稿请求已撤销或画布已改变。");
    if (["approved","exported"].includes(state.review.status)) return;
    if (state.review.status!=="pending") throw new Error("此定稿已由其他操作处理。");
    await new Promise((done)=>setTimeout(done,1000));
  }
}

function pythonExecutable() {
  if (process.env.SC2_WORKBENCH_PYTHON) return process.env.SC2_WORKBENCH_PYTHON;
  const bases=[process.env.LOCALAPPDATA,process.env.ProgramFiles,process.env["ProgramFiles(x86)"]].filter(Boolean);
  for (const base of bases) for (const version of ["313","312","311","310"]) {
    const candidate=join(base,"Programs","Python","Python"+version,"python.exe");
    if (existsSync(candidate)) return candidate;
  }
  return "python";
}

function verifyArchive(id,path,target,apply=false) {
  return execFileSync(pythonExecutable(),[
    join(directory,"apply_ui_revision.py"),path,target,"--review-id",id,...(apply ? ["--apply"] : [])
  ],{encoding:"utf8",env:{...process.env,PYTHONUTF8:"1"}}).trim();
}

async function run() {
  const [command,...args] = process.argv.slice(2);
  if (command==="start" && !args.length) return launch();
  const arity = {get:[0],status:[0],edit:[1],review:[1],export:[2],publish:[2,3],claim:[2],report:[2]};
  if (!Object.hasOwn(arity,command) || !arity[command].includes(args.length)) {
    throw new Error("用法：agent.mjs start | get | status | edit 编辑.json | review 定稿.json | export 定稿ID 回导.zip | publish 定稿ID 回导.zip [接入配置.json] | claim 定稿ID 回导.zip | report 定稿ID 结果.json");
  }
  const api = await connect();
  try {
    if (command==="get") return print(await api.evaluate("getState"));
    if (command==="status") return print(await api.evaluate("getState",[false]));
    if (command==="edit") return print(await api.evaluate("edit",[await json(args[0])]));
    if (command==="review") return print(await api.evaluate("requestReview",[await json(args[0])]));
    if (command==="claim") {
      const [id,archive] = args;
      const {review} = await api.evaluate("getState",[false]);
      if (review?.id!==id || review.status!=="exported") throw new Error("此定稿尚未导出，或已失效。");
      verifyArchive(id,resolve(archive),review.target);
      return print(await api.evaluate("claimApply",[id]));
    }
    if (command==="report") return print(await api.evaluate("reportApply",[args[0],await json(args[1])]));
    const [id,path,adapterPath] = args;
    const adapter = adapterPath ? await json(adapterPath) : null;
    if (adapter && (typeof adapter.command!=="string" || !adapter.command ||
        !Array.isArray(adapter.args) || adapter.args.some((arg)=>typeof arg!=="string"))) {
      throw new Error("接入配置需要 command 字符串和 args 字符串数组。");
    }
    if (command==="publish") await waitApproved(api,id);
    const result = await saveApproved(api,id,path);
    if (command==="export" || (result.kind==="agentIntegration" && !adapter)) return print(result);
    verifyArchive(id,result.archive,result.target);
    const approval = await api.evaluate("claimApply",[id]);
    let message;
    try {
      if (approval.kind==="existingIntegration") {
        message = verifyArchive(id,result.archive,approval.target,true);
      } else {
        message = execFileSync(adapter.command,[...adapter.args,result.archive,approval.target],{encoding:"utf8"}).trim();
      }
    } catch (error) {
      await api.evaluate("reportApply",[id,{ok:false,message:(error.stderr || error.message).trim()}]);
      throw error;
    }
    await api.evaluate("reportApply",[id,{ok:true,message}]);
    print({...result,result:message});
  } finally {
    api.close();
  }
}

run().catch((error)=>{console.error(error.message);process.exitCode=1;});
