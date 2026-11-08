# 当前状态

更新：2026-11-08（Asia/Shanghai）。

## 开局

正式环境为SeekBell-Dev的`/home/dev/projects/seekbell`，先运行`python3 scripts/dev_status.py`。本轮会话直接运行在SeekBell-Dev；基于main `e9a1dd8`（v0.6.5），工作分支`feature/about-page`，版本已改为0.7.0。

## 计划位置

M0–M4完成，v0.6.5已发布，镜像digest/CI见[发布记录](history/2026-11-08-v0.6.5每周旧榜保留7天.md)。用户先前确认实例0.6.4，本次截图显示0.6.5，未核验实例digest。M5真实RSS、四渠道和恢复验收未完成。既往证据见[阶段归档](history/2026-11-08-关于页整改前状态.md)。

## 进行中

用户确认：关于与诊断拆为“诊断”“关于”两个同级标签，先做关于，诊断暂不改（原服务状态/当前故障/事件记录/诊断摘要原样移到`DiagnosticsSettings.vue`）。决定已写入SPEC设置段、UI_DESIGN末节；诊断重构仍按[完整方案](plans/2026-11-08-关于与诊断重构方案.md)待审，讨论见[历史](history/2026-11-08-关于与诊断方案讨论.md)。

`feature/about-page`实现（随v0.7.0版本PR提交）：
- 后端：`services/about.py`+`GET /api/manage/about`（需登录，只读；版本/提交/迁移、支持网站、时区、启动时间`app.state.started_at`、Python/系统/容器、数据库+磁盘），`/api/version`不变。
- 前端：重写`AboutSettings.vue`（用户嫌初版丑，已改为品牌头图+链接卡+系统信息图标块，按用户要求不放“历史与存储”链接，视觉见UI_DESIGN末节），新增`DiagnosticsSettings.vue`；Icon新增book/database/cpu/message；Settings/App路由加`diagnostics`；告警页“查看告警记录”指向诊断；workspace.css关于样式重写；帮助文案与README同步。
- 测试：pytest新增about用例（含未登录401），与diagnostics共2项通过；改live/about、system/settings、system.spec、approved-ui、ui/workspace。最终构建上live/about 2、system 20、approved-ui 8、ui 8全部通过（桌面+手机）；全量交给CI。截图见`frontend/test-results-live/`（全页截图中固定侧栏/跳转链接错位是截图模式伪影）。

用户另说明：系统设置其他各页后续都要优化，逐页确认后再改。

前轮方案、两份历史归档、v0.6.5回执改动随本PR提交；`assets/brand/`图标仍未提交（未接入，待审）。

## 下一步

1. v0.7.0发布进行中：分支`feature/about-page`的PR合并后自动发版；用一次`gh run watch`等待“Versioned images and manual candidates”，失败只看失败job日志。完成后把镜像digest/Release写入history回执，并把本节进行中内容移入history。
2. 诊断重构：审阅完整方案的日志策略/状态范围/默认值后再实施；系统设置其他页逐页确认后优化。
3. 热榜真实观察、旧卷核实；图标采用与M5实机验收待推进。

## 授权

用户授权提交、开PR并发布v0.7.0版本与镜像（本次用完即止）；无部署实例或真实发送授权。实例只读命令的既有授权为用户本人执行。

## 按需读取

- 本任务：SPEC设置段、UI_DESIGN末节；AboutSettings.vue、DiagnosticsSettings.vue、Settings.vue、services/about.py；诊断重构另读docs/plans完整方案、CurrentFaults.vue、SystemEventLog.vue、api/management.py diagnostics、db/models.py、services/{collection,hotlists,runtime,delivery}.py。
- 发布/实机：IMAGE_RELEASE正式发布段，v0.6.4/0.6.5记录、ROADMAP当前阶段、ACCEPTANCE；图标见assets/brand/README.md。
