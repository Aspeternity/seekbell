# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5本地补修已完成；当前准备将本地修复合并GitHub，然后独立分支开展已确认的社区热榜与概览模块设置。

## 环境、基准与授权

唯一开发环境SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发；[进入说明](DEVELOPMENT_ENVIRONMENT.md)。分支codex/content-loading-and-source-time，产品58bee30ff55a7c6f0450f6a626806eba1ad49fe8；提交0af171c之后仅本状态与热榜调研文档待提交。origin/main为ee3bc8d，待合并15条本地提交，含单一前端清理及后续界面修复。

本轮用户明确授权把此前本地bug修复/优化上传GitHub并合并，再单独开分支做社区热榜；方案已确认。授权覆盖该修复PR及后续功能开发，不自动公开发布镜像、远程部署或真实发送。不组织多代理，不改D盘、旧Ubuntu或全局WSL。修复PR不包含热榜产品代码。

## 修复范围与适用证据

单一正式前端替代重复原型/正式入口；统一日期范围、筛选与卡片导航；内容区分发布/首次发现时间，保留完整旧查询快照；统一下拉与200ms延迟加载反馈；通知三个记录菜单冷进入预读、就绪整体切换及失败重试；下拉宽度兼顾经典滚动条、版块/渠道完整显示。规格与架构已随实现更新。

[最终补修证据](history/2026-10-23-通知冷进入与下拉宽度补修.md)：SeekBell-Dev、产品58bee30，16组Chromium桌面/手机仿真82项通过；类型/生产构建、格式/隐私/diff、隔离镜像及TLS代理检查通过。后端变更在b009317已有669项通过，之后仅前端变更，复用适用证据。私有详细证据/home/dev/.local/state/seekbell/acceptance/2026-10-23-first-entry-width-fix。Safari/真机/读屏和用户验收仍独立待完成。GitHub当前提交的完整CI尚待运行，不用本地结果冒充远程通过。

## 本地实例与交付边界

同一http://localhost:8001/，seekbell-local/seekbell-local-seekbell-1，原卷seekbell-local_data；镜像seekbell:local-58bee30ff55a，digest sha256:5886d4f1b9e1d6de5c922ca0bf9af8141099eee3f6a72e594f80daf58f364202。保留账号/配置/历史，仅localhost映射，健康核验见上节；回退镜像6ee4af9。备份local-runtime/backups/before-58bee30ff55a.tar.gz；[管理入口](history/2026-10-23-最新代码本地Docker实测启动.md)。本轮未更新实例。旧18080/18081已退役；公开仍ui-restore-5，远程Stack及8000/4175未动。

## 社区热榜与下一步

[调研与示意证据](history/2026-10-23-概览模块与热榜方案调研.md)。确认三模块显隐/纵向排序、服务端保存、恢复默认；上方统计固定。热榜支持网站与周期两层切换、按网站记忆；首接NodeSeek第三方实时/每日/每周，未来论坛按能力扩展，不实施Linux DO/V2EX采集。三个候选接口单次HTTP200、30/50/100条；算法与窗口语义/长期可用性未验证。RSS最新不能冒充热门。示意320/736px检查通过，聊天内嵌错误未确认恢复，截图后备；不是产品验收。

下一步：提交交接文档并推送既有修复，创建PR、确认CI通过后合并；从最新main创建codex/community-hotlist，将确认方案回写权威文档。恢复读取本状态、补修记录、调研记录及相关代码。无技术阻塞；尚未创建PR或新分支。
