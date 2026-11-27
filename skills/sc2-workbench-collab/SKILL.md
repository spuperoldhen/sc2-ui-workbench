---
name: sc2-workbench-collab
description: Operate the SC2 UI Workbench on this Windows machine through its local Agent collaboration page. Use when the user asks to edit a StarCraft II UI dialog, add or change controls, run a design review, tag or classify textures, manage favorites, or work with the SC2 UI workbench together with an Agent. The Agent starts the collaboration page, edits the shared canvas, and asks the user only for browser approvals. Do not ask the user to open PowerShell or type Node commands.
---

# SC2 UI 工作台协作

用户只需要在对话里描述要改什么，并在必要的时候点浏览器里的确认。启动、读取、编辑、导出和贴图标注都由 Agent 在本机执行。

## 1. 找到工作台目录

优先使用当前工作区：

```text
E:\Ai\sc2-ui-workbench
```

该目录应同时包含 `index.html`、`agent.mjs` 和 `apply_ui_revision.py`。如果用户使用的是解压后的发布目录，以用户给出的目录为准。

不要要求用户打开 PowerShell。Agent 使用 shell 工具在该目录执行命令。

## 2. 启动或复用协作页

先检查当前是否已有协作页：

```powershell
node agent.mjs status
```

- 成功返回 `session`：直接复用，不要重复启动。
- 连接失败：启动协作页：

```powershell
node agent.mjs start
```

`start` 发现已有协作页时会直接复用，不会重复开标签。需要关闭或重开时用 `node agent.mjs stop` / `node agent.mjs restart`。回导地图按项目记住，刷新、重开或助手重启后会自动恢复；不要因此让用户重新选择同一张地图。

项目、贴图标注、收藏、项目标记和素材目录路径保存在工作台目录的 `data/` 中。普通启动器和协作页共用这份数据；不要用另一个浏览器重新授权素材目录，也不要删除 `data/`。

如果端口 9226 被占用：
- 先复用已有协作标签页；
- 不要打开多个同目录协作页；
- 必要时用环境变量 `SC2_WORKBENCH_PORT` 指定另一个端口。

## 3. 打开项目

用户给出项目 JSON 路径时，直接由 Agent 打开：

```powershell
node agent.mjs open "C:\path\to\project.sc2ui.json"
```

这会载入项目、保存协作草稿并开始新的会话版本。不要在用户没有指定项目时猜测文件。

如果用户要导入组件地图，浏览器目录选择必须由用户完成。只用一句自然语言说明：

> 我在协作页打开了空白工作台，请在「项目 → 导入 SC2Components」里选一次地图目录；之后我来操作。

不要把这写成终端步骤。

## 4. 读取当前状态

```powershell
node agent.mjs get
```

返回内容包含：

- `session`、`revision`
- 当前对话框和选区
- 回导地图
- 用户留言
- 完整项目 JSON

日常检查用：

```powershell
node agent.mjs status
```

每次编辑前重新读取；不要使用过期 `session` 或 `revision`。

## 5. 编辑画布

把操作写到一个临时 JSON，再提交。示例：给当前对话框加按钮：

```json
{
  "session": "从 get 复制",
  "revision": 1,
  "summary": "添加准备按钮",
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
        "h": 56
      }
    }
  ]
}
```

```powershell
node agent.mjs edit "C:\path\to\edit.json"
```

支持 `addDialog`、`updateDialog`、`addControl`、`updateControl`、`removeControl`、`addImages`、`setFontStyles`。一次 1–500 个操作。

提交后：

- 读取 `status` 确认 `revision` 增加；
- 需要看画面时使用可用的浏览器/截图工具；
- 用户正在拖动、输入、打开对话框或暂停时，`edit` 会拒绝；等用户操作结束再读取。

## 6. 用户参与

- 用户说「暂停」：不要继续提交编辑，先 `status` 等 `paused:false`。
- 用户点「指出问题」：从 `get` 的 `feedback` 读取控件编号和留言，重新读取项目后处理。
- 用户手动改了画布：旧 `revision` 会失效；重新 `get`，不要复用旧请求。
- 绝不替用户点「确认定稿」或绕过审批。

## 7. 定稿与回导

1. 用户在协作栏「选择回导地图」，选一次目标组件目录。
2. 向用户确认目标路径后提交定稿：

```json
{
  "session": "从 get 复制",
  "revision": 2,
  "target": "C:\\path\\to\\Map-UI-Test.SC2Components",
  "summary": "本次改动和接入说明",
  "requiresIntegration": false
}
```

```powershell
node agent.mjs review "C:\path\to\review.json"
```

3. 告诉用户只做一次浏览器操作：

> 定稿已提交。请在协作页点「查看定稿」，核对后点「确认定稿并交给 Agent 回导」。

4. 用户确认后：

```powershell
node agent.mjs publish "定稿ID" "C:\path\to\return.zip"
```

- 返回 `existingIntegration`：`publish` 已自动领取并写入，不要再次 `claim`；失败时读取结果并在工作台重新定稿。
- 返回 `agentIntegration`：需要读取包内的 `ui_manifest.json`、初始化和 GUI 变量说明，按实际地图接入触发器；完成后用 `report` 回报。
- 目标必须是 `-UI-Test` 副本；不要写正式地图。

## 8. 贴图库标注与收藏

只有用户已连接的授权目录素材可以写入标注。用户选择目录这一步由用户在贴图库里完成一次；之后 Agent 操作。

查找素材：

```powershell
node agent.mjs asset-find "C:\path\to\filter.json"
```

```json
{"kind":"frame","query":"金边","limit":40}
```

- `annotation`：`unmarked` / `manual` / `agent`
- `annotatable:true`：只返回已授权、可标注的目录素材
- `favorites:"only"`：只返回收藏
- 默认按用户是否勾选「Agent 优先用收藏」决定 `prefer` 或 `any`

查看缩略图：

```powershell
node agent.mjs asset-preview "C:\path\to\asset.json" "C:\path\to\preview.png"
```

批量标注（每次最多 200 项，只传要改的字段）：

```json
{
  "items": [
    {
      "id": "从 asset-find 复制",
      "fields": {
        "kind": "frame",
        "race": "terran",
        "shape": "单帧",
        "label": "深色金边计分板底框",
        "tags": ["深色", "金边", "计分板"]
      }
    }
  ]
}
```

```powershell
node agent.mjs asset-tag "C:\path\to\tags.json"
```

规则：

- 用户手动保存过的字段优先；Agent 的同名字段会被跳过，返回 `skipped`。
- 不要清除用户的收藏或手动标注。
- 不确定用途时用 `"kind":"unknown"`。
- 素材文件只读；不要修改 DDS。
- `thumbnailOnly:true` 表示预览来自图标浏览器缩略图，回导前要核对实际 DDS 或游戏依赖。

## 9. 用户可见的表达

不要向用户展示 PowerShell 命令、JSON、CDP、端口或内部字段。用自然语言汇报：

- 「已打开协作页」
- 「已加上准备按钮，画布上应该已经出现」
- 「请点一下协作页里的确认定稿」
- 「已生成回导包，正在写入测试副本」

只有两种浏览器动作值得让用户做：

1. 首次选项目、地图或素材目录；
2. 查看并确认定稿。

## 10. 参考

- `Agent协作说明.md`：完整命令和示例。
- `README.md`：工作台功能、实机预览和贴图库说明。
- `docs/live-preview-baseline.md`：实机预览契约。

如果 Node 缺失、浏览器找不到或协作页无法打开，只说明这一项环境问题并给出一次性的安装/配置办法；不要把整段终端流程推给用户。
