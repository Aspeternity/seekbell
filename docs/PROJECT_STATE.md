# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。此前本地修复已通过GitHub CI并合并；当前阶段为社区热榜独立分支准备，确认方案已回写规格，产品实现尚未开始。

## 环境、分支与授权

唯一开发SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发；[进入说明](DEVELOPMENT_ENVIRONMENT.md)。当前codex/community-hotlist，从main合并提交2c682deb491bd7df9a09bfc4df15d15f3cd18b7f创建；本地main/origin/main一致。最终修复产品58bee30ff55a7c6f0450f6a626806eba1ad49fe8，其后为文档和合并提交。

用户明确授权此前修复上传GitHub合并，并在独立分支做已确认的社区热榜及模块设置。授权覆盖新功能开发，不含新功能合并、公开镜像发布、远程部署或真实发送。不组织多代理，不改D盘、旧Ubuntu或全局WSL。当前规格/设计/决策/状态及合并记录为新分支文档变更，提交后以git status核对，不因文档SHA变化重做产品验证。

## 已合并修复与验证

[PR #1](https://github.com/Aspeternity/seekbell/pull/1)已合并，head b3d1c8b；[合并与CI记录](history/2026-10-23-本地修复合并与热榜分支.md)。包含单一正式前端、统一日期/筛选/卡片导航、发布与发现时间、查询快照、共享下拉和200ms反馈、通知冷进入预读及菜单宽度补修。合并树与通过检查的PR head完全一致。

GitHub ubuntu-latest，b3d1c8b：[PR完整基线](https://github.com/Aspeternity/seekbell/actions/runs/39929832505)通过；[push完整基线及amd64/arm64原生镜像](https://github.com/Aspeternity/seekbell/actions/runs/39929788044)均通过，含后端/浏览器、迁移、构建、容器、加密备份恢复、卷切换回退及TLS。未发布镜像。本地58bee30的82项及b009317后端669项证据继续适用，见[补修记录](history/2026-10-23-通知冷进入与下拉宽度补修.md)。Safari/真机/读屏和用户验收仍独立待完成。

## 本地实例

http://localhost:8001/，同一seekbell-local/seekbell-local-seekbell-1和seekbell-local_data；镜像seekbell:local-58bee30ff55a，digest sha256:5886d4f1b9e1d6de5c922ca0bf9af8141099eee3f6a72e594f80daf58f364202。本轮未更新实例，原账号/配置/历史保留。备份local-runtime/backups/before-58bee30ff55a.tar.gz，回退6ee4af9；[管理命令](history/2026-10-23-最新代码本地Docker实测启动.md)。旧18080/18081已退役；公开仍ui-restore-5，远程Stack及8000/4175未动。

## 社区热榜与下一步

权威需求见SPEC 6.1，UI_DESIGN及ARCHITECTURE对应待实现章节。[调研证据](history/2026-10-23-概览模块与热榜方案调研.md)：三模块显隐/纵向排序/服务端保存/恢复默认，上方统计固定；热榜网站＋周期切换、按网站记忆。首接NodeSeek第三方实时/每日/每周；未来Linux DO/V2EX按能力扩展，本阶段不采集。三个接口单次HTTP200、30/50/100条，算法/窗口/长期可用性未核实；不拿RSS最新冒充热榜。独立缓存和失败旧快照，不进规则/命中/通知。示意320/736px检查通过，聊天内嵌错误未确认恢复，截图后备，不是产品验收。

下一步在当前分支先实现布局偏好与迁移，再接独立热榜适配/缓存/API/UI，并用合成数据作针对性验证；没有热榜产品代码或部署成果。恢复读本状态、SPEC 6.1、相关架构/UI章节及调研/合并记录；无技术阻塞。
