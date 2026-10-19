# 完整管理界面演示 v0.4

用户已确认首轮视觉并授权扩展全部网页。网站管理使用居中内置库与已添加卡片列表，点击卡片仍打开右侧配置；手机保持全屏面板；首次不添加任何网站。本版以 Vue 3 + TypeScript + Vite 实现六个管理模块、初始化/登录及桌面与手机布局，自定义组件，从零设计。交付完整源码、静态构建、截图与 [设计规范](UI_DESIGN.md)。

**这是完整前端模拟数据版，尚未接入真实后端。** 可以连续体验管理流程，但浏览器里的运行状态、登录、连接测试、投递和备份均不代表真实服务。M3 的服务端认证、受保护 API、采集调度和生命周期仍待实现。默认生产入口仍是原服务状态页。

## 立即预览

本机开发预览：[打开 SeekBell](http://localhost:5174/prototype.html#/)。

完整交付 ZIP 同时包含预构建 frontend/dist-prototype。解压到独立目录，在该目录使用 Node 24 运行：

~~~bash
node frontend/serve-prototype.mjs
~~~

打开 [静态预览](http://localhost:4175/prototype.html#/)。不需要安装依赖、数据库、Docker 或填写通知凭据；需要保持终端运行，Ctrl+C 停止。服务只绑定本机 127.0.0.1。不要双击 HTML 以 file 协议打开。Git 仓库不跟踪构建产物，从 Git 获取源码后须先构建。

## 开发与构建

本机正式工作目录为 SeekBell-Dev 内 /home/dev/projects/seekbell，不能在原 Ubuntu 或 D 盘交接副本继续开发。Windows 终端：

~~~powershell
wsl.exe -d SeekBell-Dev --cd /home/dev/projects/seekbell -- bash -lc 'pnpm --dir frontend dev:prototype'
~~~

首次克隆在正式目录安装锁定依赖：

~~~bash
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend dev:prototype
~~~

Node/pnpm 版本见 [开发环境](DEVELOPMENT_ENVIRONMENT.md)。构建与静态预览：

~~~bash
pnpm --dir frontend build:prototype
node frontend/serve-prototype.mjs
~~~

构建输出 frontend/dist-prototype，入口 prototype.html。原 index.html、src/App.vue、生产 dist/ 与 API 未替换，Docker 默认构建不收录演示版。开发预览使用 5174，免依赖静态预览使用 4175；不同端口的浏览器数据互相独立。

## 页面与可体验流程

以下路径均接在 prototype.html# 后。

|模块|路径|已实现行为|
|---|---|---|
|概览|/|统计快照、24小时/7天趋势、来源健康、异常入口、任务筛选/启停、最近命中|
|监控网站|/websites|空态、内置库添加、卡片搜索/状态筛选、侧栏配置/手机全屏、独立频率/启停/模拟测试、关联任务与移除|
|监控任务|/tasks、/task/new、/task/:id|搜索筛选、复制、启停、删除确认、编辑与试匹配|
|内容与命中|/content、/content/:id|关键词/任务/版块/日期/状态筛选、分页、RSS摘要、命中原因、关联投递|
|通知目标|/notifications/targets、/target/new、/target/:id|四种渠道新建编辑、表单校验、启停、依赖删除检查、独立模拟测试|
|投递记录|/notifications/deliveries、/notifications/deliveries/:id|搜索/状态/目标筛选、状态详情、结果未知提示、独立手动重发|
|目标测试|/notifications/tests|与帖子自动投递分开的测试记录|
|系统设置|/settings/preferences、/account、/backup、/about|工作空间名称/说明及预览、时区/保留策略/告警目标、管理员/密码、导入导出、版本、重置演示|
|初始化/登录|/setup、/login|唯一演示管理员、输入校验、登录失败、修改密码、退出与访问跳转|
|异常路径|其他路径|404与返回概览；缺失任务/目标/内容/投递有明确状态|

初始进入空工作空间，网站/任务/目标/历史均为空。按“添加网站”选择NodeSeek，默认暂停；添加后回到卡片列表，点击卡片打开右侧配置，启用后创建任务。若只想审阅全部界面，可在概览或网站空态点击“载入示例工作台”，明确确认后替换为合成数据。默认演示用户名 admin、密码 SeekBell2026!；可在登录页或系统设置体验初始化。初始化创建唯一的浏览器演示管理员，不使用初始化令牌。真实服务不能使用该演示认证实现。

任务编辑支持名称、备注、匹配范围、最多16组关键词、全局排除、版块、精确作者、大小写/英文整词、多个目标。关键词回车/英文逗号/失焦添加，中文输入法确认不会提前提交。规则说明实时更新；模拟输入及5条合成历史试算返回命中/不命中/信息不足。输入变化清除旧结果；保存校验，离开/后退/刷新有未保存保护。

网站独立配置，同站任务共享采集；已有任务固定所属网站，有任务依赖时阻止移除网站。移除保留历史；重新添加从未采集状态开始。来源恢复提示重新建立当前基线。任务复制默认停用；删除后历史保留名称快照。目标停用取消本地等待重试，重新启用不恢复积压。手动重发创建独立记录；结果未知明确可能重复。SMTP成功只表示服务器接受。目标测试单独记录，不冒充自动投递。

## 数据与真实业务边界

- 所有页面使用共享浏览器状态；任务、目标普通元数据、来源设置、显示偏好及模拟记录可持久化。损坏或不兼容的浏览器数据回退空工作空间；存储不可用时提示仅本次会话有效。
- 键 seekbell-demo-v3；兼容迁移v2数据与备份，将隐含NodeSeek来源转为显式实例并保留原任务/历史/设置，也兼容首轮 seekbell-ui-prototype-v1 任务。管理员摘要单独保存在 seekbell-demo-account-v2，会话在 sessionStorage。账户密码仅为演示用盐化 SHA-256 摘要，**不是服务端认证或安全边界**，不得用于保护真实数据。
- 通知连接地址、Token、Device Key、Chat/Topic ID、SMTP账号/发收地址及Webhook Header等输入只保留于当前表单内存，保存后仅留下“已配置”演示标记。切换页面后不保留真实连接值，不应填写真实凭据。
- 导出是有版本标识的普通演示 JSON，不含账号、会话和连接凭据。导入校验大小、版本、结构、枚举及关联，按白名单重建状态，经确认替换当前演示数据。**不等同 SQLite/加密密钥的生产备份恢复。**
- 数据集是固定合成样本。概览趋势、部分计数和历史不随时间自动生成；保存规则不会重新扫描历史。时区只改变展示及日期过滤；保留天数/告警设置没有后台清理或发送。
- 合成帖子没有真实原帖地址，详情明确说明；不伪造真实帖子链接。正式接入后从规范帖子 URL 提供原帖入口。
- 原型试算无网络，只用于交互验证。JS toLowerCase 不等同 Python 完整 casefold；正式接入应移除原型执行分支，统一使用后端 RuleEngine。备注为原型字段，正式映射仍待确认。
- 未调用真实 API、论坛或通知渠道；无真实采集、自动调度、真实登录、后台重试、实时监控。

## 源码结构

|路径|职责|
|---|---|
|frontend/prototype.html、vite.prototype.config.ts|独立入口与构建|
|frontend/serve-prototype.mjs|只依赖 Node 的本机静态预览|
|frontend/src/prototype/App.vue|路由、导航、访问跳转、未保存保护、全局弹窗|
|frontend/src/prototype/websites.ts|内置网站目录、能力声明与实例类型|
|frontend/src/prototype/store.ts|共享模拟状态、白名单持久化、演示账号、备份和操作|
|frontend/src/prototype/Overview.vue、TaskEditor.vue|概览与规则编辑|
|frontend/src/prototype/pages/|TaskList、Websites、Content、Notifications、TargetEditor、Settings、Auth|
|frontend/src/prototype/model.ts|样例与无网络试算|
|frontend/src/prototype/components/|图标、标签输入、开关|
|frontend/src/prototype/style.css、workspace.css|设计变量、组件与响应式布局|
|frontend/tests/prototype.spec.ts、workspace.spec.ts、websites.spec.ts|浏览器交互、规则边界、全页面与移动适配|

## 验证与交付证据

~~~bash
pnpm --dir frontend format:check
pnpm --dir frontend build
pnpm --dir frontend build:prototype
# 首次准备浏览器；本机已有 Chromium，无须重复安装
pnpm --dir frontend exec playwright install chromium
pnpm --dir frontend test:prototype
git diff --check
python3 scripts/check_privacy.py --identity
~~~

两组 Chromium 桌面1440×1000与模拟 iPhone 13，共40项通过。覆盖居中弹窗/右侧面板位置分离、工作空间自定义/长度校验/持久化/旧数据兼容与备份恢复、首次空态、网站添加/移除/依赖/配置保护、v2保留迁移、多个测试适配器配置隔离，以及全部页面、任务/来源/通知关联、四渠道表单、独立重发/测试、备份导入导出、账号全流程、损坏数据、键盘及未保存保护。20类页面逐一检查320/768/1024宽度，规则编辑额外检查320/360/390/768/1024/1440。测试禁止外网和/api、/health请求，检查页面异常及控制台警告/错误，输出桌面/手机截图。

截图在 frontend/test-results，不入 Git；交付包 screenshots 保留审阅图。Chromium仿真不能视为Safari、真机或完整无障碍验收。最终实现SHA与证据见 [添加弹窗与工作空间记录](history/2026-10-20-添加弹窗与工作空间.md)。本轮未运行远程CI、未发布、未部署，后端既有测试未因纯前端扩展重复执行。

## 工作空间自定义

系统设置→偏好与保留中填写工作空间名称（1–24字符）和说明（可选，最多40字符），查看预览后保存。左侧顶部立即同步；也可点击该区域进入设置。长文本省略，悬停显示完整值；说明留空时隐藏第二行，图标使用名称首字符，默认外观仍为S/个人工作空间/Administrator。管理员登录账号不受影响。

设置随普通配置导出/恢复。旧v2/v3数据缺失新字段时补默认值，已有网站/任务/偏好保留。重置或载入示例工作台会按明确提示替换演示设置。所有数据仍只存当前浏览器。
