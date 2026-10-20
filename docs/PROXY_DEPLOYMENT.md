# 外部HTTPS反代与只读部署检查（M4第四子阶段）

应用保持单容器，HTTPS证书由已有外部代理处理；本阶段只提供Nginx示例及本地隔离验证，不申请域名/证书、不更改现有代理/防火墙，不代表PVE或公网部署完成。直接本机HTTP仍可登录；后端默认仅绑定127.0.0.1。模板为deploy/nginx.conf.example，修改保留域名、证书路径和上游端口后由操作者核对，不可原样当作公网可用配置。

## 明确的代理信任

默认SEEKBELL_TRUSTED_PROXY_IPS为空，所有转发头忽略。启用时填代理连接在**应用内实际看到的TCP来源IP**，多个用逗号；仅确切IPv4/IPv6地址，拒绝星号、CIDR、主机名、未指定/组播地址及带zone的IPv6，最多32个。不要猜Docker/rootless的来源地址，也不要把整个桥接网段设为可信。来自同一可信IP的本机进程共享这个信任边界；应用端口仅对受信本机开放。

ASGI层统一调用已锁定Uvicorn ProxyHeadersMiddleware，Docker和本机Uvicorn入口继续--no-proxy-headers，避免在两个位置重解释。只在来源匹配时读取X-Forwarded-Proto/For；HTTPS请求的登录/预会话Cookie为Secure、HttpOnly、SameSite=Strict，同源CSRF沿用。不要另加Uvicorn --proxy-headers、FORWARDED_ALLOW_IPS=*或依靠客户端转发头改协议。

Nginx模板保留Host中的非默认端口，覆盖X-Forwarded-Proto与单边缘X-Forwarded-For，清除其他伪造的转发头；站点根路径部署，不提供子路径挂载。本阶段不配置多级CDN/多跳代理。证书不进入应用容器。不要公开应用后端来绕过代理边界。

## 配置与检查命令

在已确认的SeekBell-Dev正式目录。下面项目名seekbell-test、代理IP和域名均是示例；不能用于覆盖当前18081验收实例。固定镜像须已构建/加载，不自动拉取或升级日常实例。仅在得到实际部署授权后应用到目标环境：

~~~bash
export SEEKBELL_IMAGE='seekbell:已验证的固定完整提交标签'
export SEEKBELL_TRUSTED_PROXY_IPS='192.0.2.10' # 替换为应用实际看到的代理IP
# 审阅合成后的配置，不输出/复制真实环境配置到Git。
docker compose -p seekbell-test -f compose.yaml -f compose.proxy.yaml config
# 初次部署/切换须另按维护授权执行；此处不自动启动日常配置。
~~~

外部Nginx将模板作为http{}中的站点配置包含；HTTPS证书由用户现有证书流程供给。先nginx -t再由操作者应用/重载，不改变全局WSL或既有代理。模板关闭访问日志，错误只记crit，不开启debug/请求体/凭据Header日志；应用原生/镜像入口关闭Uvicorn访问日志，业务固定代码诊断保持原有脱敏。用户自定义日志/多级代理另行核对。

上传最大2049MiB，留足2GiB数据库加封装/元数据空间；proxy_request_buffering/proxy_buffering关闭，避免大文件与流式取消被代理缓存；不缓存API、不自动重放请求，上传间隔超时300秒、响应等待600秒。应用仍执行自身实际字节和300秒总上传限制，数据库快照自身120秒上限，不把代理配置当替代校验。

部署检查只执行Docker inspect和无Cookie的GET（live/ready/version/auth/status），不登录/初始化/改配置/迁移/发消息；匿名预会话Cookie只用于验证属性，不落盘/输出。URL不允许账号、查询参数、片段或子路径，拒绝重定向；禁用环境HTTP代理，TLS验证保持开启，CA文件只用于明确受信私有CA。

~~~bash
python3 scripts/check_deployment.py --project seekbell-test \
  --url https://seekbell.example.test --revision "$SEEKBELL_REVISION"
# 若使用私有CA：
python3 scripts/check_deployment.py --url https://seekbell.example.test \
  --revision "$SEEKBELL_REVISION" --ca-file /可信私有路径/ca.crt
# 本机直接HTTP检查：
python3 scripts/check_deployment.py --project seekbell-test \
  --url http://127.0.0.1:8000 --allow-http --revision "$SEEKBELL_REVISION"
~~~

--project核对固定版本、单容器、10001/只读根/丢弃权限/禁止提权、/data命名卷及127.0.0.1端口、标准入口和显式代理信任；--url另核对证书链/主机名、live/ready、代码版本、Cookie协议属性及no-store。只传其中一个参数只覆盖对应检查。HTTPS预会话Cookie没有Secure时，应检查实际代理来源IP、转发协议和Host/端口，不使用全信任通配绕过。检查成功不证明真实RSS/四渠道能收信。

## 与版本切换配合

发布维护工具会记录并重新应用原实例的SEEKBELL_TRUSTED_PROXY_IPS，切换/回退均作为匹配部署配置的一部分校验，避免更新镜像后悄悄失去HTTPS。compose.release.yaml为其提供显式环境配置；维护前仍先停服，按RELEASES执行。Compose配置指纹发生变化时，旧维护状态会拒绝操作，不要手改状态绕过；应使用该状态对应的已审阅配置/工具执行回退，或另行制定迁移方案。

## 本地自动演练

~~~bash
uv run --frozen pytest -q tests/test_proxy.py tests/test_management.py tests/test_administrator.py tests/test_release.py
# 已加载的固定应用镜像与精确Nginx镜像：
docker pull nginx@sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5
python3 scripts/check_proxy_container.py "$SEEKBELL_IMAGE" --revision "$SEEKBELL_REVISION"
SEEKBELL_IMAGE="$SEEKBELL_IMAGE" SEEKBELL_REVISION="$SEEKBELL_REVISION" pnpm --dir frontend test:proxy
~~~

演练独立Nginx1.30.6、一次性应用/数据卷，network internal无外网路由；Docker的internal网络不发布端口，因此测试以仅绑定127.0.0.1的字节中继经docker exec连接Nginx，TLS仍在Nginx终止，不开放容器外网。临时CA/私钥由cryptography生成在临时卷，CA不装系统信任库、私钥不写Git。Python检查通过指定CA验证真实TLS，并验证未知CA拒绝；浏览器只在该本机临时证书场景使用ignoreHTTPSErrors，不能据此宣称浏览器已验证生产证书。检查包括真实HTTPS初始化/登录/同源拒绝/退出、流式备份往返、直连伪造代理头忽略及样本秘密不进日志。桌面/手机分别验证Secure Cookie、刷新/保存/重登。finally只清本轮资源，不接触现有验收实例。

依据：[Uvicorn代理头](https://www.uvicorn.org/deployment/)、[Nginx转发/缓冲](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)、[Nginx上传大小](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size)、[Nginx TLS](https://nginx.org/en/docs/http/ngx_http_ssl_module.html)。具体行为以本仓锁定版本与自动证据为准。
