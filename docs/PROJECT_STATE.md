# 当前状态

更新时间：2026-10-21（Asia/Shanghai）。M0～M3实现/本地自动检查完成，M4工程退出通过；当前M5由用户在Portainer自行部署验收，反馈RSS测试间隔问题。Codex未操作用户部署或真实采集/发送。[阶段顺序](ROADMAP.md)。

## 环境与代码

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。当前codex/rss-connection-independent，实现10cf4e7f05cd12c1e8321985af1d80b83c4ea672；本轮收尾仅README、状态/证据随文档提交，代码不变。分支未推送/合并main，main/origin仍fc8f95b，旧开发分支cb3de42保留。原D盘/Ubuntu工具与全局WSL未改。

## 当前修复与证据

截图网站启用/10秒间隔，测试一直被本地429拦截；用户概览05:06最后尝试、连续失败0、下次05:06，尚缺完整版本/最近成功时间。旧测试与正常采集共用到期窗口，容易长期被后台抢先，不能据此判为远端限流。

用户进一步明确要求测试独立于正常采集间隔，刚采集完也应立即测试，已回写SPEC/架构。最终实现独立2秒防连点：成功采集不阻塞测试，成功测试不延后后台；仅共享在途互斥与实际错误退避。兼容旧成功probe长计时，不改正式健康/基线/历史/账本，无依赖/迁移。预约等待方案已从代码移除，其未发布证据只归档。

新契约先在旧方案取得7失败/1通过19.90秒；新实现针对性46项17.77秒、全量后端514项117.02秒、前端类型/构建及桌面/手机操作浏览器2项8.4秒通过。Ruff全仓/171文件格式通过。10cf4e7本机amd64镜像seekbell:rss-probe-independent-local（ID e4938963...）禁外网服务/重启/持久化/锁及合成Runtime通过。[完整证据和复验命令](history/2026-10-21-RSS测试独立限频.md)。旧d167356/513项证据不替代新实现检查。尚未远程CI/原生arm64/发布或用户环境验证。

## 既有镜像与实例

现有公开镜像代码d55ee70，固定引用`ghcr.io/aspeternity/seekbell@sha256:afab58706a30d2b01617f600ab36d09f82f427470a9e4e6bf2bc6f995470dbd4`，不含新修复。[39485766557](https://github.com/Aspeternity/seekbell/actions/runs/39485766557)496后端/64浏览器、原生双架构及digest拉取通过；[回执](history/2026-10-21-GHCR-release-receipt.json)。用户亲自改Public，空凭据匿名拉取/双平台索引验证通过，源码仍private，[公开记录](history/2026-10-21-GHCR公开与匿名拉取.md)。main发布检查显式public，67专项通过；开关恢复缺失。首轮部分发布/可选repository字段、原型/IPAM失败根因见历史，不重复诊断。

保留本机18081项目seekbell-acceptance-b45fc2c-20261020、-seekbell-1容器、_data卷和backup-local镜像；最近running/重启0，勿替换/重置。旧不兼容卷、4175/18080、ci-34cf183及旧本地候选保留，完整ID见归档。

## 下一步与授权

新修复合并/公开镜像发布授权仍待答复；获授权后按精确SHA完整CI/两架构、公开元数据/索引/匿名拉取检查，再由用户更新Portainer。真实RSS/四渠道、HTTPS/Safari/真机、运行观察及完整用户验收待反馈；跨版本加密恢复未验证。回退可能重复发送，保留原卷、不降级新库。

此前单次main合并/GHCR发布及镜像公开授权均已完成，非永久发布授权。无本轮新镜像公开发布、远程部署、真实发送、源码公开、正式Release或旧环境/全局WSL变更授权。不组织多代理。恢复读AGENTS、本状态和独立限频记录；发布时再读IMAGE_RELEASE/相关workflow。仅文档收尾skip ci复用10cf4e7，不循环写自身SHA。
