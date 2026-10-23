# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5实测修正。用户已批准全站下拉/日期重点击/加载闪烁统一修复，产品代码完成，72项浏览器回归通过；正在检查、提交及更新本地8001。统计数字仍不加点击。

## 环境与授权

唯一开发环境SeekBell-Dev:/home/dev/projects/seekbell，原Ubuntu通过wsl.exe派发；[入口](DEVELOPMENT_ENVIRONMENT.md)。分支codex/content-loading-and-source-time，HEADd1476f3为审批前文档，最后产品b0093170943925ca058689ec62e0f8cc74fbb1e4。本轮改动未提交：frontend/src共用弹层/选择/读取缓存及相关页面、tests/新workspace-stability配置、CI/README和本轮权威/交接文档，均为已批准范围。

用户要求今后代码改动先审批；本轮批准见[审查](history/2026-10-23-下拉与全站加载审查待审批.md)。保留现有UI/统计口径，不加数字点击；沿用保留数据更新同一8001的本地Docker授权。无推送、公开发布、远程部署或真实发送授权。不组织多代理，不动D盘副本/旧Ubuntu/全局WSL。

## 当前实现与验证

[统一修复记录](history/2026-10-23-全站下拉与加载稳定性统一修复.md)：四日期重复开关修复，15处原生select和网站选择统一AppSelect/usePopup；关闭库字体重置，聚焦只滚动菜单。通知/设置保留外壳；ReadRegion统一稳定占位、延迟覆盖反馈，列表保留完整旧快照且禁旧条件交互，新结果同时替换；写后过期与身份清理分离。移除WebsiteSelect/readHeight重复补丁，后端/数据库/规则不改；SPEC/UI_DESIGN/ARCHITECTURE已回写。

SeekBell-Dev、当前工作区正式前端：14组桌面/手机仿真72项通过，覆盖全部16选择器、四日期、冷进入/返回/慢网/错误/快速切换/写后刷新及退出。证据acceptance/2026-10-23-shared-controls-loading（完整私有路径见修复记录）。复用未改后端b009317的669项证据。类型/生产构建、Prettier/Ruff/隐私/diff及截图核对通过；镜像/容器、TLS代理和Docker更新待收尾。合成测试不碰真实库；Safari/手机真机/用户验收未完成。

## 本地实例与保留事项

http://localhost:8001/（127.0.0.1亦可），seekbell-local/seekbell-local-seekbell-1，原卷seekbell-local_data。仍运行seekbell:local-b00931709439，索引686ad9d34063f71acb15e7e374bb275abe726794b2783c2c7309e4703f1f622f；healthy/unless-stopped、仅localhost8001。真实账号/任务/来源启停/历史保留，严禁重置。原卷完整备份before-b00931709439.tar.gz、8配置表指纹及Windows两地址验证见[前轮交付](history/2026-10-23-统一日期范围与内容交互修复.md)。仓库外local-runtime/runtime.json和compose.env管理实例，保活WindowsPID14716未改。

单一正式前端/旧18080与18081退役已完成，旧卷已归档；e3等旧镜像仅回退用，无第二套运行产品。公开仍ui-restore-5，远程Stack及8000/4175未动。前轮日期范围/卡片点击/发布时间与首次快照保持。

## 下一步与恢复读取

代码/状态同提交后构建新镜像，隔离容器和TLS代理检查。停同一8001做完整原卷备份、校验SQLite/文件/8配置表，再更新原卷并从Windows复核版本/健康/静态资产，记录SHA/digest后交用户实测。恢复仅读本状态、统一修复记录、相关实现；今后代码变更继续先审批。
