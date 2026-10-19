# 管理界面原型 v0.1

本轮交付概览、任务编辑与移动布局，供用户确认视觉与交互。实现为 Vue 3 + TypeScript + Vite，采用自定义组件；既有 Naive UI 依赖保留。其余页面、认证与后端接入等待后续阶段。设计规则见 [UI_DESIGN.md](UI_DESIGN.md)。

## 运行

正式开发目录为 SeekBell-Dev 内的 /home/dev/projects/seekbell。Windows 终端：

~~~powershell
wsl.exe -d SeekBell-Dev --cd /home/dev/projects/seekbell -- bash -lc 'pnpm --dir frontend dev:prototype'
~~~

打开 [概览](http://localhost:5174/prototype.html#/) 或 [任务编辑](http://localhost:5174/prototype.html#/task/deals)。需要保持上述进程运行；Ctrl+C 停止。本机端口绑定 127.0.0.1，不对局域网开放。浏览器缩窄窗口即可体验移动布局，手机真机访问未配置。

首次安装/换机器在正式目录执行：

~~~bash
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend dev:prototype
~~~

仅运行界面不需要 Python、数据库、Docker 或通知凭据。Node/pnpm 版本沿用 [开发环境](DEVELOPMENT_ENVIRONMENT.md)。原型可独立打包并静态预览：

~~~bash
pnpm --dir frontend build:prototype
pnpm --dir frontend preview:prototype
~~~

产物为 frontend/dist-prototype/，入口仍为 prototype.html。原 frontend/index.html、src/App.vue、生产构建 dist/ 与 API 调用未替换；原型不被 Docker 的默认前端构建收录。

## 可体验的流程

1. 概览：固定模拟运行快照，24 小时/7 天趋势切换，任务搜索、状态筛选、启停、新建/编辑入口，模拟最近命中说明。
2. 编辑：任务名称、备注、启用、匹配范围、最多 16 个条件组、全部/任一关键词、全局排除词、版块多选、精确作者、大小写与英文整词、多目标通知。
3. 关键词回车/英文逗号或失焦提交，短语保留内部空格；中文输入法确认不会提前提交。空条件组在保存/试算时忽略。
4. 右侧自然语言规则说明随输入变化；模拟输入/5 条合成历史样本试匹配，呈现命中、不命中、信息不足及原因。规则或样本变动后旧结果失效。
5. 校验名称与至少一个目标；保存回概览并保留到当前浏览器；取消/导航离开有未保存确认，刷新有浏览器原生离开提示。
6. 手机：抽屉导航、双列统计卡、任务卡片、单列编辑、章节跳转、底部保存栏；导航支持 Escape、焦点约束，弹窗使用原生 dialog。

所有采集状态、投递、计数、最近命中与目标均为合成数据。新建或修改规则不会重新生成模拟历史计数。目标勾选不会发送消息。所有未交付导航给出阶段说明，不伪装可用业务页。

任务仅写 localStorage 键 seekbell-ui-prototype-v1，与后端数据库无关；不同浏览器/端口不共享。无效 JSON 回退默认样例，存储不可用时提示仅本次会话有效。需要重置时清除该站点的浏览器存储。

## 源码结构

|路径|职责|
|---|---|
|frontend/prototype.html|独立 HTML 入口|
|frontend/vite.prototype.config.ts|独立本地服务和构建输出|
|frontend/src/prototype/App.vue|导航、弹窗、模拟任务持久化|
|frontend/src/prototype/Overview.vue|概览、图表与任务列表|
|frontend/src/prototype/TaskEditor.vue|规则表单、说明、试匹配|
|frontend/src/prototype/model.ts|模拟数据与原型专用无网络试算|
|frontend/src/prototype/components/|图标、标签输入与开关|
|frontend/src/prototype/style.css|视觉变量与响应式样式|
|frontend/tests/prototype.spec.ts|浏览器交互与规则边界验证|

原型试算参考既有三值语义，处理条件组 OR、组内 AND、排除优先、字段缺失及不跨字段拼词。它不是新的正式规则引擎。当前 JS 英文大小写使用 toLowerCase，与 Python casefold 的完整 Unicode 行为不完全一致；正式接入时移除该模拟执行分支，统一调用后端 RuleEngine，不能把它作为业务权威。备注当前仅为原型字段，后端映射待确认。

## 验证

在正式目录执行：

~~~bash
pnpm --dir frontend format:check
pnpm --dir frontend build
pnpm --dir frontend build:prototype
# 首次准备浏览器；本机已存在对应 Chromium，无需重复安装
pnpm --dir frontend exec playwright install chromium
pnpm --dir frontend test:prototype
git diff --check
~~~

Playwright 同时运行桌面 1440×1000 和 Chromium 模拟 iPhone 13，两组共 12 项。测试阻止非本地及 /api、/health 请求；覆盖搜索/启停/持久化、新建校验、三值试匹配、放弃修改、菜单键盘操作、无页面异常和控制台错误/警告、截图，以及 320/360/390/768/1024/1440 编辑页横向溢出检查。截图在 frontend/test-results/，不入 Git；测试与截图均为 Chromium，不能视为 Safari 或手机真机验收。

本轮最终证据、代码 SHA 和未完成验证见 [阶段记录](history/2026-10-19-UI原型.md)。CI 已加入原型构建与浏览器测试步骤；本轮未推送、未运行远程 CI、未发布或部署。
