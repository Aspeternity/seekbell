# 当前状态

更新时间：2026-10-20（Asia/Shanghai，反代HTTPS开发中）。M1/M2、M3本地自动退出完成；M4第三子阶段保留原卷的切换/升级/显式回退已实现并通过禁外网镜像演练，整体M4及真实环境/用户验收未完成。[本阶段证据](history/2026-10-20-保留原卷切换与升级回退.md)，[前阶段](history/2026-10-20-切换开发前状态.md)。

## 环境与代码

唯一开发环境SeekBell-Dev、/home/dev/projects/seekbell，原Ubuntu显式wsl.exe派发。[入口](DEVELOPMENT_ENVIRONMENT.md)。分支codex/frontend-backend-integration，实现01f4bd6、原卷只读WAL修复f58e5f24b86883fcd3bf35c4eebac4b3775a2e92；其后仅本阶段验证文档，无未提交产品改动。原D盘/Ubuntu工具和全局WSL未改。

## 本阶段与证据

宿主机scripts/manage_release.py提供prepare/status/activate/rollback，Web无Docker权限。准备前须停服；原卷只读挂载并持同一实例锁，DB+WAL私有物化后由SQLite生成一致快照；不裸复制单DB或immutable忽略WAL。仅新卷迁移/校验原钥/清副本会话/原子发布，源与候选摘要及构建/迁移/原启动时刻再核对，固定image ID/卷/data_dir成对切换。--restored把web-restore转入新卷，原卷保留。状态0700/0600原子更新、本地单用户项目锁；启动失败停新服务不自动回退，rollback须明确accept-data-loss，不downgrade新库/不合并。无新依赖/产品迁移。[真实命令与边界](RELEASES.md)。

最终代码f58e5f2在SeekBell-Dev全量413项104.66秒通过，切换专项17项5.25秒通过（含WAL修复）。前端类型/构建/格式及备份桌面手机2项8.9秒通过；其余UI不变复用原证据。Ruff/锁/wheel/隐私noreply通过，远程CI未跑。

本地Rootless/amd64镜像seekbell:release-local，代码f58e5f2，image ID sha256:bcc185ab9a19c3dc185068e25fd4e01ff5b764d138bebab960b6cd9849fc6511，未发布。禁外网演练验证合成未来迁移成功/事务失败、启动失败停止不自动回退、原卷字节/原钥不变、显式原版本对回退及网页副本切换；通用打包/健康/资源/锁/重启/配置和离线Runtime也通过。本轮临时资源已清理，非任意未来版本兼容证明。

## 原验收实例保留

项目seekbell-acceptance-b45fc2c-20261020，容器后缀-seekbell-1、卷后缀_data，镜像seekbell:backup-local（b45fc2c），http://localhost:18081/。本次只读确认healthy/重启计数0，无替换/重置/代用户操作。旧seekbell-acceptance不兼容卷保留且旧容器停止；勿复用旧项目名、改迁移号或覆盖试验。旧4175/18080未动。[故障记录](history/2026-10-20-本机验收启动修复.md)。

## 本次进行中

用户要求下一步开发并解释阶段。当前仍M4，M0～M3实现/本地自动验证已交付，M5实机与用户验收未开始。未提交：Settings精确可信代理IP/ASGI代理中间件、默认关闭访问日志、Compose反代覆盖及发布工具保留代理设置；外部Nginx示例、只读部署检查CLI、真实TLS隔离演练/桌面手机用例及相关CI/文档待补。无新产品依赖/迁移。官方Nginx1.30.6-alpine已拉取并记录digest，只作独立反代测试依赖，不改应用单容器技术栈；无本机系统安装或信任库变更。

代理/认证/回退相关54项16.20秒、新代理专项20项1.14秒，以及本次代码全量433项108.70秒通过；Ruff/锁/wheel/前端类型构建格式/隐私noreply通过。真实TLS固定镜像/浏览器及代理配置切换保留演练尚待完成，不宣称此子阶段完成。后续完成本地反代/部署检查，M4仍有GHCR/双架构流程及部署核对，再进入M5的PVE实机/真实RSS/四渠道/真机页面/观察与用户验收，用户确认才发布。恢复读AGENTS、本状态、ARCHITECTURE认证/部署节、RELEASES及新增代理/检查代码，不全仓重读。

## 授权

用户要求继续下一步本地开发；沿用独立WSL/noreply。不推送/合并main、不组织多代理，不执行真实发送/远程部署/公开发布/原环境清理/全局WSL变更。用户验收实例及之后配置必须保留。
