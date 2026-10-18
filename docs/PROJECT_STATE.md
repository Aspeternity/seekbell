# 当前状态

更新时间：2026-10-19 07:24（Asia/Shanghai）。M1～M4本地开发及自动验证已完成；M5统一用户验收准备中。用户选择先在本机验收六页与离线功能，尚无用户通过结论。

## 环境与基准

仅SeekBell-Dev的/home/dev/projects/seekbell开发；当前聊天从原Ubuntu经wsl.exe显式派发，D盘交接副本不改。[环境入口](DEVELOPMENT_ENVIRONMENT.md)。私有origin Aspeternity/seekbell，main；本轮开始HEAD/origin/main为56be582（证据文档），固定应用镜像/自动验证基准965238ce847fb433575f003f91587c68db52320d。noreply及.githooks沿用。

## 当前验收实例

用户已确认本机路线。入口http://127.0.0.1:18080/，Docker项目seekbell-acceptance、卷seekbell-acceptance_data，仅此验收卷，无演示帖子/预置管理员/真实凭据。镜像seekbell:965238ce847fb433575f003f91587c68db52320d，本机ID sha256:d9d574975f13762499410d06d24d3b23fc9a75db1d3657e954486e8e8049021f。

挂载专用local_acceptance_server.py，强制关闭后台/代理信任，应用进程拒绝IPv4/IPv6出站连接、UDP及外部DNS；这不是容器防火墙，其他exec进程不受守卫保护，不输入真实渠道凭据。WSL健康/版本/静态入口与Windows健康检查通过；守卫新增8项测试通过（0.17秒），Ruff/格式通过。未重复本机旧全套。浏览器打开请求返回queued，可直接访问上述地址。用户自行初始化，六页结果均待确认。

Rootless internal网络曾导致无端口映射，已移除无效配置。后台派发结束后观察到容器255与Docker服务重启，现通过前台Compose保持服务（工具会话10057）；不要结束该会话。若服务失联，按[M5用户清单](M5_USER_ACCEPTANCE.md)在正式WSL前台up重启，保留卷，不改全局WSL或重置数据。该本机验收实例需保留供用户操作，不作临时检查资源清理。

## 证据与改动

M4 [CI39175581516](https://github.com/Aspeternity/seekbell/actions/runs/39175581516)全通过：387项pytest、7项Chromium、迁移/镜像、禁外网重启及Compose备份/恢复/回退。详见[M4记录](history/2026-10-19-M4部署恢复.md)，M3证据沿链接复用。均自动证据，不是用户验收。

本次准备文件：deploy/compose.acceptance.yaml、acceptance.env.example、scripts/local_acceptance_server.py、tests/test_local_acceptance.py、M5_USER_ACCEPTANCE.md及ACCEPTANCE/DECISIONS/本状态；不改产品代码/镜像。deploy/.env.acceptance为忽略的本机配置，无密码。提交/推送及CI状态本轮结束前补齐。

## 下一步及授权

先由用户按U01～U09查看六页、规则试匹配和账号设置；反馈按页/操作/现象登记，再做针对性修复。U10备份恢复按需协助，不能覆盖当前卷。PVE/真实HTTPS、RSS/四渠道接收及原生arm64仍待统一实机验证。[操作手册](DEPLOYMENT.md)。读取本状态、M5用户清单及相关问题代码，不默认全仓扫描或重跑有效验证。

沿用本地开发、noreply、私有main推送及本机验收授权；推送前隐私身份检查。不发布GHCR、不远端部署、不真实发送，不改原环境/全局WSL，不组织多代理。客户端/CI弃用提示及Rootless资源限额限制仍在。
