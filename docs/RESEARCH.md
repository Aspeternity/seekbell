# NodeSeek 数据源核实记录

本记录是2026-10-18短时观察，不是官方永久契约。不要把样本数、缺失比例、延迟当作SLA。

## 本次原始RSS实测

北京时间约18:11:15与18:11:47两次请求 https://rss.nodeseek.com/ ，无需账号/Cookie，HTTP200，application/xml。两次同批20条。

- 标题、guid（数字帖子ID）、link、category、dc:creator（用户名）、pubDate：20条都有。
- description：17条有、3条缺失；最长样本158字符，明显截断，不推断固定字符上限。
- 未发现全文content:encoded或作者稳定ID。
- 最新18:10:49，最早18:01:06，窗口9分43秒；不能推广为固定覆盖时间。
- ttl=60：按RSS2.0规范是分钟级缓存提示，不是60秒。
- 响应未见ETag/Last-Modified/Cache-Control，cf-cache-status=DYNAMIC；不证明不存在内部缓存或限频。
- 未核实官方历史分页/补查接口、允许的轮询频率、所有隐藏/权限帖覆盖范围。

原始实测文件在当时临时环境生成，未作为本包稳定测试夹具分发；开发应构造无真实个人内容的合成夹具，并在获授权的运行验证中重新核实。

2026-10-19 复核：通过 `RssCollector` + `NodeSeekAdapter` 对 `https://rss.nodeseek.com/` 执行单次只读探测，返回 HTTP 200（`application/xml; charset=utf-8`），原始 20 条全部规范化通过，其中 3 条摘要缺失（`summary=None`），0 条诊断错误。

## 依据与参考

- 官方管理员推荐独立RSS域名而非主站抓取：
  https://www.nodeseek.com/post-112722-1
- RSS2.0 ttl定义：
  https://www.rssboard.org/rss-specification
- NodeSeeker Docker功能参考：
  https://github.com/ljnchn/NodeSeeker-docker
- 组合词/排除/多目标/持久化去重，README写默认10秒轮询：
  https://github.com/AI-XMLY/nodeseek-rss-telegram-bot
- 官方频道候选（首版不接入）：
  https://t.me/nodeseekc
- 网页新增内容检测参考：
  https://changedetection.io/tutorial/how-monitor-website-new-content
- 多架构镜像参考：
  https://docs.docker.com/build/ci/github-actions/multi-platform/

上列第三方项目仅作思路参考，未完成代码审计；若复用代码须核实许可证及保留义务。搜索得到的NodeSeeker API通常是第三方监控应用管理接口，不是论坛开放帖子API。

## 对首版的结论

RSS足够实现标题/摘要/用户名/版块新帖筛选；全文和停机后完整补查不能承诺。20条有限窗口要求可能漏采提示。10秒是候选产品默认（已有项目采用），不是已验证的官方许可频率。部署前核实最新说明，运行中尊重限频并退避。
