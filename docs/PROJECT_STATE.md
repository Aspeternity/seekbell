# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5用户实测修正。通知标签404、粗焦点框与概览任务行点击已修复，本地检查通过；用户已明确要求发布新镜像供实机测试，ui-restore-5准备发布。

## 环境、代码与授权

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。本轮实现b7ae06e907977cc3f4189bad8414cbbc7b9855aa已快进合并main，原功能分支保留；本次提交只补发布状态。用户2026-10-23明确“发布新镜像 我做实机测试”，授权本轮必要合并/推送、公开GHCR发布及临时开关；不代部署、不真实采集发送。源码private、包public，不组织多代理，原D盘/Ubuntu/全局WSL不动。

## 本轮实现与证据

Targets/Records正确透传通知标签路径，四标签当前态/切换/前进后退/刷新正常。文字输入/原生下拉使用自身细边框与浅阴影，搜索外壳统一焦点反馈、内部填满；按钮/链接/复选单选保留键盘焦点，标题无外框。正式/演示概览与任务列表共享点击保护，信息格与空白打开配置；开关/状态区/操作按钮、修饰键和拖选文字独立，原UI布局/比例不变，稳定约定已写UI_DESIGN。

[本轮实现与验证](history/2026-10-23-通知导航焦点与概览任务行修复.md)。修复前正式构建新增三例均准确复现；本地正式UI8项32.8秒、history4项19.1秒、原型44项45.2秒共56浏览器通过，两版类型/构建、全前端格式、隐私/diff通过，桌面/手机截图已核对。无后端改动，不复用旧616项宣称新SHA已测。仅独立临时库/模拟服务，真实设备/Safari未验。新增用例属于独立UI套件，避免与管理员变更套件累计触发真实登录限流，未放宽产品限制。

## 发布进度

目标ghcr.io/aspeternity/seekbell:ui-restore-5；准备执行同SHA完整baseline，再原生amd64/arm64演练，复用已测字节发布及匿名拉取核对。预检确认五旧标签digest留底、新标签不存在、源码仍private；发布开关原缺失，仅本次临时启用，结束必须恢复。操作状态/原始日志在/home/dev/.local/state/seekbell/releases/ui-restore-5，待成功回执后更新IMAGE_RELEASE/Compose。

当前可用仍ui-restore-4，代码0499f8b1972f9131e0d977ea96305ccb93d5d327，索引sha256:09d7af1aa081594c2bb77f949f4bdcd534728618eef3bd3b667d708619a87e3a；旧发布616后端/82浏览器及双架构匿名证据见[回执](history/2026-10-22-通知目标删除与ui-restore-4发布.md)。前轮删除/RSS/TG修正均保留，本轮无数据库/接口语义变更。

## 保护与下一步

8001:8000与seekbell_compare_data沿用原Portainer Stack/卷；禁双实例共用SQLite卷。保护18081项目seekbell-acceptance-b45fc2c-20261020及容器/卷/backup-local、旧Stack/卷/8000/4175/18080；本轮本地5174/8012/8019已退出。仅NodeSeek。无外部阻塞；下一步完成CI/双架构、回执/匿名拉取与Compose交付，再由用户实机验收。交接读本状态/本轮记录，发布维护按IMAGE_RELEASE。
