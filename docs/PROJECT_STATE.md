# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。Linux DO新帖监控＋社区热榜已实现、自动验证并更新本地8001；真实RSS当前403，用户验收待继续。

## 环境与授权

唯一环境SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发。分支codex/linuxdo-integration，产品e1d2f21b5cd5902325449a024f9b1b64a2485f1c；从bab18a4（前产品312d657）建立，功能均未推送/合并。用户确认完整方案并要求实施，沿用开发及保留数据更新同一本机8001授权；不含公开发布、远程部署或主动真实发送。无多代理，不改D盘/旧Ubuntu/全局WSL/8000/4175。

## 实现与读取入口

[本轮记录](history/2026-10-23-LinuxDO接入.md)，SPEC 6.2/UI_DESIGN/ARCHITECTURE/DECISIONS已同步。恢复先读本状态和记录，再按影响读取sites/registry及linuxdo、collectors/http及rss、0011迁移、runtime/collection/request_budget/hotlists、管理与历史接口、前端网站/任务/热榜及新增测试。

0011只增默认关闭的网站/来源，不安装实例；按站独立SourceRunner，TaskGroup拥有/关停，预期来源失败不拖慢另一站。Linux DO监控/测试/热榜共用互斥、2秒间隔和持久退避，403/挑战至少300秒，Retry-After至多一天；延期不伪造HTTP失败，匿名请求去Cookie。主题ID去重及基线/重启语义沿用。作者显示名单独存储，规则author为空且拒绝用户名条件，摘要按RSS模板结构去尾注，不补抓正文/回帖。

热榜Linux DO热门/每日/每周、NodeSeek实时/每日/每周，各站记住选择；未知来源时间显示获取时间，数字缺失不编造。两站每榜一份SQLite成功快照，600秒按需更新、重启恢复、最多展示24小时，失败保留旧结果，隐藏/离开不继续刷新；不入监控/规则/通知。现有模块显隐/排序及仅命中依据保留。

## 证据与限制

e1d2f21实现工作区后端全量716通过（新增33），桌面/手机11套相关浏览器共84通过；类型/构建/格式/隐私/锁、三个离线演练/wheel及禁外网容器/加密恢复/升级回退通过。旧单来源/迁移号断言按NodeSeek明确过滤；测试夹具刷新/选择重置已修正，未放宽错误检查。提交检查将一条无效URL测试改为拼接，相关24项重跑通过。未声称全部浏览器/远程CI或真实发送通过。

产品提交后人工普通HTTP各一次读取4个Linux DO源均access_challenge，未使用凭据、模拟浏览器或重试轮询；真实数据可用性未验收。证据/home/dev/.local/state/seekbell/acceptance/2026-10-23-linuxdo-integration（含manual-public-rss.json）；自动验证均合成库/HTTP/发送器，不污染正式数据。

## 本地部署与回退

http://localhost:8001/或127.0.0.1:8001；seekbell-local/seekbell-local-seekbell-1、原卷seekbell-local_data，seekbell:linuxdo-e1d2f21b5cd5，镜像ID sha256:efae316460c5f0b66b3fb7a5d763d843a78aa59a916bbc4ee7e0c4c39d443b81。schema0011_linuxdo，healthy/read-only/unless-stopped，仅本机8001。Windows两地址/版本/资源通过，保活PID14716身份/创建时间一致，运行元数据已更新。Linux DO未自动安装/启用。

停服整卷备份local-runtime/backups/before-linuxdo-e1d2f21-20261023-232943.tar.gz，SHA256 5d25269eb1051c99b5f059665fbbc6a2e3d74940e8de32e49959e0d531659868，目录0700/文件0600；逐文件SHA/解包SQLite通过。隔离副本0010→0011所有原有表行哈希、12类原配置、密钥和加密凭据验证通过，未启动Runtime；正式切换后原配置指纹一致。新身份默认行单独核对，临时卷已清理。旧312d657镜像/备份保留，回退必须恢复匹配0010整卷，禁止旧镜像直接读0011。

本轮产品及交付记录均本地保存，后续仅交付文档提交，无其他用户改动。下一步用户刷新8001，从网站库添加Linux DO测试界面和连接提示，据反馈修正；实际RSS受限与用户验收明确待办，新功能推送/合并另行处理。
