# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5用户实测修正。ui-restore-4已公开发布并匿名拉取通过，待用户实机验收。

## 环境与授权

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。当前main，实现基准0499f8b1972f9131e0d977ea96305ccb93d5d327，本轮40bc7ba及兼容99bb654已合并，其后仅发布回执/Compose文档提交；codex/telegram-preview-card-fixes保留。用户批准最终删除方案、构建/公开发布镜像及8001 Compose自测；必要合并/开关已执行，不代部署、不真实发送。源码private、包public，不组织多代理；原D盘/Ubuntu/全局WSL不动。

## 实现与边界

删除弹窗仅列删除后无通知目标的任务：启用者“删除后暂停”、暂停者“保持暂停”；无此类任务时普通确认，不显示其他任务/数量，不增加替换流程。原风格/长名单滚动、保留规则和历史；正式演示共用。只读预览绑定目标/当前任务/告警版本，变化409重新确认；短事务内移除所有引用并建新任务版本，仅无目标者暂停，其余状态保持。旧目标待发取消、在途留租约/回执；告警无目标时明确关闭；无目标不可启用。
同时包含ee750a2的TG去两Emoji、发布时间、同formatter只读预览与整卡配置（保留SEEKBELL），172f6b7的RSS联合范围缺摘要按标题判断，显式摘要/作者/版块缺失仍三值。历史不回算、不补发。原确认UI/110%/采集卡/多站及详情间距、内存缓存保持；稳定语义见SPEC/UI_DESIGN。

## 验证与发布

[本轮实现/命令/回执](history/2026-10-22-通知目标删除与ui-restore-4发布.md)。本地删除52后端及54浏览器通过；首轮CI39779628607在容器旧DELETE空JSON兼容检查失败，未发布，开关已恢复。99bb654保持旧无确认依赖保护并兼容空请求体，新增两例，45相关后端与本地构建/容器持久化/实例锁复验通过。
[最终工作流](https://github.com/Aspeternity/seekbell/actions/runs/39787168575)成功：616后端、82浏览器、类型/格式/隐私/wheel/迁移、容器持久化/加密恢复/升级回退/隔离TLS、原生amd64/arm64均通过；复用已测归档发布并做发布后digest拉取检查。原型/正式桌面手机截图已核对。均合成数据与模拟服务，无真实论坛/通知；自动证据不冒充用户验收，Safari/真机未验。

当前ghcr.io/aspeternity/seekbell:ui-restore-4，索引sha256:09d7af1aa081594c2bb77f949f4bdcd534728618eef3bd3b667d708619a87e3a。空Docker配置实际匿名拉取amd64并核对UID/代码、两平台manifest及config；arm64为原生CI运行证据。旧ui3/ui2/ui1/ui-fix-1 digest均未变，临时SEEKBELL_GHCR_ENABLED已恢复缺失。原始状态/日志/ZIP在/home/dev/.local/state/seekbell/releases/ui-restore-4。

## 保护与下一步

Compose已更新，8001:8000与seekbell_compare_data沿用原Stack/卷，禁双实例共用SQLite卷。保护18081项目seekbell-acceptance-b45fc2c-20261020及容器/卷/backup-local、旧Stack/卷/8000/4175/18080；临时5174/8013/8015已退出，未代部署。仅NodeSeek，未扩大采集范围。无外部阻塞，下一步用户更新实机验收，收到反馈再修正。交接读本状态/本轮记录，发布维护按IMAGE_RELEASE。
