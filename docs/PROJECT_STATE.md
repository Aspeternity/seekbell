# 当前状态

更新时间：2026-10-21（Asia/Shanghai）。M0～M3实现与本地自动检查已完成；M4工程自动退出通过，当前进入M5实机/用户验收准备。[阶段顺序](ROADMAP.md)，[本轮证据](history/2026-10-21-主分支合并与GHCR候选发布.md)。未部署或真实发送。

## 环境与代码

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。main已普通合并/推送，代码基准d55ee70be475029b11dc5ce30c6cf340c889c349，开发分支cb3de42保留。产品代码仍等同faa991d，近期仅CI/发布/测试/文档，无业务/依赖/迁移变更。原D盘副本、Ubuntu工具与全局WSL未改。当前仅本轮状态、阶段/架构/验收/镜像说明和history回执收尾，随文档提交；无待提交实现。

## M4结果与边界

[39485766557](https://github.com/Aspeternity/seekbell/actions/runs/39485766557)对d55ee70整体success：后端496项195.78秒、浏览器64项；构建/迁移/容器重启/锁、加密备份独立恢复、新卷升级/失败回退、真实TLS通过。amd64与arm64各原生构建/演练/归档，无QEMU；复用已测产物发布私有GHCR，确认两个子manifest/config及索引、写后private和按digest拉取amd64禁外网复验成功。

固定引用：`ghcr.io/aspeternity/seekbell@sha256:afab58706a30d2b01617f600ab36d09f82f427470a9e4e6bf2bc6f995470dbd4`。两平台指纹、已下载且ZIP SHA匹配的回执见[长期JSON](history/2026-10-21-GHCR-release-receipt.json)；工作流artifact仅30天。[命令与限制](IMAGE_RELEASE.md)。

首轮39482339606实际写入后误判失败，其aabfe5e2...索引保留。已确认官方API repository可选/可空；现缺失记not-reported，明确报告错配仍拒绝，private/source/config独立验证，不声称UI关联已证明。临时诊断已禁用/删除，发布开关已恢复原先缺失并GET核对；不改包可见性/权限。此前原型误收集、Docker隐式IPAM根因见[CI记录](history/2026-10-21-远程CI与原生双架构验证.md)，无需重复排查。

## 验收实例与下一步

保留seekbell-acceptance-b45fc2c-20261020项目、-seekbell-1容器、_data卷与seekbell:backup-local（b45fc2c），http://localhost:18081/；最近只读running/重启0，未替换/重置/代配置。旧不兼容卷及4175/18080保留，勿复用旧名/改迁移号。[故障说明](history/2026-10-20-本机验收启动修复.md)。两平台ci-34cf183本机候选保留，ID见归档。

下一步取得目标PVE信息与部署/真实发送授权，按实机矩阵执行固定digest部署、实际域名证书、真实RSS/四渠道、Safari/真机、重启/恢复、运行观察和用户验收，用户确认后正式发布。以上均未执行；跨版本加密恢复仍未验证。原生CI不替代用户设备验收，回退可能重复发送，保留原卷、不降级新库。

## 恢复与授权

恢复读AGENTS、本状态及本轮证据；部署任务按需读DEVELOPMENT_ENVIRONMENT、IMAGE_RELEASE、PROXY_DEPLOYMENT、RELEASES、ACCEPTANCE。不全仓重读。文档收尾标skip ci，复用d55ee70代码证据，不声称文档HEAD已重跑或循环写自身SHA。

用户2026-10-21明确授权main合并/私有GHCR发布及临时开关恢复，已完成；沿用独立WSL/noreply。无远程部署、真实发送、仓库/包公开、正式GitHub Release、旧环境清理或全局WSL变更授权。不组织多代理，保留验收实例。
