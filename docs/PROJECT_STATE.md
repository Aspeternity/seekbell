# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5实测修正。上一轮6ee4af9已交付8001；用户实测仍报通知首次打开闪烁、版块折行及下拉截字，现已隔离复现并提出补修方案，待审批；统计数字仍不加点击。

## 环境、代码与授权

唯一开发SeekBell-Dev:/home/dev/projects/seekbell，原Ubuntu通过wsl.exe派发；[入口](DEVELOPMENT_ENVIRONMENT.md)。分支codex/content-loading-and-source-time，产品6ee4af938813dcc57d8e0a417fd8ccc0a2c741aa，随后仅交付证据文档；无未提交产品改动。

用户要求今后代码更改先审批，本轮[方案](history/2026-10-23-下拉与全站加载审查待审批.md)已批准；沿用保留数据更新同一8001授权。保留原UI/统计口径，数字不加点击。无推送、公开发布、远程部署或真实发送授权，不组织多代理，不动D盘副本/旧Ubuntu/全局WSL。

## 实现与证据

[统一修复记录](history/2026-10-23-全站下拉与加载稳定性统一修复.md)：四日期反复开关修复；15处原生下拉及网站选择归并AppSelect/usePopup，关闭库字体重置、聚焦只滚动菜单；通知/设置保留外壳。ReadRegion统一稳定占位及延迟覆盖反馈，旧条件完整快照标注并禁交互，新数据/统计/分页同时替换；写后过期与身份清理分离。删除WebsiteSelect/readHeight重复补丁，后端/数据库/规则不改，SPEC/UI_DESIGN/ARCHITECTURE已回写。

SeekBell-Dev、6ee4af9：15组Chromium桌面/手机仿真74项，类型/生产构建、Prettier/Ruff/隐私/diff、截图核对及禁外网镜像检查通过。覆盖16选择器、四日期、通知菜单/筛选、慢网/失败/重试/迟到响应/写后刷新及退出。后端未变，复用b009317的669项结果。证据/home/dev/.local/state/seekbell/acceptance/2026-10-23-shared-controls-loading；测试仅临时合成服务/库。Safari/手机真机/读屏及用户验收未完成。

## 最新反馈审查（待审批）

[补修方案](history/2026-10-23-通知冷进入与下拉宽度补修待审批.md)：首次无缓存时ReadRegion灰条未延迟，快速响应仍显示1帧；空结果区域242→316px。110px菜单遇经典滚动条时“全部版块”折两行，闭合框还残留26px原生箭头留白，Telegram Bot可用50px/需63px而页面有大量余宽。方案为通知首屏预读与目标就绪后完整切换、冷占位延迟、菜单独立宽度及按场景放宽控件/移除重复留白。证据acceptance/2026-10-23-first-entry-width-audit；8026合成服务已停。原产品/测试与8001未改，未将待审方案回写规格；上轮74项漏了冷占位与经典滚动条占宽，不能作为本轮验收。

## 本地实例

http://localhost:8001/（127.0.0.1亦可），seekbell-local/seekbell-local-seekbell-1、原卷seekbell-local_data；seekbell:local-6ee4af938813，索引sha256:eac7130ea44a4713cf7c1e41038a81e5fc88299c657dffa2335eeb8c5c02c485。healthy/unless-stopped/read-only，仅localhost8001。账号、任务、通知与网站配置保留，历史原卷不重置；更新前完整备份local-runtime/backups/before-6ee4af938813.tar.gz（0700/0600），文件/SHA/SQLite校验及更新后8配置表指纹一致。Windows两地址首页/ready/version/新资产已核验，原保活PID14716有效。仓库外runtime.json/compose.env已更新，b009317仅回退镜像。

单一正式前端及旧18080/18081退役已完成，旧卷归档；没有第二套运行产品。公开仍ui-restore-5，远程Stack及8000/4175未动。前轮日期范围/卡片点击/发布与发现时间及首次快照保持。

## 下一步与恢复读取

待用户审核最新补修方案，获准后实施并增加冷进入/空结果/经典滚动条及完整标签验收，再保留数据更新同一8001。恢复读本状态、最新补修审查及相关实现；管理命令沿用[本地运行](history/2026-10-23-最新代码本地Docker实测启动.md)。
