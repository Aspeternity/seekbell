# 当前状态

更新时间：2026-10-25（Asia/Shanghai）。阶段：V2EX数据源重新选型待审。本轮用户要求先查清可用来源再判断组合；只读调研、8次匿名元数据核验和文档，无产品/数据库/运行改动，尚未批准开发。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发，已核对发行版/目录/分支/工作区。分支codex/v2ex-plan，本轮起点640e62a（文档）；产品来自main 987beda。仅本地提交，不推送/合并新方案。此前36提交已经PR #2合入main 5cdf5bd68d88dac53fea6e364c8fe8b2fe392db7，CI head d94958d及两架构过，见合并记录。无多代理；不动D盘/旧Ubuntu/全局WSL/8000/4175，无新公开镜像、远程部署或真实试发授权。

## 优先读取与事实

先读[最新数据源报告](history/2026-10-25-V2EX数据源对比.md)；[10月24日方案](history/2026-10-24-V2EX接入方案.md)只复用多源一致性等未被替代部分，[热榜分析](history/2026-10-24-热榜刷新与节点目录说明.md)独立待批。实施再读collectors/rss.py、collection/ingestion/source_probe/request_budget、模型/注册/任务范围。
发现此前遗漏的官方节点API：站长2026帖子1187622介绍show.json?node_name，说明翻页需PAT V2；本次programmer/vps/all4all匿名API均200但各10项（历史写20不能当现状）。同轮programmer JSON Feed50项，API10全在其中，另40是更早窗口。programmer/vps/all4all XML均Atom50项；VPS/二手全部作者member URI可校验；技术聚合Atom50项无逐帖节点。节点Atom缓存头600秒、JSON1800、API432000，不能据头宣称实际更新速度。8个固定URL各一次，间隔至少2秒，无持续轮询；私有acceptance/2026-10-25-v2ex-source-review下两个JSON只留元数据，旧probe保留，不留正文/用户名/帖子ID入Git。

## 当前建议与待定

优先节点Atom主采＋公开最新API可选共享补充＋热门API/目录JSON。节点默认10分钟错峰，公开API需要时一份2分钟，热门15分钟按需，目录24小时；均工程候选，非官方时效保证。JSON Feed/节点API为替代评估，不对同节点并行三路或自动切格式绕过错误；V2 Token分页、用户专源、聚合分类、HTML及第三方不进当前版。Atom需显式安全解析/MIME适配，现parse_rss只认RSS，已有feedparser等依赖足够。
用户此前确认两类用途，后讨论倾向V2EX任务明确选节点、去掉全部板块，网站不加总范围。公开源不代表完整全站。撤回固定10节点定案，按节点数/间隔/本地出站预算核算容量；API额度与Feed访问限制分开，不把旧120硬称Feed官方总上限。正式容量/最小值需选型后明确，不能无限扩张或静默漏订阅。
多源仍须源内基线不吞主源新帖、站级去重/一次摄取、首次/恢复/重启区分。摘录2000字符、不补详情/回帖、规则无网络及旧两站语义保持。API使用/公开镜像限制与部署时效未获保证，见报告。旧站热榜分周期/自定义建议仍未批准。

## 运行与下一步

8001仍9becf75730e4e4c9accb35ed6f572529aa590c60镜像/schema0016，seekbell-local原容器/卷，digest及备份见私有local-runtime/runtime.json和按站记录。本轮仅文档检查，不重跑既有789后端/54及追加84浏览器/容器证据。待用户审阅来源选择后再回写SPEC/ARCH、收敛UI/频率/容量并实现；若迁移17先新备0016整卷和隔离验证，旧0015不能作16回退。PVE/长期部署另行授权；方案不等于实现、测试或验收。
