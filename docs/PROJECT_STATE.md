# 当前状态

更新时间：2026-10-19 07:11（Asia/Shanghai）。M1/M2及M3核心六页已实现、自动验证，尚未用户验收；M4本地部署恢复实现已提交推送a8dc7e4，正在打包演练，未宣称阶段验收。

## 环境与代码

仅WSL2 SeekBell-Dev的/home/dev/projects/seekbell开发；当前聊天从原Ubuntu经wsl.exe显式派发。main及origin/main恢复入口为ac79c9f（仅交接文档）；此前实现基准ee97cb9。进入时工作区干净，代码未失配。[环境入口](DEVELOPMENT_ENVIRONMENT.md)。私有origin Aspeternity/seekbell，noreply及.githooks检查沿用。

已提交实现：backend/seekbell/backup.py、db/runtime.py、tests/test_backup.py为加密备份/恢复及中断保护；deploy/为Compose/环境/反代示例，scripts/check_m4_container.py及ci.yml增加隔离恢复演练，image.yml提供仅main手动、默认不发布的双架构工作流；SettingsPanel.vue仅修改维护说明；README/ARCHITECTURE/DEPLOYMENT及本状态、.gitignore同步。无正式数据或凭据。

## 实现与证据

M4停服实例锁内SQLite一致性快照，含原密钥、全部账号/规则/历史/去重/队列，以独立口令scrypt+AES-GCM流式认证加密；检查密文快照，拒绝覆盖归档。恢复验证备份管理员密码，只写空目录，暂存迁移及校验后安装，撤销会话。全过程持久中断标记；SIGKILL残留阻止服务误初始化。Compose默认测试项目、回环端口、后台关闭、UID10001、只读根FS与日志轮换。操作命令见[部署恢复手册](DEPLOYMENT.md)。

SeekBell-Dev实现a8dc7e4：新增18项备份测试及11项基础/锁测试共29项通过（8.68秒），含WAL、0006→0007、损坏归档/错钥/路径拒绝、失败重试及真实子进程SIGKILL；Ruff、前端类型/构建、wheel、隐私身份通过。前端仅文案，复用M3浏览器证据；未重跑369项旧套件。固定SHA镜像a8dc7e4构建并Compose禁外网演练通过：UID10001/只读根FS、停服锁、账号/规则/原密钥恢复、旧会话失效、未知迁移版本安全停止及升级前备份回退。首轮脚本敏感字段断言遗漏Bark base_url，已按schema修正，应用实现未变。脚本修正和证据文档待提交；CI最终结果待补。

前阶段完整pytest369、Chromium7及固定镜像/CI39173808999全部成功，均临时数据和模拟服务；细节见[系统设置记录](history/2026-10-19-M3系统设置.md)，通知及更早记录按链接读取。不是用户验收。

## 下一步与读取清单

先完成M4镜像演练，记录SHA/镜像ID与结果；有代码修正只补相关检查。之后统一安排用户验收材料，不自动运行真实RSS/四渠道，不部署。PVE、原生arm64、真实反代及通知接收均未验证；客户端弃用提示、Rootless无cgroup限额仍在。

本任务读取：ROADMAP M4、ARCHITECTURE备份/部署、DEPLOYMENT、受影响backup/db/凭据与容器检查代码。无需重读全仓或重复旧验证。尚无运行中的正式实例；本机旧镜像seekbell:m3-settings可复用，未发布。

## 授权

沿用独立WSL、noreply、已确认范围本地开发及私有main推送；推送前python3 scripts/check_privacy.py --identity。用户验收尚未进行，统一安排。无GHCR发布、远端部署、真实发送、原环境清理或全局WSL调整授权；不扩大范围、不组织多代理。
