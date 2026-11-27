# SC2 UI 工作台 · 本地 Agent 协作

## 和 Agent 一起编辑

用户不需要打开 PowerShell。把解压目录交给本地 Agent，在对话里说「打开工作台协作」或直接描述要改的布局即可。Agent 会在本机运行命令、打开协作页并读取项目。Agent 应优先读取 `skills/sc2-workbench-collab/SKILL.md` 的工作流。普通工作台顶部的「Agent 协作」按钮和首次启动引导也提供同一段可直接复制给 Agent 的话；首次打开 EXE 时会自动弹出。

1. Agent 启动协作页并打开项目。使用 Node.js 22 或更新版，并安装 Edge 或 Chrome。协作页是一张可见的标签页。
2. 打开或切换项目后，点击「恢复 Agent」（如果显示「暂停 Agent」说明已经启用）。用户只需要在浏览器里完成项目/地图目录选择和最终定稿确认。
3. Agent 分批添加或修改控件。你会在同一画布上看到改动，可以照常拖动、改属性或撤销。点击「暂停 Agent」可暂时自己编辑。选中控件后点击「指出问题」，留言会连同控件编号交给 Agent。
4. 回导前在协作栏点击「选择回导地图」，选取名称以 `-UI-Test.SC2Map` 或 `-UI-Test.SC2Components` 结尾的组件目录。定稿和导出会自动复扫；Agent 在磁盘更新目标文件后也可以点「重新扫描目标目录」。Agent 完成后会提交定稿摘要。核对画布和目标路径后，打开「查看定稿」，点击「确认定稿并交给 Agent 回导」。

`agent.mjs start` 会启动本地工作台助手，并用 `127.0.0.1` 协作页代替 `file://`。项目文件、标注、收藏和素材目录保存在工作台目录的 `data/` 中，普通启动器和协作页共用。升级后关闭旧工作台标签页，再用 `node agent.mjs start` 启动更新后的本地助手。浏览器独立使用时，支持目录句柄的浏览器同样可以复扫。只支持传统目录上传的浏览器需要重新选取目录，再确认定稿。

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
| `node agent.mjs map-refresh` | 立即复扫已授权目标，沿用同一目录的布局定稿 |
| `node agent.mjs stage-assets 定稿ID 回导.zip` | 领取首次接入定稿，校验并部署清单中的文件，保留玩法接入任务 |
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
- `updateDialog` 使用 `dialogId` 和 `fields`，可选 `prefix` 和 `previewStates`。
- `setExportOptions` 的 `fields` 可设置 `scriptPath`（须为 `Scripts/SC2Workbench*.galaxy`）、`scriptMode`（`perDialog` 按对话框拆分，省略或清空则合并）和 `pruneUnusedFontStyles`（布尔值）。相同选项也可在「回导地图 → 回导设置」修改。
- `addControl` 使用 `dialogId`、`type` 和 `fields`。
- `updateControl` 使用 `dialogId`、`controlId` 和 `fields`。字段参考 `get` 返回的项目。绑定新控件时填入确切的标识符。
- `removeControl` 使用 `dialogId` 和 `controlId`。同一批需先删除或迁移依赖该控件的子控件和附着关系。
- `addImages` 使用 `images` 数组。每项包含 `path`、`format` 和 Base64 `data`，路径形如 `Assets\\Textures\\SC2WorkbenchImports\\agent_card.dds`。
- `setFontStyles` 使用 `xml` 提交完整字体样式文件。保留项目已有样式条目。
- 给按钮配置正式的事件、条件与动作时，先用工作台的控件行为面板保存一项，再从 `get` 读取该控件的 `handoff.behavior` 格式。

### 多状态预览

通过 `updateDialog` 的 `previewStates` 提交多套样例。以下示例会切换 12 号标签、13 号立绘和 20 号锁定标记。对话框本身用 `controlId: 0`。控件还支持 `opacity`（0–100）及色调 `tint`。在画布「预览」或「实机预览」选择样例，正式包使用项目保存的初始属性。

