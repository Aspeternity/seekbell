# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5实测补修。用户批准通知冷进入/版块折行/筛选截字修复，代码完成、80项浏览器回归通过，正在提交和更新本地8001；数字仍不加点击。

## 环境、代码与授权

唯一开发SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发；[入口](DEVELOPMENT_ENVIRONMENT.md)。分支codex/content-loading-and-source-time，HEAD3b248b4，最后运行产品6ee4af938813dcc57d8e0a417fd8ccc0a2c741aa。未提交均为本轮批准范围：frontend通知预读/读取交接、请求合并、占位延迟和控件宽度，first-entry新套件/既有断言、CI/README与权威/状态文档。

用户要求今后代码修改先审批，本轮明确“进行修复”；[审批证据](history/2026-10-23-通知冷进入与下拉宽度补修待审批.md)。沿用同一8001保留数据更新授权；保留原配色/字体/统计口径，无推送、公开发布、远程部署或真实发送授权，不组织多代理，不动D盘/旧Ubuntu/全局WSL。

## 当前实现与验证

[补修记录](history/2026-10-23-通知冷进入与下拉宽度补修.md)：Notifications首屏预读并保留原面板/激活标签，目标就绪整体切换；recordQueries统一参数/缓存键，fetchRead合并同会话/数据版本在途请求，prepared只消费冷交接完成快照。灰色占位及反馈均200ms延迟。菜单最低160px，闭合框移除重复箭头留白，普通/长结果/任务目标渠道136/156/180px；中等桌面内容搜索独占一行，筛选与日期同行，窄屏换行。SPEC/UI_DESIGN/ARCHITECTURE已回写。

SeekBell-Dev工作区：15组Chromium桌面/手机仿真80项通过，包含冷/空/非空/慢网/失败重试/快速切换/迟到响应、直达200ms、经典滚动条/短项一行/渠道全文及既有回归；最终内容布局相关30项复跑。类型/生产构建、Prettier/Ruff/隐私/diff与截图核对通过。后端未改，复用b009317的669项结果。证据/home/dev/.local/state/seekbell/acceptance/2026-10-23-first-entry-width-fix；只用临时合成服务/库，未调整认证限流。Safari/真机/读屏/用户验收未完成。

## 本地实例

http://localhost:8001/（127.0.0.1亦可），seekbell-local/seekbell-local-seekbell-1、原卷seekbell-local_data；仍为seekbell:local-6ee4af938813，索引eac7130ea44a4713cf7c1e41038a81e5fc88299c657dffa2335eeb8c5c02c485，healthy/unless-stopped/read-only，仅localhost8001。账号/配置/历史严禁重置；既有before-6ee4af938813.tar.gz及8配置表校验见前轮交付。仓库外local-runtime/runtime.json、compose.env管理实例，原Windows保活PID14716不变。

单一正式前端及旧18080/18081退役已完成，旧卷归档；没有第二套运行产品。公开仍ui-restore-5，远程Stack及8000/4175未动。前轮日期范围、卡片点击、时间/首次快照保持。上轮74项漏验冷占位和经典滚动条占宽，本轮已补验证。

## 下一步与恢复读取

代码/状态同提交，构建新镜像并隔离容器/TLS代理检查；停同一8001完整备份原卷并校验，再原卷更新及Windows两地址健康/版本/新资源核验。记录SHA/digest后交用户实测；后续代码仍先审批。恢复读本状态、补修记录和相关实现。
