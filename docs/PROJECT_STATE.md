# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5实测修正。筛选/日期/通知计数修复已本地提交；结构清理及正式浏览器验证已完成，正进行最后容器打包核对，均未发布。

## 环境与授权

仅SeekBell-Dev:/home/dev/projects/seekbell开发；聊天在原Ubuntu时经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。当前codex/single-production-frontend，基于修复a7435a2ecb062f20c43d0ede5f0bd3dd6b0c9143，本轮实现与文档同提交。用户要求“进行结构清理”“继续任务”；保持批准UI和统计口径，数字点击搁置。拒绝的改版/结果按钮组不得实施；内嵌可视化不可用，使用文字/实际截图。无本轮推送、公开发布、部署、真实采集/消息授权，不组织多代理，不动旧D盘/Ubuntu/全局WSL。

## 当前改动与证据

[结构清理记录](history/2026-10-23-单一正式前端结构清理.md)含原因、覆盖迁移与命令。frontend/src统一App/Bootstrap、pages/components/styles、真实store/API模块；移除live/prototype双目录、组件注入/别名、演示入口/构建/账号/备份/规则引擎和重复页面，预览仅用正式API。本轮包括上述源文件/构建/CI、浏览器迁移用例、预览回归、当前说明与退役资料。离线合成运行器保留供CI，不是第二产品。既有UI/业务/迁移未改变。

已通过SeekBell-Dev后端659项、类型/正式构建、Ruff/Prettier/隐私/diff。结构审计23个正式组件/页面仅导入路径变化，CSS有效声明相同。浏览器56项全部通过，含新增8项真实通用UI替代演示专项；离线核心/后台/加密备份及wheel检查通过，容器打包待核对。证据/home/dev/.local/state/seekbell/acceptance/2026-10-23-single-frontend，使用临时库/合成传输，不冒充真实RSS/消息、Safari/手机真机、远程CI或用户验收。

上轮a7435a2修复说明对齐、过滤/详情闪动、四处全部日期、任务选项/中文版块、网站筛选尺寸与通知共享计数；[记录](history/2026-10-23-筛选日期与通知计数修复.md)含后端15、浏览器76及截图证据。该旧结果不代替当前结构验证。

## 发布状态与保护

公开镜像仍ui-restore-5，代码c8be41c9a1f85650be6447e773b73a204dba9b88，digest sha256:089289552719774057aa527bbd055e7c33370e6cc5c1811c0da4583b0675f7ff；记录见[旧回执](history/2026-10-23-通知导航焦点与概览任务行修复.md)。本轮未更新镜像/部署。

保护18080/18081、seekbell-acceptance-b45fc2c-20261020容器/卷、backup-local、旧Stack/卷及8000/4175；Compose沿用8001与seekbell_compare_data，禁止同SQLite卷双实例。下一步完成本地容器打包与TLS核对、保存最终证据；发布须用户明确指示。恢复读本状态、结构记录及受影响代码。
