# 当前状态

更新时间：2026-10-20（Asia/Shanghai）。M1/M2、M3本地自动退出已完成；M4第一子阶段Compose/停服加密备份/独立恢复已验证，当前开发第二子阶段网页下载与上传恢复候选。整体M4、真实服务和用户验收未完成。[此前状态](history/2026-10-20-网页备份开发前状态.md)、[M4第一阶段](history/2026-10-20-Compose与加密备份恢复.md)。

## 环境与基准

只在SeekBell-Dev的/home/dev/projects/seekbell开发，原Ubuntu显式wsl.exe派发。[环境入口](DEVELOPMENT_ENVIRONMENT.md)。分支codex/frontend-backend-integration，起点HEAD d26f78e6738aff0055c88ebd6032503b6e98c88a，初始干净；比旧状态多一次交接文档提交，产品基准仍b45fc2c。原D盘、原WSL和全局设置未改。

## 当前交付与证据

M4第二子阶段已实现，待本地提交及镜像验证：[阶段证据](history/2026-10-20-网页加密备份与独立恢复.md)。网页在持有实例锁的应用进程内做一致快照，后台继续运行；CLI仍要求停服。会话/CSRF/同源/当前密码再验证、限速、单操作门禁、私有暂存和清理；上传元数据8KiB/数据库2GiB/300秒。只恢复到data_dir/web-restore固定新候选，验证备份管理员/原钥/版本并撤销副本会话，不覆盖/切换/启动副本，无跨版本或新迁移/依赖。

独立WSL自动证据：初版31+18共49项；全量393项104.99秒；最后仅补中断/清理边界，网页21项17.79秒通过。桌面/手机备份2项10秒及相关生产页面20项通过；Ruff/锁/wheel/前端类型构建格式/隐私noreply通过。镜像/Compose固定提交复验待补，远程CI未跑。[维护命令与边界](BACKUP_RESTORE.md)。

未提交路径：backend的backup/api/backups/main；frontend的BackupSettings/Settings/store及帮助、专项/相关测试、配置/package/ignore；scripts运行与Compose检查、CI及本阶段文档。均为本次实现与证据，不含数据、密钥或浏览器产物。

## 保留的验收实例

用户验收实例seekbell-acceptance-b45fc2c-20261020，容器后缀-seekbell-1、新卷后缀_data；镜像seekbell:backup-local（b45fc2c），127.0.0.1:18081，http://localhost:18081/。本次只读确认healthy，不升级/重置/替用户操作。原seekbell-acceptance旧卷迁移号不兼容，旧容器已停止、旧卷保留；不要复用旧项目名或改迁移号。旧4175/18080未动。[故障证据](history/2026-10-20-本机验收启动修复.md)。

## 下一步与读取

完成本地提交与固定镜像禁外网核对；之后才补原卷切换、升级/失败回退。独立恢复副本不是恢复已生效；启用副本前必须停原实例，时间点恢复可能重复发送。真实RSS/通知、反代/PVE/arm64/Safari/真机与用户验收仍待完成。

恢复先读本状态、AGENTS、BACKUP_RESTORE、ARCHITECTURE的备份节；按影响读backup/api/backups/main及对应测试；无需重读全仓。

## 授权

沿用本地开发、独立WSL、GitHub noreply；本次用户要求下一阶段开发。不推送/合并main、不组织多代理；不执行真实RSS/通知、远程部署/公开发布、原环境清理或全局WSL变更。当前验收实例及用户后续配置必须保留。
