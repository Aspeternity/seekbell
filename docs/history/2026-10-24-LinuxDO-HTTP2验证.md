# Linux DO HTTPX HTTP/2隔离验证

日期：2026-10-24（Asia/Shanghai）。用户批准“验证一下httpx开启HTTP/2支持”。隔离验证完成，本次验证时正式依赖、产品及部署未改。后续用户已批准正式采用，实现与本机交付见2026-10-24-LinuxDO-HTTP2接入.md。

## 环境和范围

SeekBell-Dev:/home/dev/projects/seekbell，分支codex/linuxdo-integration，HEAD 4ce2dd94b7e3cce0d5cc81c26f28514a7bfb56c0，产品e1d2f21，x86_64/Python 3.12.3、httpx 0.28.1。
用uv pip --target在/home/dev/.local/state/seekbell/experiments/linuxdo-httpx-http2-20261024/deps隔离安装h2 4.4.1、hpack 4.2.0、hyperframe 6.1.0；沿用项目现有解释器/httpx。pyproject.toml、uv.lock、项目.venv及正式镜像均未改变。三个包及元数据文件合计506,633字节（约0.48MiB，不含运行后字节码），不是实际镜像增量。
实验脚本probe.py同目录，installed-packages.txt记录版本；最多5次GET、同模式来源去重，读取上轮curl实验及本轮记录共同遵守300秒挑战冷却和2秒间隔。首次执行因上轮冷却未结束而延期，未发请求；冷却结束后才开始。
当前HTTPX官方用法：https://www.python-httpx.org/http2/ ：安装可选HTTP/2依赖并显式http2=True，通过response.http_version核对实际协商协议。

## 真实请求与结果

全程新建匿名AsyncClient，无Cookie/登录/浏览器配置；trust_env=False、禁止重定向、TLS校验、10秒请求/5秒连接及15秒外层超时，RSS Accept、identity编码、SeekBell/0.1，与当前采集参数一致。复用产品collectors/http.py的public_response确保匿名请求和响应关闭；限制1MiB。H1对照只把http2=True改为False。

|北京时间|配置|来源|实际协议|HTTP/解析结果|
|---|---|---|---|---|
|07:16:18|http2=True|hot.rss|HTTP/2|200，30条解析/适配，30条热榜|
|07:16:30|http2=True|latest.rss?order=created|HTTP/2|200，30条解析/适配|
|07:16:33|http2=True|top.rss?period=daily|HTTP/2|200，30条解析/适配，30条热榜|
|07:16:36|http2=True|top.rss?period=weekly|HTTP/2|200，30条解析/适配，30条热榜|
|07:16:40|http2=False|hot.rss|HTTP/1.1|403、cf-mitigated=challenge、text/html|

所有成功响应均为application/rss+xml、无额外压缩，约65～205KiB，parse_rss/LinuxDoAdapter无diagnostic，三榜单均通过parse_linuxdo_snapshot。没有修改解析器。全部请求均无Cookie头，TLS保持验证。最后挑战后停止，无额外重试、轮询或其他来源请求；本轮5次预算用完。
HTTP/2成功请求约1.02～1.51秒；进程峰值包括Python/依赖/解析器且有波动，不用来预测正式服务内存增量。

## 结论与修复建议

当前本机环境中，开启httpx HTTP/2即可匿名读取四个RSS；同客户端、同热门地址和其他相同参数下，关闭HTTP/2仍触发Cloudflare挑战。该对照比先前跨curl/httpx比较更聚焦，支持采用httpx HTTP/2作为当前最小修复，暂不引入curl_cffi。
不能由此认定网站有明确“禁止HTTP/1.1”配置，或断言单独TLS指纹导致：启用HTTP/2同时影响TLS ALPN协商及HTTP传输特征，具体Cloudflare规则无站方日志。已有证据足以选择实现方向，不需要继续枚举指纹或请求头。
仅证明本机短时匿名可读，未验证长期运行、目标容器、重启、PVE/arm64或用户验收；正式产品仍为原HTTP/1.1配置。

待批准的正式改动：pyproject使用httpx[http2]并更新锁，仅对Linux DO请求启用HTTP/2（监控/连接测试/热榜一致）；复用现有请求预算/去Cookie/超时/大小边界，保持其他来源传输行为和MockTransport注入可测试。针对传输选择、协议可用性/回退、来源错误及取消验证，再做目标镜像匿名真实读取和保留数据更新8001。无需浏览器模拟、登录Cookie或额外服务。
此次只授权验证，不自动批准产品变更或部署；SPEC/ARCHITECTURE/DECISIONS在正式方案批准后同步。curl实验保留为备选证据，生产不加入两套兜底链。

## 证据和检查命令

/home/dev/.local/state/seekbell/acceptance/2026-10-24-linuxdo-httpx-http2/results.json、summary.json，后者含精确版本、文件体积与脚本/结果SHA256。只保存状态/允许的响应头/条数，不保存RSS正文、Cookie或用户会话。正式库、Runtime、通知未触及。

~~~bash
cd /home/dev/projects/seekbell
python3 -m json.tool /home/dev/.local/state/seekbell/acceptance/2026-10-24-linuxdo-httpx-http2/results.json
python3 -m json.tool /home/dev/.local/state/seekbell/acceptance/2026-10-24-linuxdo-httpx-http2/summary.json
~~~

以上命令只读证据，不会再次发RSS请求。本轮只有实验和文档，无产品代码改动，复用已有自动测试结果；新文档/状态检查无空白错误。
