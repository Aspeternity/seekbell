# 当前状态

更新时间：2026-10-20（Asia/Shanghai）。M1/M2、M3本地自动退出已完成；M4第二子阶段网页加密下载/上传生成独立恢复副本已完成本地自动验证，整体M4和真实服务/用户验收仍未完成。[本阶段证据](history/2026-10-20-网页加密备份与独立恢复.md)，[前阶段状态](history/2026-10-20-网页备份开发前状态.md)。

## 环境与代码

只在SeekBell-Dev的/home/dev/projects/seekbell开发，原Ubuntu显式经wsl.exe执行。[环境入口](DEVELOPMENT_ENVIRONMENT.md)。分支codex/frontend-backend-integration；实现提交69668ada946a2504af4b5ecb3ac683219ef3ea45，其后仅验证文档，无未提交产品改动。原D盘/WSL及全局配置未改。

## 本阶段与证据

网页在持有实例锁的进程内做SQLite一致快照，后台继续运行；CLI仍须停服。管理员会话/CSRF/同源/当前密码再验证、限速和单操作门禁；私有暂存、取消join线程再清理。上传清单8KiB/数据库2GiB/300秒。复用原加密格式与全量验证，只发布固定data_dir/web-restore新候选，撤销副本旧会话；不覆盖/切换/启动副本，不接收路径，无新依赖/迁移。已有候选拒绝覆盖，状态可刷新；大库浏览器Blob内存占用较高，建议CLI。[命令及边界](BACKUP_RESTORE.md)。

独立WSL证据：全量393项104.99秒；最后仅补中断/清理边界，网页21项17.79秒通过（含新增3项，非再次全量）。桌面/手机备份2项10秒、相关生产页面20项通过；未改模拟原型行为，复用原证据。Ruff/锁/wheel/前端类型构建格式/隐私noreply通过，远程CI未跑。

本地Rootless/amd64镜像seekbell:web-backup-local，代码69668ad，image ID sha256:08603d00e3c86512e13fdd785bc62ba1582bff526104ebc93055d9f790463b0a，未发布。通用打包/重启/锁/资源与禁外网Compose已通过；后者验证网页往返、原库/原钥/队列保持、副本会话撤销、运行中CLI拒绝、停服备份/恢复和恢复实例重登；仅清理本轮资源。

## 用户验收实例保留

项目seekbell-acceptance-b45fc2c-20261020，容器后缀-seekbell-1、新卷后缀_data；镜像seekbell:backup-local（旧代码b45fc2c），http://localhost:18081/。本次只读核对healthy、重启0，未升级/重置/替用户操作。旧seekbell-acceptance卷迁移号不兼容，旧容器已停、卷保留；勿复用旧项目名或改迁移号。旧4175/18080未动。[启动故障](history/2026-10-20-本机验收启动修复.md)。

## 下一步与读取

下一子阶段为保留原卷的正式切换、升级/失败回退，无开发阻塞。独立候选不等于当前恢复生效；启用前必须停原实例，时间点恢复可能重复发送。跨版本、PVE/arm64/实际反代/Safari/真机、真实RSS/通知及用户验收仍待完成。

恢复读AGENTS、本状态、BACKUP_RESTORE及ARCHITECTURE备份节，再按需读backup/api/backups/main和专项测试，无需全仓重读。

## 授权

本次用户要求下一阶段开发；沿用本地开发/独立WSL/noreply。不推送/合并main、不组织多代理；不运行真实RSS/通知、不远程部署/公开发布、不清理原环境或改全局WSL。当前验收实例和用户后续配置必须保留。
