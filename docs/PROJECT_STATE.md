# 当前状态

更新时间：2026-10-18（Asia/Shanghai）。阶段：用户授权进入M1核心闭环；先落实提交邮箱隐私检查，M1业务实现正在开始。

## 代码与环境

正式目录为SeekBell-Dev发行版的`/home/dev/projects/seekbell`（Ubuntu24.04.5/WSL2/amd64，用户dev）；虚拟磁盘`D:\WSL\SeekBell-Dev`。原D盘项目仅交接副本，不再同步新提交或继续构建。入口及隔离边界见[开发环境](DEVELOPMENT_ENVIRONMENT.md)。

origin为私有仓库[本项目](https://github.com/Aspeternity/seekbell)，main跟踪origin/main。M0应用实现基准`1ddea580bbfc314a9e9df97bd2e95e375a2d0202`；CI修复基准`69d71cef3470966ab21601a1c569417c0584d549`。之后仅提交文档证据，不改变代码基准。本轮未提交：scripts/check_privacy.py、.githooks、隐私测试、CI及相关文档，防止真实邮箱进入提交身份/历史内容；后续追加M1模块与测试。历史作者/提交者已核实均为noreply，无需重写历史。

## 实现与证据

隐私检查：现有全部作者/提交者为noreply；本地提交/推送钩子已启用，6项隔离Git仓库测试通过，历史与索引邮箱检查通过，不打印被拒地址。

M0已实现FastAPI/Vue骨架、SQLite迁移、版本/健康API、数据目录锁、基础CI和非root镜像；管理员/采集/规则/通知业务尚未实现，不代表M1～M4完成。

新WSL：Python3.12.3、uv0.13.1、Node24.22.0、pnpm10.34.7；11项pytest、静态检查、wheel、前端构建、迁移检查及离线容器验证通过，见[迁移记录](history/2026-10-18-开发环境迁移.md)。

远程CI：上述69d71ce，在GitHub-hosted Ubuntu24.04/amd64、镜像版本20261012.334.1上[运行39138356106](https://github.com/Aspeternity/seekbell/actions/runs/39138356106)成功。锁校验、Ruff、11项测试、wheel、前端、迁移、Docker构建及禁用外网的容器检查均通过。首轮job.env引用runner失败，已移至step.env，旧配置已移除；详情和CI镜像ID见[接入记录](history/2026-10-18-GitHub接入.md)。

## 部署与限制

本地Rootless Docker29.9.1，数据`/home/dev/.local/share/docker`，socket`/run/seekbell-docker/docker.sock`；冷启动残留PID已通过systemd RuntimeDirectory修复。无容器级cgroup限额，未改全局WSL设置，原Ubuntu工具/镜像未清理。

本地M0镜像inspect ID为`sha256:354cae141dd1ed0a2ba9df5001dc5eab70c8436fce52ac65cc5d0071651e3d55`，应用版本为1ddea58；CI镜像仅临时构建，未发布。PVE/SSH、浏览器/手机、arm64、真实RSS/通知、备份恢复与用户验收均未完成。

## 下一步与读取

隐私检查通过后实施M1：合成RSS解析/身份、纯三值规则、首次成功基线、持久化outbox及模拟通知恢复；不启用真实轮询、真实发送或未认证管理API。

M1本轮按需阅读SPEC第3～5节、ARCHITECTURE模块契约/一致性/恢复、RESEARCH RSS字段/身份结论、ACCEPTANCE R01～R05/F01～F05/D01/D04/P01及受影响代码，不重复全读。

## 授权

用户已确认新WSL与D盘位置及私有仓库，现明确授权进入M1并继续推送，要求不暴露真实邮箱。用户新增授权进入下一步M1，要求后续推送不暴露真实邮箱；未授权原Ubuntu清理、全局WSL调整、GHCR发布、部署或真实发送；M0尚无用户验收。不组织多代理，不扩大范围。
