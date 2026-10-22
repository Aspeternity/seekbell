# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5实测修正。筛选/日期/通知计数修复及单一正式前端结构清理已本地实现、验证并提交，未发布；统计数字点击搁置。

## 环境与授权

仅SeekBell-Dev:/home/dev/projects/seekbell开发；聊天在原Ubuntu时经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。当前codex/single-production-frontend，最后实现d224853a2f24cd003ff02eafb27a1532e78e54bf，其后仅证据文档。用户授权“进行结构清理”“继续任务”，保持批准UI及统计口径，拒绝的改版/结果按钮组不得实施。内嵌可视化不可用，使用文字/实际截图。用户追加授权清理无用旧Docker实例，已退役18080/18081及同批失败容器，旧数据先在仓库外归档。无本轮推送、公开发布、新部署、真实采集/消息授权；不组织多代理，不动旧D盘/Ubuntu/全局WSL。

## 实现与证据

[结构清理](history/2026-10-23-单一正式前端结构清理.md)含原因、测试迁移与命令。唯一正式入口App/Bootstrap，pages/components/styles和真实store/API模块；移除live/prototype双目录、组件注入/别名、独立演示入口/构建/账号/备份/规则引擎及重复页面，预览只用正式API。离线合成运行器供CI检查，不是第二产品。既有UI/业务/迁移不变，旧说明归档、当前运行/CI统一。

SeekBell-Dev、实现d224853：后端659项、浏览器58项（含新增通用UI8及实际TLS代理2）、类型/正式构建、Ruff/Prettier/隐私/diff、离线核心/后台/加密备份、wheel和无外网容器检查通过。结构审计23个迁移正式组件/页面仅导入路径变化，CSS有效声明相同；dist仅index.html，无演示状态键。截图已核对，证据/home/dev/.local/state/seekbell/acceptance/2026-10-23-single-frontend。临时端口/容器退出、检查镜像移除，原运行实例前后一致。不冒充远程CI、真实RSS/通知、Safari/真机或用户验收。

此前修复a7435a2包含说明对齐、筛选/详情闪动、四处全部日期、任务选项/中文版块、网站控件与通知共享计数；[记录](history/2026-10-23-筛选日期与通知计数修复.md)保留原证据，已纳入本次正式浏览器验证。

## 发布状态与下一步

公开镜像仍ui-restore-5，代码c8be41c9a1f85650be6447e773b73a204dba9b88，digest sha256:089289552719774057aa527bbd055e7c33370e6cc5c1811c0da4583b0675f7ff，[旧回执](history/2026-10-23-通知导航焦点与概览任务行修复.md)。本轮未更新镜像/部署。

[旧Docker已定向清理](history/2026-10-23-旧Docker实例退役清理.md)：3容器、3专属卷、2网络、2旧镜像移除，18080/18081释放；rootless现无容器/卷，其他镜像标签保持。旧数据归档在/home/dev/.local/state/seekbell/maintenance/2026-10-23-retired-docker/archives，权限0600、SQLite和SHA校验通过，未入Git。原Ubuntu、远程Stack及8000/4175仍未动。Compose沿用8001与seekbell_compare_data，禁同SQLite卷双实例。结构清理及旧Docker清理完成，无阻塞，下一步用户审阅；发布/部署需明确指示。恢复读本状态、结构记录与受影响代码。
