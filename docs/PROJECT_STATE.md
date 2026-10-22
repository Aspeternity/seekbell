# 当前状态

更新时间：2026-10-22（Asia/Shanghai）。M0～M3完成、M4工程退出通过，现M5用户实测修正。Telegram预览/卡片及本轮RSS缺摘要修正均已本地实现、针对性检查通过，尚未发布或用户实机验收。

## 环境与基准

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。当前codex/telegram-preview-card-fixes，基于main f5cac4d（已发布实现679bcf0）；前轮实现ee750a2008fee07c51d0906b260f9762de680172，本轮实现172f6b7c3bea3575e1f6f6fe7b65ce6e1b14ed12（基于ca2068d，代码/规格/测试/状态同提交；后续仅文档收尾）。原D盘/Ubuntu/全局WSL及旧分支保留，不组织多代理。

## 本轮批准与实现

用户明确要求按RSS实际提供内容判断，并授权修改：标题＋摘要缺摘要时仅按标题匹配和排除，不因未知摘要挡住已满足的标题；标题不满足为不命中。仅摘要缺失与空文本、显式作者/版块缺失仍保留三值判断，已知否决优先。共用后端只过滤联合范围的缺失字段，原None保留；演示逻辑及原位置说明同步，不新增选项或改UI布局。SPEC/ARCHITECTURE/ACCEPTANCE已回写。
[本轮根因、范围、命令和证据](history/2026-10-22-RSS缺摘要匹配语义修正.md)。此前“严格默认/可选降级”仅是讨论建议，已被本轮确认方案替代。历史判定不回写，已见帖子不重推；无迁移/采集/队列结构扩展。

前轮TG去两Emoji、发布时间、同正式formatter的认证只读预览及整卡进配置已完成，内部SEEKBELL保留；154后端/54独立浏览器及类型构建检查证据见[前轮记录](history/2026-10-22-Telegram预览与通知卡片交互修正.md)。原UI/1475f5a采集卡、批准110%/多站交互、概览/下拉/间距/退出、679bcf0的详情16px和页面内存缓存保持。稳定约束以SPEC/UI_DESIGN为准。

## 本轮本地验证

88后端通过（19.87秒，一条既有warning）：规则边界、真实RSS解析摄取后入队一次、摘要排除、仅摘要及元字段限制、手动与历史同结果且业务表不写。原型桌面/手机4项3.7秒、正式API接入2项11.7秒通过，共6项浏览器回归；两版类型/构建、Ruff/Prettier/隐私/diff通过。均合成RSS/临时库，无真实采集或发送。临时5174/8015均已退出（ss核对）；自动证据不冒充用户验收。

## 已发布与保护

当前公开ghcr.io/aspeternity/seekbell:ui-restore-3，代码679bcf0ee09c9da63f01f2fbbe99347bc7f5a01c，digest sha256:328f888d8b616e45947edb512e5c7f9d1e6b27ded11ff0c33ee43021277f97e4；[564后端/74浏览器/双架构及匿名证据](history/2026-10-22-详情通知与页面加载修正.md)。源码private/包public、关联not-reported，临时开关恢复缺失。本轮仅授权修复，未合并/推送/发布，Compose仍原镜像。
8001:8000及seekbell_compare_data保留，更新沿用同一Stack/卷，禁双实例共用SQLite卷；保护18081项目seekbell-acceptance-b45fc2c-20261020及容器/卷/backup-local、旧Stack/卷/8000/4175/18080。仅NodeSeek；Safari/真机未验收。

无外部阻塞。本轮本地提交完成，下一步按用户指示发布或处理反馈；未擅自合并/发布。交接读本状态、本轮记录、相关规则/试算代码，发布时按需IMAGE_RELEASE。
