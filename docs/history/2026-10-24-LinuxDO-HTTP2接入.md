# Linux DO HTTP/2正式接入

日期：2026-10-24（Asia/Shanghai）。用户“可以 采用这个方案”批准正式采用HTTPX HTTP/2；沿用保留数据更新本机8001授权，不含推送/合并、公开发布、远程部署或主动真实通知。

## 实现

collectors/http.py新增public_client供Runtime及HotlistService共用：精确https://linux.do mount使用http2=True且trust_env=False的AsyncHTTPTransport，默认池保持既有HTTP/1.1；传入测试transport时不创建真实mount。AsyncClient统一关闭两池，匿名public_response继续去Cookie、禁跳转并关闭响应。
pyproject.toml将HTTPX改为httpx[http2]；锁仅新增h2 4.4.1、hpack 4.2.0、hyperframe 6.1.0，HTTPX仍0.28.1。采集/连接测试共享原SourceRunner，三热榜复用同一工厂；源URL、预算/退避、规则、数据库schema及前端均未改。未引入curl_cffi/浏览器/登录会话。
SPEC/ARCHITECTURE/DECISIONS/README同步已批准边界。前因和对照证据见同日HTTP2验证及匿名客户端实验，外部资料见前日访问诊断。

## 自动验证

在SeekBell-Dev:/home/dev/projects/seekbell的当前实现工作区验证，代码基准4ce2dd9，最终实现提交后仅更新交付记录。后端720通过（新增4项，142.12秒），Ruff/格式/锁/隐私/wheel通过。Starlette关于未来TestClient迁移的一条既有弃用提示不属于本次故障。
新增测试分别对Runtime和HotlistService验证域名/协议路由、匿名去Cookie、关闭所有池、MockTransport完整覆盖及HTTP/1.1响应仍可解析。初版测试只替换导出构造器、未替换HTTPX内部引用，且用预读content模拟流，4项被禁网络保护/流检查正确拦下；修正测试夹具后4项通过，完整720再通过。没有放宽外网禁令或产品错误处理。
前端未改，复用e1d2f21相关84项浏览器证据；本轮不声称重新验证全部浏览器。

~~~bash
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv lock --check
python3 scripts/check_privacy.py
uv build --wheel
~~~

本轮证据/home/dev/.local/state/seekbell/acceptance/2026-10-24-linuxdo-http2-integration，含backend.log、wheel.log。后续容器/部署结果在该目录记录并在交付后补齐本记录。

## 当前交付阶段

实现与自动检查完成，镜像构建/离线容器检查/容器内真实四RSS和本地8001保留数据切换待执行。验证前不宣称正式容器已可用。
同schema0011更新仍先停服整卷备份并解包校验，独立卷纯迁移/凭据与原表/配置指纹预检，不启动Runtime；失败保留新卷归档并恢复原镜像/备份。不能以旧0010镜像直接读0011。
