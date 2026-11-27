# SC2 UI 工作台 · 本地 Agent 协作

## 和 Agent 一起编辑

用户不需要打开 PowerShell。把解压目录交给本地 Agent，在对话里说「打开工作台协作」或直接描述要改的布局即可。Agent 会在本机运行命令、打开协作页并读取项目。Agent 应优先读取 `skills/sc2-workbench-collab/SKILL.md` 的工作流。

1. Agent 启动协作页并打开项目。使用 Node.js 22 或更新版，并安装 Edge 或 Chrome。协作页是一张可见的标签页。
2. 打开或切换项目后，点击「恢复 Agent」（如果显示「暂停 Agent」说明已经启用）。用户只需要在浏览器里完成项目/地图目录选择和最终定稿确认。
3. Agent 分批添加或修改控件。你会在同一画布上看到改动，可以照常拖动、改属性或撤销。点击「暂停 Agent」可暂时自己编辑。选中控件后点击「指出问题」，留言会连同控件编号交给 Agent。
4. 回导前在协作栏点击「选择回导地图」，选取这次要写入的组件地图目录。Agent 完成后会提交定稿摘要。核对画布和目标路径后，打开「查看定稿」，点击「确认定稿并交给 Agent 回导」。

`agent.mjs start` 会启动本地工作台助手，并用 `127.0.0.1` 协作页代替 `file://`。项目文件、标注、收藏和素材目录保存在工作台目录的 `data/` 中，普通启动器和协作页共用；更换浏览器后不需要重新授权素材目录。

本版 EXE 已包含更新后的助手。从旧版升级时，请先关闭原启动器打开的所有工作台标签页，待旧助手退出，再由 Agent 使用 `agent.mjs start` 启动。多个浏览器同时编辑标注和收藏时，由更新后的 `tools/local_store.py` 在本机合并。

第一次使用可以从原工作台保存项目 JSON，再让 Agent 用 `open` 打开，或在协作页导入。已有浏览器集成也可以直接打开同目录 `index.html?agentCollab=1`，通过原有浏览器控制通道调用 `window.SC2WorkbenchCollaboration`。

## 给本地 Agent

在解压目录运行命令。Agent 控制用户正在看的标签页。每次提交后等画布刷新，再通过截图或项目状态检查效果。收到新留言、版本过期或用户暂停时，先读取最新状态并处理用户修改。审批由用户在工作台完成。

| 命令 | 用途 |
|---|---|
| `node agent.mjs get` | 返回当前项目、`session`、`revision`、选区、回导地图和留言 |
| `node agent.mjs status` | 读取同样的状态，省略完整项目 JSON |
| `node agent.mjs open 项目.json` | Agent 直接打开项目 JSON，并开始新的协作会话版本 |
| `node agent.mjs edit edit.json` | 验证一批改动，写入画布，形成一次可撤销操作 |
| `node agent.mjs review review.json` | 请求用户查看定稿，返回 `review.id` |
| `node agent.mjs publish 定稿ID 回导.zip [integration.json]` | 等待用户确认，导出回导包，按接入类型继续 |
| `node agent.mjs claim 定稿ID 回导.zip` | 仅对 `agentIntegration` 核对定稿、文件和目标路径，开始本地接入；`existingIntegration` 已由 `publish` 自动处理 |
| `node agent.mjs report 定稿ID result.json` | 把接入或编译结果显示在工作台协作栏 |

如需指定浏览器，使用环境变量 `SC2_WORKBENCH_CHROME`，值为其可执行文件的完整路径。协作调试端口默认为本机 9226，可用 `SC2_WORKBENCH_PORT` 修改；工作台页面端口默认为 8765，可用 `SC2_WORKBENCH_HELPER_PORT` 修改。现有测试副本的增量回导和接入前校验需 Python 3.9 或更新版。如命令名不是 `python`，可用 `SC2_WORKBENCH_PYTHON` 指定。

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

如果定稿包的 `files` 已列出 `triggerData`，随包的 `stage.py` 会核对原文件哈希，把生成的 `Triggers` 和译文写到已确认的地图副本，并保留备份。接着连接初始化动作并编译地图。包内包含数组初始值时，在创建界面前执行对应的初始化动作。

