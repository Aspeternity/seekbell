# 当前状态

更新：2026-11-09（Asia/Shanghai）。

## 开局

正式环境为SeekBell-Dev的`/home/dev/projects/seekbell`，先运行`python3 scripts/dev_status.py`。main `031f82a`（PR #36），版本0.7.0已发布。

## 计划位置

M0–M4完成；v0.7.0（设置拆“诊断/关于”、关于页重做）已发布，镜像digest、CI与本地证据见[v0.7.0记录](history/2026-11-08-v0.7.0关于页重做.md)；前版见[v0.6.5记录](history/2026-11-08-v0.6.5每周旧榜保留7天.md)。M5真实RSS、四渠道和恢复验收未完成。既往证据见[阶段归档](history/2026-11-08-关于页整改前状态.md)。

## 进行中

运行中心阶段一、二已实现，随v0.8.0发布PR提交（基于031f82a）：[方案](plans/2026-11-09-运行中心方案.md)第8节，SPEC 6.5.1、UI_DESIGN末节、DECISIONS、ARCHITECTURE已回写。侧栏改“通知目标/运行中心”，内容与命中、通知记录迁入，诊断页和`/api/manage/diagnostics`已删。新增`services/{operations,fault_guide,crash_records}.py`、`/api/manage/operations/*`、`pages/{Operations,OperationsStatus,NotificationRecords}.vue`、`components/{ProblemDrawer,RecordTabs}.vue`；无数据库迁移。

证据（SeekBell-Dev、最终工作区）：全量pytest 978项通过；17个浏览器套件全部通过（含新增`operations-center.spec.ts`）；ruff、prettier、typecheck、bump_version --check通过。linuxdo/backup/proxy浏览器套件留给CI。未做真实环境验证和用户验收。

其他未提交：`assets/brand/`图标（未接入，待审）。

用户说明系统设置其他各页后续都要优化，需逐页先出方案、经同意再改代码。

## 下一步

1. 等v0.8.0 CI与自动发布完成，核对Release和镜像digest并写发布记录。
2. 阶段三：内容与命中补强（方案第6节：搜索帖子链接/ID、查不到的原因、详情处理过程小结），下一版发布。
3. 程序日志做法待用户议定；系统设置其他页先出方案再改；热榜真实观察、旧卷核实、图标采用与M5实机验收待推进。

## 授权

用户授权发布0.8.0（提交、PR、合并、Release与镜像）；部署实例、真实发送未授权。实例只读命令的既有授权为用户本人执行。

## 按需读取

- 设置页优化：SPEC设置段、UI_DESIGN末节、Settings.vue及对应页面；运行中心另读docs/plans/2026-11-09方案、App.vue、pages/{Operations,OperationsStatus,NotificationRecords,Content,Records}.vue、services/{operations,fault_guide,crash_records,alerts,runtime}.py。
- 发布/实机：IMAGE_RELEASE正式发布段，v0.6.4/0.6.5记录、ROADMAP当前阶段、ACCEPTANCE；图标见assets/brand/README.md。
