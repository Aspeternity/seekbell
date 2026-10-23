# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。Linux DO新帖监控＋社区热榜代码与自动验证完成，准备容器验收/本地更新，尚未宣称实际来源可用。

## 环境与授权

唯一开发环境SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发。分支codex/linuxdo-integration从bab18a4建立，前一产品312d657，概览功能尚未推送。用户确认本轮完整方案并要求实施；沿用开发及保留数据更新本地8001授权，不含公开发布、远程部署或主动真实发送。无多代理，不改D盘/旧Ubuntu/全局WSL/8000/4175。

## 实现与恢复入口

本轮未提交改动均属已授权Linux DO实现，范围backend/seekbell的sites/collectors/domain/db及0011迁移、runtime/collection/request_budget/hotlists/API/历史/通知展示，frontend的网站库/任务/内容/热榜/类型，tests新增Linux DO及旧单来源断言调整，CI与容器检查、README和契约文档；无其他用户改动。详见history/2026-10-23-LinuxDO接入.md，恢复先读本状态和该记录，按其中路径读代码。

0011只增加默认关闭的网站/来源身份，不安装实例；按站独立SourceRunner，TaskGroup拥有/关停，预期来源失败不影响另一站。Linux DO监控/测试/热榜共用互斥、2秒请求间隔和持久退避，403/挑战至少300秒，Retry-After至多一天；延期不伪造HTTP失败，匿名请求显式去Cookie。主题ID去重和基线/恢复语义复用。显示名单独存储，规则author为空且拒绝用户名条件；RSS结构去尾注后纯文本化，不补抓正文/回帖。

热榜Linux DO热门/每日/每周、NodeSeek实时/每日/每周，按能力切换并记住各站选择；Linux DO来源时间未知显示获取时间，不虚构数字。两站每榜一份SQLite成功快照，600秒按需更新，重启恢复，最多展示24小时；失败保留旧结果，隐藏/离开不继续刷新。热榜不入监控/规则/通知，既有模块显隐排序保留。SPEC/UI_DESIGN/ARCHITECTURE/DECISIONS已同步。

## 验证与限制

当前实现工作区：后端全量716通过（含新增33），桌面/手机11套相关浏览器共84通过，类型/生产构建、Ruff/Prettier、diff/隐私/锁检查通过。初轮旧测试单来源/迁移号假设已显式按NodeSeek修正；新浏览器用例增加独立选择重置和外部修改后的刷新，错误检查未放宽。全量并非真实论坛或渠道验收，测试使用临时库/合成HTTP和发送器。证据/home/dev/.local/state/seekbell/acceptance/2026-10-23-linuxdo-integration。

本机4个Linux DO候选RSS普通HTTP均403，另次标准库显示Cloudflare挑战；原证据linuxdo-design/public-rss-probe.json（bab18a4）。无Cookie/模拟浏览器/轮询绕过；上游源码不能替代站点当前版本验收。CI新增test:linuxdo（8030），原NodeSeek专项均保留。

## 本地实例与下一步

8001仍seekbell-local/seekbell-local-seekbell-1、原卷seekbell-local_data，seekbell:match-evidence-312d657f582b，镜像ID sha256:52f6c5626a7d1dab27f69ee3d7e8d8eb4a474b5728e4a3d36a01c8a6bea94cf1，schema0010，健康。Windows保活PID14716不调整。

下一步提交实现后构建标记镜像，执行禁外网容器/备份恢复/升级回退演练；停服整卷备份校验，在隔离副本验证0010→0011及既有配置/历史，再切换同一8001。新迁移回退必须恢复匹配0010备份，禁止直接旧镜像读新库或复用上轮同schema更新假设。原备份local-runtime/backups/before-312d657f582b-20261023-221929.tar.gz保留。来源403是已知接入限制，既有功能无阻塞。
