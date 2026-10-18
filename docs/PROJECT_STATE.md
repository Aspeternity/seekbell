# 当前状态

更新时间：2026-10-18（Asia/Shanghai）。阶段：M0工程基线完成且本地验证通过；下一阶段M1，尚未开始。

## 代码与环境

目录`/mnt/d/Projects/SeekBell`；WSL2/Linux x86_64；分支`main`，无远程。原规格保存于`b9df967`；M0实现提交`1ddea580bbfc314a9e9df97bd2e95e375a2d0202`。此后仅提交文档证据，不改变代码基准；无在途实现或需保留的未提交用户改动。

Python 3.12.3、Node 24.22.0、uv 0.13.1、pnpm 10.34.7、Docker 29.5.2。Linux工具位于用户目录；新shell需设置PATH，命令见[阶段记录](history/2026-10-18-M0.md)。忽略的依赖/构建产物不入Git。

## 实现与证据

已实现：模块骨架、SQLite/Alembic初始迁移、单实例锁、版本/存活/就绪API、Vue/Naive UI版本页、锁文件、基础CI和非root单容器构建。无管理员/采集/通知业务，不代表M1～M4完成。

自动验证（实现`1ddea58`/WSL2 amd64）：11项pytest、Ruff、锁校验、wheel、前端类型/格式/构建、迁移维护命令通过。本地CLI约5.3秒启动，API/编译首页与SIGTERM完整关闭通过。禁用外网的临时Docker容器通过API/编译资源/UID10001/进程锁/healthcheck/同卷重启检查，临时容器与卷已清理。命令、范围、上游弃用警告见阶段记录；原RSS研究证据仍见RESEARCH。

## 部署与待验证

本地amd64镜像`seekbell:m0-local`已固定上述完整SHA并复核通过；image ID：`sha256:716a7c0cbcf95084f931f979c3726e82ddb15b29e7e765df907a0629fb84f265`，非远程manifest digest。迁移`0001_installation`。PVE/SSH未提供，未部署；临时容器和卷已清理。

浏览器/手机体验、远程CI、arm64、真实RSS/通知、Compose/备份恢复、用户验收均未执行。RSS频率无官方限频数字，10秒仍是候选默认，不能保证摘要和窗口完整覆盖。

## 已排除与下一步

外部迁移资源映射导致editable安装失败，已移除；迁移随Python包安装，源码/容器均通过，不保留回退补丁。未扩大范围，不组织多代理。

M1先做NodeSeek合成样本解析/首次成功基线/稳定身份与纯三值规则，再接持久化outbox及模拟通知；没有阻塞本地M1的外部依赖。

## 本任务需要读取

M0已读内容同会话复用。进入M1时按需读取：
- SPEC第3～5节；ARCHITECTURE模块契约、数据一致性、调度恢复。
- RESEARCH中NodeSeek RSS字段/身份/原始样本结论。
- ACCEPTANCE：R01～R05、F01～F05、D01/D04/P01；ROADMAP的M1行。
- 当前`backend/seekbell/db`、`migrations`、`main.py`及`tests/test_baseline.py`，扩展到实际受影响模块。

## 授权

已授权本地开发、Git初始化和模拟验证。未提供/授权远程创建推送、GHCR发布、SSH部署、真实通知目标或许可证；不阻塞M1。具体远程动作准备可审阅后再询问。用户验收尚无，不能以自动检查替代。
