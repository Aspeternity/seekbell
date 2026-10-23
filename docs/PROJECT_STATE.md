# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。用户确认内容详情按命中/其他判定分组展示，本轮已实现，后端26项/浏览器20项及最终布局补验通过，待提交/镜像更新；8001仍运行上一产品2a37ebc。

## 环境与授权

唯一环境SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发，见[环境](DEVELOPMENT_ENVIRONMENT.md)。codex/overview-modules-and-hotlist，最新产品2a37ebce01c3919d46be2f1357c779a0f070881f，随后仅交付文档；上一产品2665aa6，功能基线e53d89e、规格7f8c15b、main 2c682de。此前PR #1已合并，见[记录](history/2026-10-23-本地修复合并与热榜分支.md)。

用户已授权本分支开发、本地Docker实测及反馈修正，沿用8001保留数据更新。不含新功能推送/合并、公开发布、远程部署或主动真实发送。无多代理，不改D盘、旧Ubuntu、全局WSL或8000/4175。上一产品/交付已提交；本轮未提交路径见下方，无其他用户改动。

## 实现与边界

契约SPEC 6.1、ARCHITECTURE、UI_DESIGN；[功能开发](history/2026-10-23-概览模块与热榜开发.md)及[上轮入口/箭头修正](history/2026-10-23-热榜入口与折叠箭头修正.md)。0010保存布局/浏览选择；三模块显隐/拖动/键盘排序、默认草稿/冲突与跨设备保持，上方统计固定。仅NodeSeek第三方三周期，5/10条、来源时间/署名、按站能力/选择；Linux DO/V2EX未接入，合成多站仅验证UI。热榜不入规则、历史、统计或通知。

[本轮记录](history/2026-10-23-热榜缓存与整行点击.md)：已有缓存立即返回，过期以一次合并后台任务更新；冷读共享且单读者取消不取消其他读者，生命周期关闭取消/等待任务。refreshing与失败分开，约2秒读完成结果，结束后恢复600秒冷却/退避。可见卡片预取当前网站其他周期、复用认证会话缓存/在途请求，不改选择，不抓其他网站；隐藏/离开不继续刷新，无消费者不循环请求。无磁盘缓存或迁移，重启/首次全无缓存仍可能等一次，不承诺绝对零等待。

最近命中整行原生链接到站内内容详情，已清理行无链接；热榜整行新标签打开规范原帖，两者支持元信息/留白/键盘与焦点。“版本N”改“任务配置 vN”，解释为命中当时配置；创建v1，后续配置更新递增，历史保留原版本。

本轮新增：内容详情“任务匹配快照”默认命中卡片，原因跟随各任务；其他判定计数折叠且展开时读取，无命中直接展示全部。服务端group=all/primary/other在分页前过滤，返回两组总数；无迁移/重算，旧all调用兼容。独立加载/错误/分页、换帖重置与迟到隔离，已删除任务历史保留。未提交：api/history.py、services/history.py、frontend/src/history.ts、pages/Content.vue、新TaskEvaluationCard.vue、evaluations/evaluations.spec.ts及history.spec.ts、tests/test_history.py、playwright.evaluations.config.ts、package.json、ci.yml、契约/状态/[本轮记录](history/2026-10-23-内容任务判定分组优化.md)。生产构建/类型已通过，后端历史26项通过；分组浏览器场景通过，初轮共用实例触发旧账号测试限流，已将新增组拆至8029临时实例，保留正式限流；最终桌面/手机分组8、历史4、内容稳定8项均通过，共20浏览器；格式/Ruff/diff通过。

## 验证与实例

2a37ebc：后端热榜/概览22项，桌面/手机hotlist 26、loading 4、history 4共34浏览器通过；手机提示样式清理后重建和相关8项补验通过。类型/生产构建、Prettier、Ruff/diff/隐私通过。镜像禁外网服务、静态、重启及配置持久化通过。证据/home/dev/.local/state/seekbell/acceptance/2026-10-23-hotlist-cache-and-rows。自动测试为临时合成库/模拟HTTP，不访问真实论坛或通知；真机/Safari/读屏、提供方长期稳定性与用户验收独立。

同一http://localhost:8001/或127.0.0.1:8001；seekbell-local/seekbell-local-seekbell-1、原卷seekbell-local_data，运行seekbell:hotlist-cache-2a37ebce01c3，镜像ID sha256:9688f0821748e28e126eb02423290f44ec2450488c701ac8b2e7b1f290ed5823。仍0010、healthy/read-only/unless-stopped、仅本机8001。Windows两地址/版本/资源通过，原保活PID14716身份/创建时间一致。

停服整卷备份before-2a37ebce01c3-20261023-192139.tar.gz（local-runtime/backups，0700/0600），逐文件SHA、解包副本SQLite及实际更新前后12类配置指纹通过；账号/配置/历史保留，无合成导入。运行元数据已更新；旧2665aa6同0010可回退，更旧58bee30需配旧库备份。完整SHA/命令与证据文件见本轮记录。

下一步完成本轮针对性验证、提交与隔离镜像检查，备份当前数据后更新同一8001供验收；新功能推送/合并另行处理。恢复读本状态、本轮记录和相关实现；无技术阻塞。
