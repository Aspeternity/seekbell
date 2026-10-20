# 当前状态

更新时间：2026-10-20（Asia/Shanghai）。M0～M3已交付实现与本地自动验证；当前M4部署恢复，第四子阶段外部HTTPS/部署检查本地验证完成。整体M4和M5实机/用户验收未完成。[本阶段证据](history/2026-10-20-外部HTTPS反代与部署检查.md)，[前阶段](history/2026-10-20-HTTPS开发前状态.md)。

## 环境与代码

只在SeekBell-Dev、/home/dev/projects/seekbell开发，原Ubuntu显式wsl.exe派发。[入口](DEVELOPMENT_ENVIRONMENT.md)。分支codex/frontend-backend-integration；应用/镜像代码faa991d93c45a7bd42cc344ea57ed8efbe93d680，其后仅测试设施/只读检查兼容及验证文档。本次后续提交保留这些修正，无新产品依赖/迁移。原D盘/Ubuntu工具和全局WSL未改。

## 本阶段与证据

精确可信代理IP默认空，禁止通配/CIDR/主机名；ASGI层统一处理，Uvicorn外层关闭代理头及访问日志。Cookie/CSRF按可信HTTPS和Host端口处理，直接HTTP可用。外部Nginx示例支持流式备份、不缓存/重放。部署CLI只读Docker及无会话GET，严格验TLS/版本/健康/Cookie，不登录/改配置/发消息。发布工具切换/回退保留代理配置。[真实命令与边界](PROXY_DEPLOYMENT.md)。

独立WSL全量433项108.70秒，新代理20项及后续只读检查补测20项1.16秒通过；Ruff/锁/wheel/前端类型构建格式/隐私noreply通过。真实TLS桌面/手机及退出清理复验2项7.7秒通过；未改其他UI，复用原证据。远程CI未跑。

Rootless/amd64镜像seekbell:proxy-local，代码faa991d，image ID sha256:9c4c944742ff7181a00fd8cc8868f34151f52c81c9f116ef374f725946c9717b，未发布。固定Nginx1.30.6 digest见证据：内部无外网路由网络、临时CA、真正TLS终止于Nginx，主机只用回环加密字节中继；严格链/主机名/未知CA拒绝、HTTPS认证/同源/流式备份、伪造头和秘密日志样本通过。浏览器仅临时证书忽略未知CA，不能当生产证书验证。带非空代理设置的禁外网升级/失败/显式回退及网页副本切换也通过，仅清本轮资源。浏览器以SIGTERM/宽限期退出，复验后本轮容器/卷/网络均无残留。

## 原验收实例保留

项目seekbell-acceptance-b45fc2c-20261020，容器后缀-seekbell-1、卷后缀_data，镜像seekbell:backup-local（b45fc2c），http://localhost:18081/。未替换/重置/代用户操作。旧seekbell-acceptance不兼容卷保留、旧容器已停；勿复用旧名/改迁移号或覆盖试验。旧4175/18080未动。[故障记录](history/2026-10-20-本机验收启动修复.md)。

## 下一步与恢复

下一步M4的GHCR/amd64+arm64构建发布流程与部署核对，无开发阻塞；实际推送/发布/部署另需授权。再进入M5的PVE实机、真实RSS/四渠道收信、Safari/真机页面、运行观察和用户验收；确认后正式发布。[阶段顺序](ROADMAP.md)。实际目标代理/证书、原生arm64、跨版本加密恢复仍未验证。恢复/回退可能重复发送，保留原卷、不得直接降级新库。

恢复读AGENTS、本状态、PROXY_DEPLOYMENT；按需读RELEASES、代理/部署/发布脚本和专项测试，不全仓重读。

## 授权

用户要求下一步本地开发并说明阶段；沿用独立WSL/noreply。不推送/合并main、不组织多代理，不执行真实发送/远程部署/公开发布/原环境清理/全局WSL变更。用户验收实例及之后配置须保留。
