# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5实测补修。用户批准的通知冷进入、版块折行和筛选截字修复已交付同一8001，82项浏览器及隔离镜像检查通过，待用户实测。数字仍不加点击。

## 环境、代码与授权

唯一开发SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发；[入口](DEVELOPMENT_ENVIRONMENT.md)。分支codex/content-loading-and-source-time，产品58bee30ff55a7c6f0450f6a626806eba1ad49fe8，随后仅交付证据文档，无未提交产品改动。

用户要求代码更改先审批；本轮明确“进行修复”，[审批证据](history/2026-10-23-通知冷进入与下拉宽度补修待审批.md)。保留原配色/字体/统计口径，沿用同一8001保留数据更新授权。无推送、公开发布、远程部署或真实发送授权，不组织多代理，不动D盘/旧Ubuntu/全局WSL。

## 实现与证据

[补修记录](history/2026-10-23-通知冷进入与下拉宽度补修.md)：通知预读三个记录菜单首屏，保留原完整面板和激活标签，目标就绪整体切换，失败重试、慢请求延迟反馈；recordQueries统一参数/缓存键，fetchRead合并同会话/数据版本请求，prepared只消费冷交接完成快照。灰条及反馈均200ms延迟，避免快读占位闪现。菜单最低160px，闭合框移除重复箭头留白，普通/长结果/任务目标渠道136/156/180px；中等桌面内容搜索独占一行，筛选与日期同行，窄屏换行。规格/架构已回写。

SeekBell-Dev、58bee30：16组Chromium桌面/手机仿真82项通过，覆盖冷/空/非空、慢网、失败重试、连续切换/迟到响应、直达200ms、经典滚动条/短项一行/渠道全文及既有回归；最终内容布局相关30项复跑，其余适用证据复用。类型/生产构建、Prettier/Ruff/隐私/diff、截图及禁外网容器/TLS代理通过。后端未改，复用b009317的669项结果。证据/home/dev/.local/state/seekbell/acceptance/2026-10-23-first-entry-width-fix；只用临时合成库，未改认证限流。Safari/真机/读屏和用户验收未完成。

## 本地实例

http://localhost:8001/（127.0.0.1亦可），seekbell-local/seekbell-local-seekbell-1、原卷seekbell-local_data；seekbell:local-58bee30ff55a，索引sha256:5886d4f1b9e1d6de5c922ca0bf9af8141099eee3f6a72e594f80daf58f364202。healthy/unless-stopped/read-only，仅localhost8001。原账号/配置/历史保留，完整备份local-runtime/backups/before-58bee30ff55a.tar.gz（0700/0600）；文件/SHA/SQLite及更新后8配置表指纹一致。Windows两地址首页/ready/version/新资源已核验，原保活PID14716有效。local-runtime/runtime.json、compose.env及windows_check已更新；6ee4af9仅回退镜像。

单一正式前端及旧18080/18081退役已完成，旧卷归档；没有第二套运行产品。公开仍ui-restore-5，远程Stack及8000/4175未动。前轮日期范围、卡片点击、发布/发现与首次快照保持。上轮74项漏验冷占位与经典滚动条占宽，本轮新增用例已覆盖。

## 下一步与恢复读取

请用户在8001验收三项补修；暂无技术阻塞，后续反馈先审查方案再经审批改代码。恢复读本状态、补修记录及相关实现；管理命令沿用[本地运行](history/2026-10-23-最新代码本地Docker实测启动.md)。
