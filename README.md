# SC2 UI 工作台

用于制作《星际争霸 II》地图对话框的单文件网页工具。可在画布上摆放控件、对照游戏截图，再导出 Galaxy 布局脚本，交给银河编辑器的 GUI 触发器使用。

## 快速开始

1. 下载 `index.html`，用桌面版 Chrome 或 Edge 打开。也可通过 GitHub Pages 使用。
2. 从「布局模板」选择一个起点，或在「项目」中新建空白项目。左侧管理图层，右侧调整坐标、锚点、贴图、字体和变量绑定。
3. 从「项目 → 保存项目 JSON」导出工程备份。离线文件与 GitHub Pages 页面各有自己的浏览器草稿，可用项目 JSON 在两者之间迁移。

## 工作台功能

- 三套工作台主题、快速命令、图层搜索、锁定、拖放排序与附着。
- 多对话框、按玩家预览、参考截图、16:9 与 4:3 检查，以及可调整的重复布局和 GUI 数组绑定。
- 投票、英雄选择、三选一、天赋树、观战资源、排行榜等布局模板。
- 本地贴图库、按钮图集匹配、字体样式编辑、SC2Layout 与 SC2Components 导入。
- 导出 Galaxy 脚本、初始化动作、GUI 变量清单和地图回导 ZIP。回导包中的 `ui_manifest.json` 可交给本地 agent，辅助接入地图的 GUI 触发器。

| 快捷键 | 操作 |
| --- | --- |
| `Ctrl / ⌘ + K` | 打开快速命令 |
| `/` | 搜索图层 |
| `Space` + 拖动 | 平移画布 |
| `Ctrl / ⌘` + 滚轮 | 以指针为中心缩放 |
| `Shift + 1` / `Shift + 2` | 适应画布 / 聚焦选区 |
| `Shift + F` | 切换画布专注模式 |

## 使用本地素材与回导

- 点击「贴图库 → 素材来源与接入设置 → 连接图标浏览器文件夹」，选择本地 [SC2 UI 图标浏览器](https://github.com/spuperoldhen/sc2-ui-browser) 的仓库目录或 `web` 文件夹。也可以直接导入 DDS。原生控件样式在载入图集后按本地贴图预览。
- 公开包用近似外观提供初始预览。原生游戏图集以及六栏投票大厅的截图和贴图由使用者在本地提供。工作台生成的紫色投票按钮可以从导出窗口下载。
- 回导时，按工具内的图文教程在地图副本中接入布局。已有 GUI 事件、计时和玩法逻辑可调用导出的控件变量。HUD 重叠按参考区估算，可用实机截图复核。

## 发布到 GitHub Pages

1. 解压发布包，将 `index.html`、`README.md` 和 `.nojekyll` 放到仓库根目录并提交。
2. 在仓库的 **Settings → Pages** 中选择 **Deploy from a branch**，选择包含这些文件的分支和 **/ (root)**，保存。
3. 部署完成后，从 Pages 设置页打开站点。开发时也可在该目录运行 `python -m http.server 8000`，然后访问 `http://localhost:8000/`。

详情见 [GitHub Pages 发布源配置](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)。
