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

本轮证据/home/dev/.local/state/seekbell/acceptance/2026-10-24-linuxdo-http2-integration，含backend.log、wheel.log。容器/部署与Windows证据均已保存在该目录。

## 当前交付阶段

实现提交54bee56f750dfb502a8439ea1ee6acdba20d1a45。候选seekbell:linuxdo-http2-54bee56f750d构建/离线容器检查通过；镜像ID sha256:631f2a65080c75e8de8f91bc2e3d4830c36e97d7744fc33d07c8ab609aff199a，Size 281,559,293字节，比原镜像增加1,474,845字节（约1.41MiB，0.53%）。

07:35在不挂数据卷、不启动Runtime的候选容器内，通过生产Runtime的collector和HotlistService有界读取四个真实RSS，各30条、均200/HTTP/2/无Cookie；新帖适配无诊断，三榜单ready。仅四次GET、间隔至少2秒，无正式库或消息；证据container-rss.json及image-size.json，前端构建沿用同源码。07:39已完成同一本机8001保留数据切换。
同schema0011更新仍先停服整卷备份并解包校验，独立卷纯迁移/凭据与原表/配置指纹预检，不启动Runtime；失败保留新卷归档并恢复原镜像/备份。不能以旧0010镜像直接读0011。

## 本地交付结果

同一seekbell-local/seekbell-local-seekbell-1、原seekbell-local_data与127.0.0.1:8001已切换上述54bee56镜像，schema仍0011_linuxdo，healthy/read-only/unless-stopped，管理员已初始化与两静态资源保留。没有新增迁移、自动安装/启用网站或改变用户配置。

停服整卷备份：local-runtime/backups/before-http2-54bee56-20261024-073950.tar.gz，SHA256 fc34a11dd391bc0899ae85729a373a6dd008adc69fe7274e242f92e35e0c1700。目录0700/文件0600，逐文件manifest/解包/SQLite检查通过；独立临时卷纯迁移后全部原表行哈希一致，密钥不变、加密凭据可解、12类配置指纹一致，未启动Runtime。正式切换后原配置指纹再次一致；临时卷已清理。证据backup-verification.json、private-data-preflight.json、deployment-result.json。
旧e1d2f21同schema镜像及备份保留，私有update-local.py具有失败候选归档和匹配整卷/原镜像恢复流程；此次没有触发回退。更早312d657/0010回退边界仍按原记录执行。

切换第一次预检在改动数据前发现旧容器反复冷启动。核实原Windows保活PID14716不存在；SeekBell-Dev的systemd服务无法独立维持发行版存活，短命派发命令退出后Docker随发行版重启。按既有本机运行方式恢复专用隐藏wsl.exe sleep进程，PID32480、创建2026-10-23T23:39:27.9859010Z，身份/创建时间已核对，未改全局WSL或旧Ubuntu。记录windows-keeper-restored.json及runtime.json。启动命令的跨shell变量转义已修正；没有修改Windows执行策略。

Windows对localhost与127.0.0.1的8001首页、ready、完整实现SHA/0011版本及两资源均通过；保活身份符合预期。证据windows-after-update.json。实际界面/用户验收及长期运行、PVE/arm64仍待继续，不用短时四源通过替代长期承诺。用户可刷新本机8001进行验收，按原设置添加/启用Linux DO；已有挑战预算不擅自重置。

新增容器验证命令（完全离线、合成库，不发通知）：

~~~bash
python3 scripts/check_container.py seekbell:linuxdo-http2-54bee56f750d --revision 54bee56f750dfb502a8439ea1ee6acdba20d1a45
~~~

真实RSS容器验证已按4请求完成，脚本container-rss-probe.py不自动轮询。后续需重新真实验证时应先核对来源冷却并设定有限预算，不把它放入CI。运行元数据位于/home/dev/.local/state/seekbell/local-runtime/runtime.json。
