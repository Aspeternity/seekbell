# 当前状态

更新时间：2026-10-19 07:18（Asia/Shanghai）。M1/M2、M3核心六页与M4本地部署恢复已实现并自动验证；用户验收尚未进行，统一安排。M4本地交付无开发阻塞，下一阶段为M5实机/用户验收准备。

## 环境与代码

只在WSL2 SeekBell-Dev的/home/dev/projects/seekbell开发；当前从原Ubuntu经wsl.exe显式派发，D盘交接副本与原环境未改。[环境入口](DEVELOPMENT_ENVIRONMENT.md)。私有origin Aspeternity/seekbell，main；实现a8dc7e41a64d94e06cbb7bc1eb6efd639631b78f，测试脚本修正后HEAD/origin/main为965238ce847fb433575f003f91587c68db52320d，工作区干净。本次仅证据文档提交可使HEAD变化，不改实现基准。

## 实现与证据

M4停服实例锁内SQLite一致性备份，含账号/规则/历史/去重/队列及原密钥，用独立口令scrypt+AES-GCM流式认证加密。恢复验证备份管理员，只写空目录，暂存迁移/校验全部密文后安装并撤销会话。全过程持久中断标记，SIGKILL残留阻止误初始化。Compose默认独立测试项目、回环端口、后台关闭、UID10001/只读根FS及日志轮换；GHCR仅main手动、默认不发布，未执行。[操作手册](DEPLOYMENT.md)。

SeekBell-Dev/amd64：18项新增备份与11项基础测试共29项通过（8.68秒），含已提交WAL、身份去重、0006→0007、破损/错钥/路径拒绝、异常清理及真实子进程SIGKILL；Ruff、前端类型/构建/文案格式、wheel、noreply隐私通过。原前端仅说明文案，沿用有效浏览器证据，本机未重跑旧全套。

a8dc7e4固定SHA镜像用修正脚本通过Compose禁外网恢复/回退演练，临时项目/卷已清理；首轮脚本遗漏Bark敏感base_url，965238c按schema修正，应用未变。965238c镜像亦已本机构建（未重复本地演练）。[CI39175581516](https://github.com/Aspeternity/seekbell/actions/runs/39175581516)全部通过：pytest387项62.70秒、Chromium7项32.4秒、迁移/镜像、禁外网服务重启及Compose原密钥恢复/会话撤销/迁移失败停止/备份回退。CI镜像ID及本机镜像ID见[M4记录](history/2026-10-19-M4部署恢复.md)；均合成凭据/临时数据，无真实发送，不是用户验收。

前阶段证据见[系统设置记录](history/2026-10-19-M3系统设置.md)，无需重读/重跑。无遗留未提交实现、检查进程或临时部署；本地固定SHA镜像保留未发布。客户端弃用、CI动作Node20兼容提示及Rootless无cgroup限额仍在，不影响本次通过。

## 下一步与读取清单

按[验收矩阵](ACCEPTANCE.md)统一安排六页Web、PVE/真实反代、RSS及四渠道实际接收、恢复切换；原生arm64也未验证，双架构工作流未执行。先落实相应环境/目标及授权，再执行实机动作，不把自动通过记为用户通过。

读取本状态、ACCEPTANCE待执行项、DEPLOYMENT及DECISIONS授权；只有相关代码变化后再补针对性检查，无需全仓扫描或重复有效验证。

## 授权

沿用独立WSL、noreply、已确认范围本地开发及私有main推送；推送前python3 scripts/check_privacy.py --identity。用户验收统一安排。无GHCR发布、远端部署、真实发送、原环境清理或全局WSL调整授权；不扩大范围、不组织多代理。
