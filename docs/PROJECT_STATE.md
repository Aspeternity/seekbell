# 当前状态

更新时间：2026-10-18（Asia/Shanghai）。阶段：M0实现保留待审；新WSL开发环境已配置，冷启动和容器复核通过；M1未开始。

## 代码与工作目录

正式开发环境改为`SeekBell-Dev`（WSL2 Ubuntu24.04.5/amd64），目录`/home/dev/projects/seekbell`。虚拟磁盘位于`D:\WSL\SeekBell-Dev`；默认用户dev。原`D:\Projects\SeekBell`保留交接副本，后续不在原Ubuntu构建。进入方式及配置见[开发环境](DEVELOPMENT_ENVIRONMENT.md)。

M0实现基准`1ddea580bbfc314a9e9df97bd2e95e375a2d0202`；交接基准`4f0d8d5`，分支main，无远程。源码/Git历史已复制，依赖在新环境按锁文件重建。本轮仅提交AGENTS、README、状态、新环境文档和迁移记录，记录环境边界与证据；无业务代码变更，文档同步后两处代码一致。

## 实现与自动证据

M0：FastAPI/Vue骨架、SQLite迁移、版本/健康API、数据目录锁、CI与非root镜像，业务采集/通知/管理员尚未实现。原证据见[阶段记录](history/2026-10-18-M0.md)。

新环境（同一M0代码）：Python3.12.3、uv0.13.1、Node24.22.0、pnpm10.34.7；11项pytest、Ruff、锁校验、wheel、前端类型/格式/构建、迁移upgrade/current/check通过。Docker29.9.1 Rootless已独立启动，新发行版定向重启后可恢复；amd64镜像构建与离线容器API/资源/UID/锁/healthcheck/重启持久化均通过，临时容器和卷已清理。

## 环境与部署

新Docker上下文rootless，数据`/home/dev/.local/share/docker`，服务以dev身份运行。系统级Docker服务已禁用。持久化运行目录曾因残留PID阻止冷启动，现由systemd RuntimeDirectory管理`/run/seekbell-docker`及socket；修复后新发行版冷启动和离线容器复核通过，旧运行目录已删除，不保留回退补丁。当前无容器级cgroup限额，未改全局资源设置。

新镜像`seekbell:m0-local`的本地inspect标识为`sha256:354cae141dd1ed0a2ba9df5001dc5eab70c8436fce52ac65cc5d0071651e3d55`，版本为上述完整M0代码SHA。详见[迁移记录](history/2026-10-18-开发环境迁移.md)。原Ubuntu工具/镜像/缓存保留，未授权清理。无PVE/SSH部署、远程发布或manifest digest。浏览器/手机、arm64、真实RSS/通知、远程CI、备份恢复与用户验收均未完成。

## 下一步与读取

下一步请用户在新发行版目录打开项目，审阅环境与M0；不自动推进M1。环境无阻塞；原Ubuntu后续只用于其既有项目。

本轮只需环境文档、M0检查命令和受影响配置。同会话已读规格复用；未来获准进入M1时读SPEC第3～5节、ARCHITECTURE模块契约/一致性/恢复、RESEARCH的RSS字段/身份结论、ACCEPTANCE R01～R05/F01～F05/D01/D04/P01及实际影响代码。

## 授权与限制

用户指出原开发跳过环境确认，要求先确定环境；随后明确同意新建独立WSL及`D:\WSL\SeekBell-Dev`位置。授权新环境工具、独立Docker、源码复制与模拟验证。未授权原Ubuntu清理、全局WSL调整、远程推送/发布/部署或真实发送；M0尚无用户验收。不组织多代理，不扩大首版范围。
