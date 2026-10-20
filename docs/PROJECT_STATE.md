# 当前状态

更新时间：2026-10-20（Asia/Shanghai，原卷切换开发中）。M1/M2、M3本地自动退出已完成；M4第二子阶段网页加密下载/上传生成独立恢复副本已完成本地自动验证，整体M4和真实服务/用户验收仍未完成。[本阶段证据](history/2026-10-20-网页加密备份与独立恢复.md)，[前阶段状态](history/2026-10-20-网页备份开发前状态.md)。

## 环境与代码

只在SeekBell-Dev的/home/dev/projects/seekbell开发，原Ubuntu显式经wsl.exe执行。[环境入口](DEVELOPMENT_ENVIRONMENT.md)。分支codex/frontend-backend-integration；实现提交69668ada946a2504af4b5ecb3ac683219ef3ea45，其后仅验证文档，无未提交产品改动。原D盘/WSL及全局配置未改。

## 本阶段与证据

网页在持有实例锁的进程内做SQLite一致快照，后台继续运行；CLI仍须停服。管理员会话/CSRF/同源/当前密码再验证、限速和单操作门禁；私有暂存、取消join线程再清理。上传清单8KiB/数据库2GiB/300秒。复用原加密格式与全量验证，只发布固定data_dir/web-restore新候选，撤销副本旧会话；不覆盖/切换/启动副本，不接收路径，无新依赖/迁移。已有候选拒绝覆盖，状态可刷新；大库浏览器Blob内存占用较高，建议CLI。[命令及边界](BACKUP_RESTORE.md)。

独立WSL证据：全量393项104.99秒；最后仅补中断/清理边界，网页21项17.79秒通过（含新增3项，非再次全量）。桌面/手机备份2项10秒、相关生产页面20项通过；未改模拟原型行为，复用原证据。Ruff/锁/wheel/前端类型构建格式/隐私noreply通过，远程CI未跑。

本地Rootless/amd64镜像seekbell:web-backup-local，代码69668ad，image ID sha256:08603d00e3c86512e13fdd785bc62ba1582bff526104ebc93055d9f790463b0a，未发布。通用打包/重启/锁/资源与禁外网Compose已通过；后者验证网页往返、原库/原钥/队列保持、副本会话撤销、运行中CLI拒绝、停服备份/恢复和恢复实例重登；仅清理本轮资源。

## 用户验收实例保留

项目seekbell-acceptance-b45fc2c-20261020，容器后缀-seekbell-1、新卷后缀_data；镜像seekbell:backup-local（旧代码b45fc2c），http://localhost:18081/。本次只读核对healthy、重启0，未升级/重置/替用户操作。旧seekbell-acceptance卷迁移号不兼容，旧容器已停、卷保留；勿复用旧项目名或改迁移号。旧4175/18080未动。[启动故障](history/2026-10-20-本机验收启动修复.md)。

## 本次进行中与下一步

用户要求继续原卷切换与升级失败回退。未提交：backend/release.py离线原卷只读锁/一致快照、新卷迁移/原钥校验/清副本会话/原子发布、来源和候选校验；backup.py提取公共SQLite快照；scripts/manage_release.py宿主机维护CLI、compose.release及离线覆盖、tests/test_release.py、check_release_container.py/CI、维护文档和相应界面说明；.dockerignore补排除浏览器产物。不向网页授予Docker权限；准备须先停服，新卷独立、原卷保留；激活固定镜像与卷对，健康失败停新服务、不自动回退；明确回退需接受切换后的数据丢失。本次未提交代码全量411项104.79秒通过，切换专项15项4.55秒通过；网页备份复验2项9.2秒通过。Ruff/锁/wheel/隐私noreply通过；固定提交镜像及禁外网真实Compose演练待完成，尚未宣布本阶段通过。

后续完成测试、维护命令和交接后本地提交。跨版本备份恢复、PVE/arm64/实际反代/Safari/真机、真实RSS/通知及用户验收仍待完成。恢复读AGENTS、本状态、BACKUP_RESTORE和ARCHITECTURE备份节，再读release/维护脚本及测试；无需全仓重读。

## 授权

本次用户要求下一步开发；沿用本地开发/独立WSL/noreply。不推送/合并main、不组织多代理；不运行真实RSS/通知、不远程部署/公开发布、不清理原环境或改全局WSL。当前验收实例和用户后续配置必须保留。
