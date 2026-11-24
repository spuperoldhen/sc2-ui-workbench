---
name: sc2-galaxy-bridge
description: Export a saved SC2 UI Workbench project to Galaxy, stage it in a local .SC2Components test map, wire it into StarCraft II Galaxy Editor using the local desktop, and verify a fresh compile. Use for 自动导出 Galaxy, 地图回导, 接入银河编辑器, UI 编译校验, or 实机预览. Requires Workbench v1.0.2 or a compatible later version.
---

# SC2 Galaxy 导出与校验

在本机完成「工作台项目 → 地图副本 → 银河编辑器编译」。需要工作台 `index.html`、项目 JSON、目标地图测试副本。项目从地图导入时，还需要原始 `SC2Components` 来源目录。保留用户指定的测试副本路径并先读取其项目约定。

1. **导出。** 从当前工作台保存最新项目 JSON。使用本技能 `scripts/export.mjs`，通过工作台自身的校验和导出器取得回导 ZIP。若用户已经提供回导 ZIP，直接预检。导出失败时，先读错误和控件位置，修正项目或补齐原路径资源再重试。按清单核对由地图依赖提供的资源。
2. **预检并写入。** 确认目标是独立测试副本。以 `scripts/stage.py` 预检 ZIP，检查 `stage-report.json`；关闭测试副本的文档后加 `--apply` 写入。GUI 包使用 `Scripts/SC2WorkbenchUI.galaxy`；v1.0.5 预览包由工作台启动器以 `preview=True` 调用同一脚本，脚本为 `Scripts/SC2WorkbenchPreview.galaxy`。若地图已有不同的同名文件，按键合并本地化文本或在编辑器中合并字体样式；保留地图原文件作为备份。迭代时用同一副本的上一份成功报告 `--previous`，用于核对可替换文件的哈希。
3. **编辑器接入。** 使用本机可用的 Windows 桌面工具操作银河编辑器。打开测试副本，读取清单、脚本和初始化片段。建立或更新唯一的顶层自定义脚本，按清单核对 GUI 变量、补齐资源登记，再将初始化片段写入对应触发器。读取 [Windows 编辑器操作手册](references/windows-editor.md) 执行，核对文件与地图标题再保存。只有一个清楚的接入点时继续执行；存在多个可能的初始化阶段且会改变玩法时，向作者确认目标。
4. **编译与取证。** 每次记录目标地图和启动时间。用项目规定入口发起新一轮校验，读取本次编译窗口或日志，并记录原始错误消息、文件、行列和证据路径。对确定的接入问题修复后重编，最多追加两次；依赖或设计问题交代具体阻塞项。没有本次编译证据时报告未校验。游戏行为需要另外验证。
5. **交付。** 列出项目 JSON、测试地图、回导 ZIP、阶段报告、编译证据，以及剩余资源或运行问题。交付报告分别记录导出预检、地图写入、编辑器编译、实机观察。

## 实机预览（v1.0.5+）

预览包只创建和显示对话框，不接入触发器、事件、动作函数或 GUI 变量；响应逻辑由地图作者或本地 agent 另外注入。合成画布开启时清单的 `preview.dialogIds` 是全部对话框，关闭时只有当前页。

```powershell
py -3 .\tools\live_preview.py --map-copy 'D:\SC2\黄金矿工-UI-Test.SC2Map'
```

- 给普通用户时双击工作台根目录的 `启动SC2 UI 工作台.exe`：无窗口、无控制台，浏览器就是界面；页面关闭后服务自动退出并释放端口。agent/自动化用上面的源码命令，或 `tools\启动SC2 UI 工作台（备用）.bat`。
- 启动器在 `127.0.0.1:8765` 提供工作台页面；只有这个地址下页面才出现「写入并测试」。EventSource 由启动器注入，页面只需保留 `sc2-preview-bridge` meta；`index.html` 每次请求读取，替换后刷新即可。
- 默认 `--launch direct`：写入预览脚本，自动补齐 `include "Scripts/SC2WorkbenchPreview"` 和 `SC2WorkbenchPreview_Init();`，再用 `Support64\SC2Switcher_x64.exe -run "<地图>" -displaymode 0` 直启，上一局会被先结束。不要直接运行 `SC2_x64.exe`，会缺 `icuuc52.dll`。
- `--launch editor`：保留银河编辑器「测试文档」流程，需要测试副本已在编辑器中打开并保存。
- 测试副本目录名要以 `-UI-Test` 结尾并含 `ComponentList.SC2Components`。首次覆盖字体样式加 `--replace-font-styles`。
- `scripts/preview.py` 是另一条本地直启路径（部署 + 接线 + 截图），不依赖页面。

仅在可以操作本机银河编辑器和读取编译结果时执行第 3–4 步。地图副本、编辑器或登录状态阻塞时，完成还能执行的步骤并报告所处阶段。项目启动规则优先；崩溃或账号登录提示出现时停止自动化。
