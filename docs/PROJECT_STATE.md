# 当前状态

更新时间：2026-10-22（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5用户实测修正。删除流程及前轮Telegram/RSS修正本地完成，ui-restore-4首次CI失败，已定位旧空请求体兼容问题并修复中，尚未发布或用户验收。

## 环境与授权

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。当前main 9783c0f1859ff41eaacda4c7043f14f8797e783e，已合并本轮40bc7ba及前轮ee750a2/172f6b7；codex/telegram-preview-card-fixes保留。用户明确批准最终删除交互并要求构建镜像、给Compose自测；本次公开GHCR发布及必要合并/开关已授权，不代部署、不真实发送。源码仍private、包public，不组织多代理，原D盘/Ubuntu/全局WSL不动。

## 已实现与本地证据

删除弹窗只显示删除后无通知目标的任务：启用者“删除后暂停”、暂停者“保持暂停”；无此类任务时普通确认，无其他任务/数量或替换流程。任务规则/历史保留，原风格/长名单滚动，正式演示共用。认证只读预览与确认摘要绑定目标/全部当前关联任务/告警版本，过期409需重新确认；短事务内解除引用并建新任务版本，仅无目标者暂停。原目标待发取消、在途保留租约/回执；告警无目标时明确关闭；无目标任务不可启用。
本地52后端20.61秒、原型44项45.8秒、operations6项16.5秒、sending4项20.2秒，共54浏览器通过；两版类型构建/Ruff/Prettier/隐私身份/diff通过，截图已核对。均模拟RSS/临时库，无真实采集发送，5174/8013/8015已退出。[本轮代码/命令/证据](history/2026-10-22-通知目标删除与ui-restore-4发布.md)。远端pytest步骤已通过（最终数量待回执），完整浏览器/镜像检查尚待，不冒充验收。

前轮[TG预览/卡片](history/2026-10-22-Telegram预览与通知卡片交互修正.md)保留SEEKBELL、去两Emoji、真实发布时间、同formatter只读预览及整卡配置；[RSS缺摘要](history/2026-10-22-RSS缺摘要匹配语义修正.md)联合范围只匹配已得字段，缺摘要按标题，仅摘要/作者/版块仍三值，历史不重算不补发。原确认UI及110%/采集卡/多站、详情间距和内存缓存保持，稳定语义见SPEC/UI_DESIGN。

## 发布中与保护

目标ghcr.io/aspeternity/seekbell:ui-restore-4原不存在；工作流39779628607在容器检查失败，native/publish均跳过，未写镜像。根因：旧脚本DELETE传{}，新可选请求体模型却要求confirmation，返回422；修复为缺省None继续旧依赖保护，新增None/{}两种回归，不放宽有依赖的无确认删除。原614后端及80个非代理浏览器均已通过，最终数量待日志整理。
SEEKBELL_GHCR_ENABLED已DELETE并GET404，恢复原缺失。操作目录/home/dev/.local/state/seekbell/releases/ui-restore-4保留失败日志，待本地容器复验后新SHA重启全流程。兼容修正及相关管理回归45项通过（19.06秒）；准备提交API/测试/两份进度文档并本地构建容器复验后再发布。
当前可用镜像仍ui-restore-3，代码679bcf0ee09c9da63f01f2fbbe99347bc7f5a01c，digest sha256:328f888d8b616e45947edb512e5c7f9d1e6b27ded11ff0c33ee43021277f97e4。旧ui3/ui2/ui1/ui-fix-1 digest已留底；成功及匿名核对后才更新Compose。
8001:8000与seekbell_compare_data沿用原Stack，禁双实例共用SQLite卷。保护18081项目seekbell-acceptance-b45fc2c-20261020及容器/卷/backup-local、旧Stack/卷/8000/4175/18080。仅NodeSeek；Safari/真机未验收。无外部阻塞；下一步等待CI并完成发布回执、匿名核对、Compose交付。交接读本状态/本轮记录与IMAGE_RELEASE。