- **使用本地 Agent 的地图编辑能力。** 仅当 `publish` 返回 `agentIntegration`（且没有传入适配器）时，运行 `claim`；`existingIntegration` 已由 `publish` 自动领取并写入，不要再执行 `claim`。读取包内 `ui_manifest.json`、初始化动作、全局变量和触发器交接。根据现有地图结构接入，复用同名兼容变量和实际初始化位置，处理素材登记，打开编辑器编译地图副本，再用 `report` 返回结果。结果 JSON 包含 `ok` 布尔值和 `message` 文本。
- **挂接已经可运行的地图接入命令。** 给 `publish` 传入本地 `integration.json`。它包含 `command` 可执行文件路径和 `args` 字符串数组。工具核对定稿、目标及文件哈希后调用该命令，在原有参数后追加回导 ZIP 路径和目标地图路径。接入命令成功退出后，其输出会显示在协作栏。此包提供上面提到的增量写入工具和接入入口。首次接入所用的本地地图编辑及编译命令由实际地图工程提供。

例如，如果本地已有处理该地图的脚本，可以把 `command` 设置为 `python`，把脚本的绝对路径作为 `args` 第一项。脚本读取追加的两个参数，按地图实际触发器结构接入和编译。选择已有脚本时，先确认它能接收这两个参数。

协作标签页中的确认用于约束这条工作台流程。Agent 操作本机浏览器和文件的权限由本机环境决定。部署进入「Agent 正在接入地图」后，暂停用于停止后续画布任务，地图编辑命令的中止由执行该命令的本地 Agent 处理。

## 贴图库分类、标签和收藏

在「贴图库」选择素材，展开右侧「编辑分类和标签」。可修正显示名、用途、种族、形态，并输入用顿号或逗号分隔的标签。顶部「所有标注」可切换到「未打标」「我的标注」「Agent 标注」。用途无法确认时可选「用途待核对」。

右侧「收藏」可一键增减，左上「收藏」显示已收藏素材。勾选顶部「Agent 优先用收藏」后，Agent 的搜索会先返回满足当前关键词和用途的收藏。若想限定本次只用收藏，在给 Agent 的指令里说明。

分类、标签、收藏和优先选项保存在同一浏览器配置中，可跨项目使用。升级时把本包解压到原工作台目录并打开同一个浏览器配置。再次连接同一授权目录会恢复标注。使用临时目录上传时，浏览器无法记住目录授权，重开工作台后需再次选择同一份素材。素材文件仍以只读方式打开。

### Agent 素材命令

| 命令 | 用途 |
|---|---|
| `node agent.mjs asset-find [筛选.json]` | 查找用于搭建 UI 的素材。可按用途、关键词、标注状态和收藏筛选 |
| `node agent.mjs asset-preview 素材.json 预览.png` | 用 `{"id":"从搜索结果复制"}` 保存一张检查用缩略图 |
| `node agent.mjs asset-tag 标注.json` | 批量保存 Agent 对已授权目录素材的分类和标签，每次最多 200 项 |

**搭建 UI 时**，先按用途或关键词调用 `asset-find`，保持用户的收藏设置。明确要求只用收藏时，传 `"favorites":"only"`。没有符合用途的收藏，默认搜索会返回其他符合条件的素材。返回值里的 `path` 是可写入控件的 Galaxy 路径。若 `thumbnailOnly` 为真，回导前应核对游戏依赖或连接实际 DDS。

查找边框或面板的示例

```json
{"kind":"frame","query":"金边","limit":40}
```

**整理贴图库时**，先用 `asset-find` 读取 `{"annotation":"unmarked","annotatable":true,"limit":40}`，根据 `nextOffset` 分页浏览。若一边打标一边读取「未打标」，每批重新从第一页读取，已打标的条目会从该筛选退出。对用途拿不准的素材用 `asset-preview` 看图，仍不确定时用 `"kind":"unknown"`。搜索结果的 `library` 显示来源，`materials` 是素材目录，`icons` 是图标浏览器目录。

使用搜索原样返回的 `id` 保存一批标注

```json
{
  "items": [
    {"id":"从搜索结果复制","fields":{"kind":"frame","tags":["深色","金边","计分板"],"label":"深色金边计分板底框"}}
  ]
}
```

只传需要修改的字段。用途可填 `frame`、`button`、`btn_unit`、`btn_ability`、`portrait`、`bar` 等；种族可填 `terran`、`protoss`、`zerg`、`neutral`；形态可填「单帧」「双态图集」「三态图集」「四态图集」。手动保存过的字段会优先保留，Agent 会在结果中用 `skipped` 报告跳过的字段数。用户可以点「恢复原始分类」清除该素材的标注。
