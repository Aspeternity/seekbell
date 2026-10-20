# 当前状态

更新时间：2026-10-21（Asia/Shanghai）。M0～M3实现与本地自动检查完成，M4工程退出通过；当前M5由用户在Portainer自行部署验收，反馈RSS测试间隔问题。Codex未操作用户部署或真实采集/发送。[阶段顺序](ROADMAP.md)。

## 环境与代码

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。当前分支codex/rss-connection-wait，实现d167356d296a1fa729d9e4c1655093d99e5d3af9，本轮仅文档收尾随状态提交；分支未推送/合并main。main/origin仍fc8f95b（公开包校验），旧开发分支cb3de42保留。原D盘/Ubuntu工具及全局WSL未改。

## 当前修复与证据

用户截图启用网站/10秒间隔，测试一直被429拦截；概览最后尝试05:06、连续失败0、下次05:06，尚缺完整版本/最近成功时间。代码确认手动测试与自动采集共享到期窗口，后台可持续抢先；笼统错误又隐藏原因/剩余时间，不能据此判为远端限流。

已修启用网站距到期≤10秒时持来源锁异步等一次，到期重新核对安装/间隔/退避再请求；长等待回显秒数及固定故障码，不提前请求。等待不持DB事务、取消释放锁；测试不改正式健康/基线/账本。前端显示等待状态，无依赖/迁移。

原实现先复现3失败/2通过；修复针对性45项17.48秒、全量后端513项116.89秒、前端类型/构建和桌面/手机操作浏览器2项13.3秒通过。Ruff全仓通过；d167356本机amd64镜像seekbell:rss-probe-local（ID db263a7a...）禁外网服务/重启/持久化/锁及合成Runtime通过。[完整证据](history/2026-10-21-RSS连接测试等待修复.md)。新修复未远程CI/原生arm64/发布或用户环境验证，不能声称旧镜像已更新。

## 既有镜像与验收实例

现有公开镜像代码d55ee70，固定引用`ghcr.io/aspeternity/seekbell@sha256:afab58706a30d2b01617f600ab36d09f82f427470a9e4e6bf2bc6f995470dbd4`。首次完整发布[39485766557](https://github.com/Aspeternity/seekbell/actions/runs/39485766557)496后端/64浏览器、原生双架构及digest拉取通过；[回执](history/2026-10-21-GHCR-release-receipt.json)。用户随后亲自改Public，空凭据匿名拉取/双平台索引验证通过、源码仍private，[记录](history/2026-10-21-GHCR公开与匿名拉取.md)。main的三处发布检查显式public，67项专项通过；开关已恢复缺失。

首轮aabfe5e2...部分发布保留；repository元数据可选/可空，缺失记not-reported，错配拒绝，见历史，不重复诊断。原型误收集/IPAM根因见远程CI归档。

保留18081本机验收项目seekbell-acceptance-b45fc2c-20261020、-seekbell-1容器、_data卷、backup-local镜像；最近running/重启0，勿替换/重置。旧不兼容卷及4175/18080保留；ci-34cf183候选亦保留，完整ID见归档。

## 下一步与授权

待本轮新修复合并/公开镜像发布授权后跑精确SHA完整CI/两架构及公开/匿名拉取检查，再由用户更新Portainer验收。真实RSS/四渠道、HTTPS/Safari/真机、运行观察及完整用户验收仍待反馈；跨版本加密恢复未验证。回退可能重复发送，保留原卷、不降级新库。

此前用户已授权单次main合并/GHCR发布及镜像公开，均完成；非永久发布授权。无本轮新镜像公开发布、远程部署、真实发送、源码公开、正式Release或旧环境/全局WSL变更授权。不组织多代理。恢复读AGENTS、本状态和RSS修复记录，发布时再读IMAGE_RELEASE及相关workflow；文档收尾skip ci复用d167356，不循环写自身SHA。
