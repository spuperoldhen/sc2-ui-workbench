# SC2 UI 工作台 · 本地 Agent 协作

## 和 Agent 一起编辑

1. 解压到本地目录。在这个目录打开 PowerShell，运行 `node .\agent.mjs start`。使用 Node.js 22 或更新版，并安装 Edge 或 Chrome。该命令打开一张可见的协作标签页。
2. 在标签页中打开原项目 JSON 或导入组件地图。打开或切换项目后，点击「恢复 Agent」。把解压目录交给本地 Agent，告诉它要做的布局。
3. Agent 分批添加或修改控件。你会在同一画布上看到改动，可以照常拖动、改属性或撤销。点击「暂停 Agent」可暂时自己编辑。选中控件后点击「指出问题」，留言会连同控件编号交给 Agent。
4. 回导前在协作栏点击「选择回导地图」，选取这次要写入的组件地图目录。Agent 完成后会提交定稿摘要。核对画布和目标路径后，打开「查看定稿」，点击「确认定稿并交给 Agent 回导」。

启动命令使用独立的浏览器配置保存协作草稿。第一次可从原工作台保存项目 JSON，再在协作标签页打开。已有浏览器集成也可以直接打开同目录 `index.html?agentCollab=1`，通过原有浏览器控制通道调用 `window.SC2WorkbenchCollaboration`。

## 给本地 Agent

在解压目录运行命令。Agent 控制用户正在看的标签页。每次提交后等画布刷新，再通过截图或项目状态检查效果。收到新留言、版本过期或用户暂停时，先读取最新状态并处理用户修改。审批由用户在工作台完成。

| 命令 | 用途 |
|---|---|
| `node agent.mjs get` | 返回当前项目、`session`、`revision`、选区、回导地图和留言 |
| `node agent.mjs status` | 读取同样的状态，省略完整项目 JSON |
| `node agent.mjs edit edit.json` | 验证一批改动，写入画布，形成一次可撤销操作 |
| `node agent.mjs review review.json` | 请求用户查看定稿，返回 `review.id` |
| `node agent.mjs publish 定稿ID 回导.zip [integration.json]` | 等待用户确认，导出回导包，按接入类型继续 |
| `node agent.mjs claim 定稿ID 回导.zip` | 核对定稿、文件和目标路径，开始本地接入 |
| `node agent.mjs report 定稿ID result.json` | 把接入或编译结果显示在工作台协作栏 |

如需指定浏览器，使用环境变量 `SC2_WORKBENCH_CHROME`，值为其可执行文件的完整路径。端口默认为本机 9226，可用 `SC2_WORKBENCH_PORT` 修改。现有测试副本的增量回导和接入前校验需 Python 3.9 或更新版。如命令名不是 `python`，可用 `SC2_WORKBENCH_PYTHON` 指定。

### 编辑 JSON 示例

将 `session`、`revision` 和 `dialogId` 换成 `get` 的当前值。一批可以包含多个操作。新增控件时返回其编号，可在下一批中引用它。也可以在请求里用 `focus` 指定要显示的对话框和控件，结构为 `{"dialogId":1,"controlId":0}`。

```json
{
  "session": "替换为当前会话编号",
  "revision": 1,
  "summary": "添加一个准备按钮",
  "operations": [
    {
      "op": "addControl",
      "dialogId": 1,
      "type": "button",
      "fields": {
        "name": "准备按钮",
        "text": "准备游戏",
        "anchor": "Bottom",
        "x": 0,
        "y": 100,
        "w": 250,
        "h": 56,
        "guiBindingEnabled": true,
        "binding": "gv_ReadyButton",
        "handoff": {
          "role": "当前玩家准备进入游戏",
          "event": "click",
          "scope": "triggeringPlayer",
          "notes": "玩家点击后接入地图已有的准备动作。"
        }
      }
    }
  ]
}
```

支持的操作

- `addDialog` 可省略 `layout` 以添加空白对话框，或传入工作台版本 3 的完整布局。
- `updateDialog` 使用 `dialogId` 和 `fields`，可选 `prefix`。
- `addControl` 使用 `dialogId`、`type` 和 `fields`。
- `updateControl` 使用 `dialogId`、`controlId` 和 `fields`。字段参考 `get` 返回的项目。绑定新控件时填入确切的标识符。
- `removeControl` 使用 `dialogId` 和 `controlId`。同一批需先删除或迁移依赖该控件的子控件和附着关系。
- `addImages` 使用 `images` 数组。每项包含 `path`、`format` 和 Base64 `data`，路径形如 `Assets\\Textures\\SC2WorkbenchImports\\agent_card.dds`。
- `setFontStyles` 使用 `xml` 提交完整字体样式文件。保留项目已有样式条目。
- 给按钮配置正式的事件、条件与动作时，先用工作台的控件行为面板保存一项，再从 `get` 读取该控件的 `handoff.behavior` 格式。

### 定稿和回导

`review.json` 填写当前 `session`、`revision`、用户选定组件地图的完整本机路径 `target` 和定稿摘要 `summary`。如果本次涉及修改地图触发器，设置 `requiresIntegration: true`。用摘要说明发生哪些布局或玩法改动，准备把脚本接到哪里。收到用户留言或新的项目改动后，旧定稿失效，Agent 重新读取当前项目再提交。

`publish` 等待用户确认后保存 ZIP。对于已连接工作台脚本、初始化和 GUI 绑定都相符的 `-UI-Test` 副本，它校验目标哈希，备份旧文件并写入增量文件。输出会回到协作栏。

首次接入、需要新建 GUI 变量、动作或事件变更时，结果为 `agentIntegration`。本地 Agent 可以通过以下任一方式接续：

- **使用本地 Agent 的地图编辑能力。** `publish` 返回后先运行 `claim`。读取包内 `ui_manifest.json`、初始化动作、全局变量和触发器交接。根据现有地图结构接入，复用同名兼容变量和实际初始化位置，处理素材登记，打开编辑器编译地图副本，再用 `report` 返回结果。结果 JSON 包含 `ok` 布尔值和 `message` 文本。
- **挂接已经可运行的地图接入命令。** 给 `publish` 传入本地 `integration.json`。它包含 `command` 可执行文件路径和 `args` 字符串数组。工具核对定稿、目标及文件哈希后调用该命令，在原有参数后追加回导 ZIP 路径和目标地图路径。接入命令成功退出后，其输出会显示在协作栏。此包提供上面提到的增量写入工具和接入入口。首次接入所用的本地地图编辑及编译命令由实际地图工程提供。

例如，如果本地已有处理该地图的脚本，可以把 `command` 设置为 `python`，把脚本的绝对路径作为 `args` 第一项。脚本读取追加的两个参数，按地图实际触发器结构接入和编译。选择已有脚本时，先确认它能接收这两个参数。

协作标签页中的确认用于约束这条工作台流程。Agent 操作本机浏览器和文件的权限由本机环境决定。部署进入「Agent 正在接入地图」后，暂停用于停止后续画布任务，地图编辑命令的中止由执行该命令的本地 Agent 处理。
