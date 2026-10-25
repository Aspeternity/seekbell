# 当前状态

更新时间：2026-10-25（Asia/Shanghai）。阶段：V2EX范围收敛，技术方案待审。用户明确不需要具体节点，最多导航栏大类。先前千余节点配置/目录方案退出当前推荐；本轮仅调研、9次匿名页面/Feed元数据读取与文档，不改产品/数据库/运行，尚未批准开发。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发并复核。分支codex/v2ex-plan，本轮起点79c0940（文档），产品来自main 987beda。仅本地文档提交，不推送/合并新方案。此前PR #2合入main 5cdf5bd，CI head d94958d及两架构过，证据在合并记录。无多代理，不动D盘/旧Ubuntu/全局WSL/8000/4175，无新公开镜像、远程部署或真实试发授权。原已有PROJECT_STATE候选网站咨询段未提交，本轮原样保留且不夹入提交。

## 优先读取与最新证据

先读[导航大类修订](history/2026-10-25-V2EX导航大类方案.md)；[数据源对比](history/2026-10-25-V2EX数据源对比.md)与[10月24日旧方案](history/2026-10-24-V2EX接入方案.md)仅按需复用事实/一致性风险，不再执行节点配置推荐；热榜两旧站优化仍独立待批。实施需读collectors/rss.py、collection/ingestion/source_probe/request_budget、模型/规则/任务范围。
本机首页确认8个常规tab：tech/creative/play/apple/jobs/deals/city/qna；最热/全部/R2另为导航，VXNA指/xna。按官方规则各读一次分类Atom：技术/创意/好玩/Apple/城市均200且50项，问与答200且40项；酷工作ReadTimeout、交易ConnectTimeout，未重试、未通过。成功6源无逐帖category，作者本站member URI/内容齐备，缓存声明300秒；全部updated降序但published非降序，含早期主题，不是纯新帖列表。
私有acceptance/2026-10-25-v2ex-navigation-scope下navigation-links.json与category-feed-metadata.json只留元数据，未存正文/用户名/帖子ID，无持续轮询。此前节点API10/Feed50、原目录1378等证据保留，不再据此增加节点功能。

## 当前方案与关键未决

范围已确认：仅导航大类、不开放具体节点。候选8类用固定小多选，不做全目录/搜索分页/目录缓存；网站不加总范围。新帖拟按任务所选tab合并共享Atom来源，热门仍hot.json独立；latest API不默认增加，不能凭node映射tab。全部/最热/R2/VXNA不机械作为普通分类；最终清单、来源与频率待审。成功源可讨论5分钟错峰，不是时效承诺。
技术未完成：updated流会回复顶旧帖，不能仅靠Seen判断新帖；首次/恢复基线、带缓存延迟容忍的发布时间窗口/游标须设计验收。长期开启后，首次见到的旧主题也不能当新发。跨类归属必须集合化，后到分类不能吞掉先前启用任务的匹配，新任务不补扫历史，目标仍去重。6源成功不等于8源通过；先补jobs/deals有限核验及新帖语义准入，不能静默改回逐节点或活动提醒。
SPEC只记录确认范围，技术仍待审；Atom显式安全解析保持XML约束、纯规则、最多2000字符摘录、不补详情/回帖及旧两站语义。无新依赖/服务/Token/浏览器，授权不扩大。

## 运行与下一步

8001记录仍9becf75730e4镜像/schema0016、seekbell-local原容器/卷，digest/备份见私有local-runtime/runtime.json和按站记录；本轮无运行修改，不宣称新验收。未重跑既有789后端/54及追加84浏览器/容器证据。下一步收敛新帖判断与跨类任务事件语义，再定源/频率/容量并申请开发审批；若迁移须新备16整卷并隔离验证，旧15不能作16回退。PVE/长期部署另行授权。
