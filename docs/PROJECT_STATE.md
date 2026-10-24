# 当前状态

更新时间：2026-10-24（Asia/Shanghai）。本轮用户要求V2EX接入方案，已核对官方资料与少量一次性匿名实源；仅文档方案，尚未开发/迁移/部署。待用户审阅API来源、内容摘录及节点交互边界。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发。方案分支codex/v2ex-plan，起点main 987beda5ea38c01e9969fb2fa684c8f970edeec0；本轮只写本状态与方案文档并本地提交，不推送/合并此新方案。先前用户授权的成品36提交已通过PR #2合入main，合并SHA5cdf5bd68d88dac53fea6e364c8fe8b2fe392db7，CI精确head d94958d及两架构检查均过；详见同日合并记录。无多代理，不改D盘/旧Ubuntu/全局WSL/8000/4175；无新公开镜像发布/远程部署/真实试发授权。

## 本任务读取与事实

先读[V2EX方案](history/2026-10-24-V2EX接入方案.md)，再看sites/registry/hotlists、collectors/rss/http、SourceRunner/request_budget及相关模型。SPEC仍只确认NodeSeek/Linux DO；本轮不把未批准建议回写为需求。
官方订阅说明blog.v2ex.com/rss，V1说明www.v2ex.com/p/7v9TEc53，V2说明/help/api。匿名HTTP/1.1本机实测：Atom index.xml为50项，无节点字段；现解析器仅RSS2，不能直接换URL。最新API本次36项均带用户名/node元数据，按created降序，是本次Atom子集；热门10项；nodes/all目录1378项约794KB；index.json为404。条数/覆盖均是时点事实，不承诺全部节点、权限内容或不漏帖。私有acceptance/2026-10-24-v2ex-proposal只留字段/计数/响应头元数据，不留正文或用户名样本入Git，实测不等于长期可用。
API有效额度头与旧120/新600文档不同，目录Reset可能来自过期缓存；Cache-Control可长达5天，不等于采集周期，也不能用帖子created冒充来源更新时间。

## 建议（待批准）

优先固定官方匿名V1列表＋独立节点目录＋官方热门：新帖120秒/最小60秒、热门600秒按需、目录24小时缓存及限频刷新，都是工程候选。每站共享采集/锁/限流，额度不足优先采集，服务器等待不可手测绕过。HTTPX现依赖足够，不加浏览器/Token/额外服务。
节点按稳定node.id存值，标题/slug用于搜索；千余项用本地缓存搜索/分页50条，不全塞workspace，候选限高/跨页保留/最多64项，任务独立全部或指定，不加网站总范围。正文仅列表附带内容转纯文本截2000字符并标“接口摘录”，不补主题详情或回复；原帖/v2ex身份/首次基线/去重/诊断/四渠道沿用，旧任务不动。热门仅一个支持项，不伪造每日/每周。候选下个迁移17须保留旧数据并备份16。
关键边界是RSS-only扩为官方只读API与内容摘录；官方API公平使用要求对个人/商业站内容填充有限制，不能凭匿名200判定授权，正式采用前须核对保存/展示用途。方案不宣称私有部署自动获许可，不做公开内容镜像。

## 运行与下一步

8001仍9becf75730e4e4c9accb35ed6f572529aa590c60镜像、schema0016，原项目seekbell-local/容器seekbell-local-seekbell-1/卷seekbell-local_data；实际digest/备份在私有local-runtime/runtime.json及按站记录。本轮无产品/数据/运行改动，未重复既有789后端/54及追加84浏览器/容器验证。待批准后再更新SPEC/ARCH、实现适配器/节点缓存/预算/UI及合成CI，实施17前新备16整卷；旧15备份不能当16回退快照。PVE/长期部署及用户验收仍独立。
