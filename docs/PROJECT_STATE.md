# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。用户后续确认只展示命中依据，本轮已实现，后端26/浏览器16项验证通过，待提交/镜像更新；8001仍运行上轮0f74ed8。

## 环境与授权

唯一环境SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发，见[环境](DEVELOPMENT_ENVIRONMENT.md)。codex/overview-modules-and-hotlist；最新产品0f74ed813726b762f7704c764feaf764e50b3394，随后仅交付文档。之前产品2a37ebc、2665aa6，功能基线e53d89e、规格7f8c15b、main 2c682de；此前PR #1已合并，见[记录](history/2026-10-23-本地修复合并与热榜分支.md)。

已授权本分支开发、本地Docker实测及反馈修正；本轮明确取消其他判定入口，只展示命中任务/原因，无命中只显示简洁状态，沿用8001保留数据更新。不含新功能推送/合并、公开发布、远程部署或主动真实发送。无多代理，不改D盘、旧Ubuntu、全局WSL或8000/4175。上一产品/交付已提交，本轮未提交路径见下方，无其他用户改动。

## 实现

契约SPEC、ARCHITECTURE、UI_DESIGN已回写；[本轮记录](history/2026-10-23-内容详情仅展示命中依据.md)。Content仅请求新增group=matched，API在分页前严格过滤match，即使零命中也不返回失败任务。区域“命中依据”，删除其他任务的折叠/状态/加载器/样式，移除未用EvaluationPage类型；命中卡片按任务显示保存版本/原因，多页才显示分页。无命中区分no_match/insufficient_data/not_evaluated/unrecorded，加载/错误不冒充空态；旧未知记录说明与换帖隔离保持。

后台保留全部历史判定，旧all/primary/other读接口及计数兼容，不改规则/采集/通知或数据库迁移。本轮未提交：api/history.py、services/history.py、Content.vue/history.ts、tests/test_history.py、evaluations.spec.ts及四个受标题变更影响的浏览器文件、契约/状态/本轮记录。类型/生产构建/格式/Ruff/diff通过；后端history26项、命中依据8/既有历史4/详情加载2/概览入口2共16浏览器通过；测试路由收尾问题已修正，不改产品逻辑或放宽检测。

原功能保持：0010保存模块布局/选择，三模块显隐/排序，上方统计固定；仅NodeSeek第三方三周期，5/10条。热榜缓存立即返回/后台更新、同站其他周期预取，无消费者循环或磁盘快照；首次/重启无缓存仍需读取。热榜不入规则/历史/通知。最近命中/热榜整行打开内容详情/原帖，版本按任务独立计数。Linux DO/V2EX未接入。前阶段细节见[热榜记录](history/2026-10-23-热榜缓存与整行点击.md)。

## 验证与本地实例

0f74ed8：后端history26项通过；桌面/手机分组8、history4、内容稳定8共20浏览器通过；最终去空汇总块后重建并补验前12项通过，不重复计数。类型/生产构建、Prettier、Ruff/diff/隐私及镜像禁外网服务/静态/健康/重启/配置持久化通过。新增test:evaluations独立8029临时实例/CI步骤；初轮共用history触发测试登录限流，已分离，正式限流不变。自动验证为合成库/模拟HTTP，无真实论坛/通知；未声称重跑完整CI或用户验收。

同一http://localhost:8001/或127.0.0.1:8001；seekbell-local/seekbell-local-seekbell-1、原卷seekbell-local_data，运行seekbell:evaluations-0f74ed813726，镜像ID sha256:0a8abd90f8e512de314fee5c699847f47435405d5752c2557d0015534f33b705。仍0010，healthy/read-only/unless-stopped，仅本机8001。Windows两地址/版本/资源通过，保活PID14716身份/创建时间一致，运行元数据已更新。

已停服整卷备份before-0f74ed813726-20261023-200412.tar.gz（local-runtime/backups，0700/0600），逐文件SHA、解包副本SQLite与实际更新前后12类配置指纹通过。账号/配置/历史保留，无合成导入。旧2a37ebc同0010可回退；更旧58bee30需配旧库备份。证据/home/dev/.local/state/seekbell/acceptance/2026-10-23-evaluation-snapshots；完整SHA/命令见本轮记录。

下一步完成只展示命中的针对性验证/提交/隔离镜像检查，备份当前数据后更新同一8001；推送/合并另行处理。恢复读本状态、本轮记录及相关实现；无技术阻塞。
