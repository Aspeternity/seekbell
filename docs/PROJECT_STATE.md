# 当前状态

更新时间：2026-10-21（Asia/Shanghai）。M0～M3实现/本地检查完成，M4工程退出通过；当前M5用户Portainer实测修正。本轮通知时区与Telegram排版已实现/自动验证，尚未发布新镜像，真实接收待用户验收。

## 环境与代码

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。codex/ui-content-readability基于main/origin e7b5d81；a42b02d包含主内容1.1倍/概览移除创建，f7f84ca为入口收敛/侧栏退出。本轮通知代码、检查、DisplaySettings/SPEC/ARCHITECTURE与状态同提交，未推送/合并。原D盘、全局WSL和18081验收实例未动。

## 当前通知修复与证据

用户反馈UTC正文与网站时区不符并要求优化Telegram样式。根因为render直接输出RSS UTC ISO；现于自动认领/目标测试/手动重发/告警认领读取保存时区，向发送副本加入display_timezone。旧队列兼容，重试/重发按本次准备时区；不改原消息/UTC数据/去重，Webhook仍原版本机器时间。发布缺失时用发现时间并标明；正常时间展示日期/时分秒/IANA名，已发送不改写。

TG使用普通文本+结构化bold实体、分组信息、原帖按钮和可选摘要；不解析外部HTML/Markdown。UTF-16逐段及4000总限长，按钮不截断，保留话题/关闭预览和故障分类。Bark/SMTP共用时间格式，无依赖/迁移。[完整实现与证据](history/2026-10-21-通知时区与Telegram排版.md)。

本轮相关后端214项31.12秒通过；四渠道真实队列/Registry/模拟HTTP及SMTP补强后10项1.04秒通过（含于上述范围）。时区/DST/跨日/缺失值、旧队列重试、测试/重发/告警、字面标记/emoji/长度/按钮及机器时间均覆盖。前端类型检查/Vite构建、Ruff/Prettier/diff通过；桌面/手机system浏览器4项14.4秒通过。合成排版示意来自实际生成JSON，截图已检查，不等同Telegram实测；未访问真实RSS/发通知。

## 既有UI与镜像

f7f84ca的入口/退出等48项浏览器证据仍适用：[尺寸记录](history/2026-10-21-内容区尺寸与概览入口.md)、[入口记录](history/2026-10-21-入口收敛与侧栏退出.md)。偏好/管理员统一从设置管理，左下账号仅展示且独立退出，顶栏头像及概览网站行重复跳转移除，内容/投递详情入口保留。

已交付公开ghcr.io/aspeternity/seekbell:rss-fix-1代码e658b465159a24800887c30de5a645831615301b，Compose仍指此版本，不含本轮UI/通知修改。digest/528后端/64浏览器/双平台原生/TLS/匿名拉取见[发布记录](history/2026-10-21-RSS修复镜像发布.md)。发布开关恢复缺失、源码private。18081项目seekbell-acceptance-b45fc2c-20261020及其容器/卷/backup-local保留，旧卷/4175/18080/已有镜像不动。

## 下一步与授权

交付修复与样式示意，按用户后续授权决定新镜像交付；真实Telegram/其他渠道、目标环境、Safari/真机待验收。用户已批准UI入口及账号退出、明确要求本轮通知修复；无需重复审批。此前RSS发布授权已完成，本轮无新公开发布/合并/远程部署/真实发送/源码公开/正式Release授权。独立WSL/noreply，不组织多代理。恢复读AGENTS、本状态、本轮通知记录，按需读渲染/四个发送入口与SPEC/ARCHITECTURE。