```json
{
  "op": "updateDialog",
  "dialogId": 1,
  "fields": {},
  "previewStates": [
    {
      "id": "raynorLocked",
      "name": "雷诺 · 已锁定",
      "controls": [
        {"controlId": 12, "text": "吉姆·雷诺", "color": "#e4ba70"},
        {"controlId": 13, "path": "Assets\\Textures\\ui_loading_coop_hero_raynor.dds"},
        {"controlId": 20, "visible": true}
      ]
    }
  ]
}
```

### 定稿和回导

`review.json` 填写当前 `session`、`revision`、定稿摘要 `summary`。本地助手授权的目标已提供 `targetPath`，可省略 `target`。浏览器直接授权时，填写组件目录的完整本机路径 `target`。如果本次涉及修改地图触发器，设置 `requiresIntegration: true`。用摘要说明发生哪些布局或玩法改动，准备把脚本接到哪里。收到留言、切换目标或改变布局后，Agent 重新读取当前项目再提交定稿。同一目录复扫保留定稿；仅脚本或绑定变化时，用户可在原定稿中确认更新。

`publish` 等待用户确认后保存 ZIP。对于已连接工作台脚本、初始化和 GUI 绑定都相符的 `-UI-Test` 副本，它校验目标哈希，备份旧文件并写入增量文件。输出会回到协作栏。

首次接入、需要新建 GUI 变量、动作或事件变更时，结果为 `agentIntegration`。先关闭编辑器中的测试副本，再通过以下任一方式接续。

- **先部署已审核文件。** 运行 `stage-assets`，部署清单中的贴图、字体、UI 脚本、本地化和变量同步后的 `Triggers`，并为旧文件保留备份。它已领取定稿。接下来在银河编辑器接入实际事件和动作并编译，再用 `report` 回报。也可直接运行 `python apply_ui_revision.py 回导.zip 目标目录 --review-id 定稿ID --stage-assets` 执行文件部署。

- **使用本地 Agent 的地图编辑能力。** 仅当 `publish` 返回 `agentIntegration`（且没有传入适配器）时，运行 `claim`；`existingIntegration` 已由 `publish` 自动领取并写入，不要再执行 `claim`。读取包内 `ui_manifest.json`、初始化动作、全局变量和触发器交接。根据现有地图结构接入，复用同名兼容变量和实际初始化位置，处理素材登记，打开编辑器编译地图副本，再用 `report` 返回结果。结果 JSON 包含 `ok` 布尔值和 `message` 文本。
- **挂接已经可运行的地图接入命令。** 给 `publish` 传入本地 `integration.json`。它包含 `command` 可执行文件路径和 `args` 字符串数组。工具核对定稿、目标及文件哈希后调用该命令，在原有参数后追加回导 ZIP 路径和目标地图路径。接入命令成功退出后，其输出会显示在协作栏。此包提供上面提到的增量写入工具和接入入口。首次接入所用的本地地图编辑及编译命令由实际地图工程提供。

项目默认输出 `Scripts/SC2Workbench_<前缀>.galaxy`，已存在且绑定同一组创建函数的工作台模块会沿用原路径。接入时以 `integration.scripts`、`integration.include` 为准；普通回导包的预检工具位于 `skills/sc2-galaxy-bridge/scripts/stage.py`。协作定稿包用 `apply_ui_revision.py` 核对目标哈希并部署。

较长的首次初始化会生成一行调用和「初始化接线.galaxy.txt」。辅助函数需在地图全局变量和 UI 模块声明之后可见。如果编辑器无法保证声明顺序，在原初始化位置使用「完整GUI初始化动作.txt」。接入前检查清单中的贴图实际尺寸、预期尺寸和来源。用「素材目录」连接含原始 DDS 的提取目录，可以自动回填图标浏览器的缩略图。清单的 `cleanupCandidates` 来自项目布局基线，删除前应查其他界面及触发器的引用。

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
