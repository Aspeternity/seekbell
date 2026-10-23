# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5实测修正。上一轮四项已实现并更新8001；用户新增日期重点击、下拉UI和全站闪烁反馈，已审查复现并提交方案，待审批；统计数字点击仍搁置。

## 环境、代码与授权

仅SeekBell-Dev:/home/dev/projects/seekbell开发；原Ubuntu经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。分支codex/content-loading-and-source-time，最后产品实现b0093170943925ca058689ec62e0f8cc74fbb1e4，其后仅证据文档。

用户要求今后代码更改先审批；本轮已批准筛选截字、全部四处日期范围、帖子整块点击、移除统计区时区提示。数字不加点击，维持原UI；沿用本地Docker实测授权。无推送、公开发布、远程部署或代用户真实发送授权。不组织多代理，不动旧D盘/Ubuntu/全局WSL。

## 当前修复与证据

[修复/交付记录](history/2026-10-23-统一日期范围与内容交互修复.md)：“全部匹配结果”完整显示；内容/投递/手动重发/测试统一起止日、应用/取消/清除，与搜索和其他条件组合、回第一页。保存时区完整包含起止日，内容仍按首次发现。兼容旧单日API。卡片信息/空白可进详情，复制/独立操作不误触，标题保留键盘入口。统计区移除时区提示，实际时区不变；SPEC/UI_DESIGN已回写。

SeekBell-Dev、b009317：后端669、浏览器30（四页桌面/手机范围流、加载稳定性、截字/整块点击/时区/适配）及类型/构建、Ruff/Prettier/隐私/diff、镜像/禁外网容器检查通过。证据/home/dev/.local/state/seekbell/acceptance/2026-10-23-history-range-approved。弃用造成遮挡的内部焦点捕获，未留临时补丁。自动测试用合成服务/临时库；Safari/手机真机、真实发送和用户验收未完成。

## 本地实例

http://localhost:8001/（127.0.0.1亦可），项目seekbell-local、容器seekbell-local-seekbell-1、原卷seekbell-local_data。镜像seekbell:local-b00931709439，索引sha256:686ad9d34063f71acb15e7e374bb275abe726794b2783c2c7309e4703f1f622f，healthy/unless-stopped；仅localhost8001映射。管理员/任务/来源启停/历史保留，严禁重置。

更新前完整归档local-runtime/backups/before-b00931709439.tar.gz（0700/0600，逐文件/SQLite/SHA通过）；更新后8配置表数量/内容指纹一致。Windows两地址首页/ready/version匹配SHA，实际静态资产通过。仓库外local-runtime/runtime.json、compose.env已更新，旧e3cfbf8仅留回退镜像，没有第二实例。Windows保活PID14716仍有效；管理命令见[本地运行](history/2026-10-23-最新代码本地Docker实测启动.md)。

## 最新审查（待审批）

[审查与方案](history/2026-10-23-下拉与全站加载审查待审批.md)：日期四页连续三次点击均未关闭，捕获阶段外部关闭与按钮toggle冲突；15处/9页面原生select展开UI由系统绘制。隔离复现通知筛选20→0行、内部切换标题/导航重建；另有通知详情180ms非搜索防抖/即时提示、流内反馈位移、概览/设置/备份读取及写操作统一清缓存等共性原因。证据acceptance/2026-10-23-dropdown-loading-audit/observations.json。仅用临时合成服务，已停；没有改产品代码、重建或更新Docker。

## 保留事项与下一步

[前轮源时间修复](history/2026-10-23-内容加载闪烁与RSS时间核对修复.md)的首次快照/发布发现区分/同批排序保留；[单一正式前端](history/2026-10-23-单一正式前端结构清理.md)及[旧Docker退役](history/2026-10-23-旧Docker实例退役清理.md)已完成，18080/18081释放，旧数据已归档。公开仍ui-restore-5，远程Stack及8000/4175未动。

下一步等用户批准共用弹层/全站下拉及统一加载修复方案后实施、验证并保留原卷更新8001；当前运行仍b009317。今后代码更改继续先审批，发布/远程部署另需明确指示。恢复读本状态、最新审查及受影响代码。
