# Windows 银河编辑器接入

## 导出和暂存

本地需要 Node.js 20+、Python 3.10+ 和 Playwright。把 Playwright 装在专用工具目录，从该目录运行命令。使用现有 Edge 时，可用 `--browser msedge`，否则先运行 `npx playwright install chromium`。

```powershell
npm install playwright
$skill = 'D:\tools\sc2-galaxy-bridge'
node "$skill\scripts\export.mjs" --workbench '.\index.html' --project '.\project.json' --out '.\run-01' --browser msedge
py -3 "$skill\scripts\stage.py" --bundle '.\run-01\sc2-ui-return.zip' --map-copy 'D:\test\UI-Test.SC2Components' --evidence '.\run-01\plan'
py -3 "$skill\scripts\stage.py" --bundle '.\run-01\sc2-ui-return.zip' --map-copy 'D:\test\UI-Test.SC2Components' --evidence '.\run-01\applied' --apply
```

从地图导入过的项目应给导出命令加 `--components 'D:\maps\original.SC2Components'`，指定最初导入的来源目录。导出命令只打开本地 HTML，使用独立浏览器会话。每次使用新的输出目录。目标目录需含有 `ComponentList.SC2Components`。若只有单文件地图，先用编辑器将副本另存为组件目录；也可按下述脚本内嵌方式接入，再通过导入模块加入资源。

## 写入编辑器

1. 在编辑器中打开测试地图。用实际窗口标题确认地图，切到触发器模块。先检查是否已有同名接入或旧 UI 创建动作。给专用顶层自定义脚本取名 `SC2WorkbenchUI`。使用清单中的 `integration.include`（默认 `include "Scripts/SC2WorkbenchUI"`）。若当前地图打包方式无法解析 include，确认脚本的资源路径；确需内嵌时，把完整 Galaxy 脚本贴入同一顶层节点，移除 include，保持入口唯一。
2. 从 `ui_manifest.json` 读取 `variables`。按 GUI 识别符找到对应变量，核对生成后的 Galaxy 名称、类型及维数。每个维度至少满足 `minimumArrayLengths`。对清单中的绑定，优先复用原变量；仅创建清单要求且用途明确的 GUI 变量。保留原玩家组、事件、绑定回调和时序。对于标记为 `guiBindingEnabled: false` 的对话框或控件，从 `intent` 判断是否需要运行时接入。只在初始化中使用时，优先将句柄作为参数传给接入函数。若运行时确实需要，`handleScope: "script"` 可直接用于同一地图脚本的回调，`handleScope: "createFunction"` 则在创建时把句柄交给地图现有的脚本回调或其状态。按项目源码流程保存并记录接入，便于重新导出后复用。
3. 按清单 `integration.initialization` 读取 `初始化动作.txt`，把内容贴入对应触发器的自定义脚本动作。新测试地图可创建专用 UI 初始化触发器。旧地图在原 GUI 创建阶段更新专用动作，保留它周围的事件、条件和游戏逻辑，并检查该阶段只创建一次该批 UI。按原运行时流程处理必须在玩家组初始化之后执行的调用。使用系统剪贴板粘贴多行，并读回核对首尾各行；只在确认文本编辑区有焦点时粘贴。
4. 用导入模块核对自定义贴图和字体的内部路径。清单中标记 `gameUI` 的布局检查游戏 UI 注册和加载顺序。游戏原生资源检查地图依赖，自定义资源检查原文件；缩略图不能作为地图贴图。通过编辑器保存测试副本，并检查可重新读出专用节点和初始化动作。

## 结构体成员

当 `variables` 条目标记为 `storage: "structMember"`，请在当前地图中核对原全局结构体及其成员声明。用 `segmentDimensions` 将数组长度对应到点分隔路径的每一层。按清单 `binding.reference` 访问完整成员路径。

## 独立玩家实例

- 当清单 `instanceMode` 为 `perPlayer`，先准备 `audience` 指定的玩家组，再执行整段初始化。生成的动作已经遍历组成员。首维是游戏玩家编号，索引 0 留空。按 `minimumArrayLengths` 核对 GUI 数组，其他维度沿用槽位顺序。
- 对准备、余额、排名、技能和购物的事件，用触发玩家编号访问 `binding.reference`。脚本管理的控件用 `galaxyReference`，两处的 `player` 都替换为本次事件的玩家编号。核对 `hasInstanceFunction` 为真后，比较 `EventDialogControl()` 与该玩家的按钮句柄，再更新该玩家的数组项和单人玩家组。
- 使用两个不同玩家编号做验收。让一名玩家点击「结束购物」或切换准备状态，查看另一名玩家的面板仍可独立操作。按实际游戏玩家编号检查实际句柄。

## 编译与证据

如果项目认可的启动器会为本次启动输出 `compile_errors=N`，可将命令交给 `verify_compile.py`。调用前核对打开的地图标题及启动器读取的是该副本。例如在项目已经具备下面的启动器时：

```powershell
py -3 "$skill\scripts\verify_compile.py" --cwd 'D:\project' --map-copy 'D:\test\UI-Test.SC2Components' --evidence '.\run-01\compile' -- py -3 tools/launch_test_game.py
```

脚本仅解析这次启动器的输出。退出码 0 表示新输出记录为零编译错误，1 表示看到明确错误计数，2 表示需要读取编辑器界面或新日志确认。

- 使用作者项目的启动脚本或已打开编辑器的「测试文档」。如果项目规定只准使用 `tools/launch_test_game.py` 和主窗口命令 `170`，依该流程运行。主图的注入、重新打开、客户端重启等操作遵从项目约定。出现崩溃或战网登录提示时停止。
- 记录本次触发编译的时间和目标文档。捕获本次对话框截图与文本，或保存本次新增的日志段。可用编辑器明确的编译成功通知，或项目脚本输出的、与此次启动匹配的 `compile_errors=0`。只有成功打开新测试场景且无弹窗时，记录实际观察，并注明编译器计数未读到。旧日志、空日志、静态检查和进程存在都不能证明本次零错误。
- 报错时从第一条处理。include 找不到就检查脚本的内部路径和导入登记。名称不存在、类型不匹配或数组越界就核对 GUI 变量、清单和实际生成脚本。重复符号就找重复的 include 或声明。保留完整错误文本及行列。若缺失的符号属于玩法逻辑，报告该符号及引用位置。
- 编译通过后，如任务要求实机，用本次新会话验证显示、按钮状态及各玩家覆盖，保存截图或项目规定的探针证据。编译通过、素材登记和实际游戏行为在交付中各列一项。
