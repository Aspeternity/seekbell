# 当前状态

更新时间：2026-10-20（Asia/Shanghai）。M1/M2、M3本地自动退出完成；M4第三子阶段保留原卷的切换/升级/显式回退已实现并通过禁外网镜像演练，整体M4及真实环境/用户验收未完成。[本阶段证据](history/2026-10-20-保留原卷切换与升级回退.md)，[前阶段](history/2026-10-20-切换开发前状态.md)。

## 环境与代码

唯一开发环境SeekBell-Dev、/home/dev/projects/seekbell，原Ubuntu显式wsl.exe派发。[入口](DEVELOPMENT_ENVIRONMENT.md)。分支codex/frontend-backend-integration，实现01f4bd6、原卷只读WAL修复f58e5f24b86883fcd3bf35c4eebac4b3775a2e92；其后仅本阶段验证文档，无未提交产品改动。原D盘/Ubuntu工具和全局WSL未改。

## 本阶段与证据

宿主机scripts/manage_release.py提供prepare/status/activate/rollback，Web无Docker权限。准备前须停服；原卷只读挂载并持同一实例锁，DB+WAL私有物化后由SQLite生成一致快照；不裸复制单DB或immutable忽略WAL。仅新卷迁移/校验原钥/清副本会话/原子发布，源与候选摘要及构建/迁移/原启动时刻再核对，固定image ID/卷/data_dir成对切换。--restored把web-restore转入新卷，原卷保留。状态0700/0600原子更新、本地单用户项目锁；启动失败停新服务不自动回退，rollback须明确accept-data-loss，不downgrade新库/不合并。无新依赖/产品迁移。[真实命令与边界](RELEASES.md)。

最终代码f58e5f2在SeekBell-Dev全量413项104.66秒通过，切换专项17项5.25秒通过（含WAL修复）。前端类型/构建/格式及备份桌面手机2项8.9秒通过；其余UI不变复用原证据。Ruff/锁/wheel/隐私noreply通过，远程CI未跑。

本地Rootless/amd64镜像seekbell:release-local，代码f58e5f2，image ID sha256:bcc185ab9a19c3dc185068e25fd4e01ff5b764d138bebab960b6cd9849fc6511，未发布。禁外网演练验证合成未来迁移成功/事务失败、启动失败停止不自动回退、原卷字节/原钥不变、显式原版本对回退及网页副本切换；通用打包/健康/资源/锁/重启/配置和离线Runtime也通过。本轮临时资源已清理，非任意未来版本兼容证明。

## 原验收实例保留

项目seekbell-acceptance-b45fc2c-20261020，容器后缀-seekbell-1、卷后缀_data，镜像seekbell:backup-local（b45fc2c），http://localhost:18081/。本次只读确认healthy/重启计数0，无替换/重置/代用户操作。旧seekbell-acceptance不兼容卷保留且旧容器停止；勿复用旧项目名、改迁移号或覆盖试验。旧4175/18080未动。[故障记录](history/2026-10-20-本机验收启动修复.md)。

## 下一步与恢复

下一本地子阶段补反代HTTPS配置与部署检查，无开发阻塞。GHCR/双架构、实际反代/PVE/arm64/Safari/真机、跨版本加密恢复、真实RSS/通知及用户验收待完成。本地P02/P03已有证据不等于实机验收。启用副本会按原配置处理队列，回退丢失之后回执可能重复发送。

恢复读AGENTS、本状态、RELEASES；按需读BACKUP_RESTORE/ARCHITECTURE备份节及release/维护脚本和专项测试，不全仓重读。

## 授权

用户要求继续下一步本地开发；沿用独立WSL/noreply。不推送/合并main、不组织多代理，不执行真实发送/远程部署/公开发布/原环境清理/全局WSL变更。用户验收实例及之后配置必须保留。
