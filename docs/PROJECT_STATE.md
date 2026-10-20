# 当前状态

更新时间：2026-10-21（Asia/Shanghai）。M0～M3实现及本地自动退出已完成；当前M4部署恢复，原生双架构CI与产物往返已通过。GHCR实际发布及M5实机/用户验收未完成。[本次证据](history/2026-10-21-远程CI与原生双架构验证.md)，[镜像流程](IMAGE_RELEASE.md)。

## 环境与代码

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发。[入口](DEVELOPMENT_ENVIRONMENT.md)。分支codex/frontend-backend-integration；已验证实现提交34cf1830291240f09071bbb4fb343be3aba4b642已推送，后续仅文档收尾。产品代码仍等同faa991d，本轮改CI/测试设施/文档，无新业务/依赖/迁移。原D盘、Ubuntu工具与全局WSL未改。

## 本阶段与证据

native-images只读复用工作流由开发分支push的完整CI及手动images流程调用，支持合并前原生双架构验证；默认不发布。手动入口未进入main，不能假定可直接派发。GHCR仍需单独授权、仓库开关、手动选择、默认分支和全部检查成功；仅独立发布job有packages写权限，不部署。

已修两处真实CI问题：原型改为根目录正向收集，避免误跑backup/proxy；TLS fixture先由Docker选可用池再显式声明internal子网，兼容静态IP，不改全局网络。失败日志、排除路线及本机40项原型/26项代理/2项HTTPS证据见本次记录。

[远程CI 39463442124](https://github.com/Aspeternity/seekbell/actions/runs/39463442124)整体success：后端473项184.52秒、浏览器64项、格式/锁/隐私/构建/迁移/容器重启、备份恢复/升级回退/真实TLS通过。ubuntu-24.04 amd64和ubuntu-24.04-arm均原生构建/服务/备份升级/TLS/归档全过，无QEMU。产物下载后ZIP及归档校验、两平台版本/配置/层及本机加载预检通过，published=false。

本机保留seekbell:ci-34cf183-amd64（image ID 8ffd0690...）和-arm64（62fc22b9...）；完整ID、配置digest、归档/ZIP SHA及artifact ID见证据。CI classic ID与本机containerd ID不同已实际验证；这些不是GHCR发布digest。临时归档/容器清理，无真实发送。

## 用户验收实例

保留项目seekbell-acceptance-b45fc2c-20261020、容器后缀-seekbell-1、卷后缀_data，seekbell:backup-local（b45fc2c），http://localhost:18081/。最终只读running/重启计数0，未替换/重置/代配置。旧seekbell-acceptance不兼容卷保留、容器已停，勿复用旧名/改迁移号；旧4175/18080未动。[故障记录](history/2026-10-20-本机验收启动修复.md)。

## 下一步与恢复

无开发阻塞。下一步审阅本次证据，经授权处理main合并及GHCR候选发布，先核对包权限/可见性并取得真实registry digest；再进入M5授权PVE、真实RSS/四渠道、Safari/真机、运行观察和用户验收，确认后正式发布。[阶段顺序](ROADMAP.md)。目标环境/域名证书、GHCR实际写入、跨版本加密恢复未验证；原生CI不等同用户设备验收。恢复/回退可能重复发送，保留原卷，不直接降级新库。

恢复读AGENTS、本状态、IMAGE_RELEASE及本次证据；按需读三个workflow、proxy_fixture/专项、RELEASES/PROXY_DEPLOYMENT，不全仓重读。仅Markdown收尾标注skip ci，复用34cf183代码证据，不宣称文档HEAD重跑过CI，不为写自身SHA循环提交。

## 授权

本轮用户在明确下一步为推送/CI后要求继续，已执行开发分支普通推送和无发布远程CI。沿用独立WSL/noreply；无main合并、GHCR写入、远程部署、真实发送/公开发布、原环境清理/全局WSL变更授权。不组织多代理；保留用户验收实例及配置。
