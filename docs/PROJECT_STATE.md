# 当前状态

更新时间：2026-10-19 09:36（Asia/Shanghai）。M1～M4本地开发及自动验证已完成；完成13项审查优化及Web全屏侧边栏控制台彻底重构并通过全套本地验证；M5本机统一用户验收进行中。

## 环境与基准

仅SeekBell-Dev的`/home/dev/projects/seekbell`开发；当前聊天经`wsl.exe -d SeekBell-Dev`或`\\wsl.localhost\SeekBell-Dev`显式访问，D盘交接副本不改。[环境入口](DEVELOPMENT_ENVIRONMENT.md)。私有origin `Aspeternity/seekbell`，`main`；noreply及`.githooks`沿用。

## 本轮完成的13项审查优化与控制台UI重构（第8项默认间隔保持10秒不改）

1. **后台循环自恢复**：`ApplicationRuntime._guard`捕获未预期异常后标记`failed`（readiness 503），按5～300秒指数退避自动重启循环，下一正常周期恢复`running`并记录`scheduler.restarts`。
2. **按目标并发投递与有界认领**：`DeliveryWorker.claim()`增加`LIMIT 64`并排除已有活跃租约的目标；`DeliveryWorker.run()`支持跨目标最多4路并发（同目标严格串行），消除慢目标队头阻塞。
3. **规则匹配与信息不足通知**：`Rule`新增可选`notify_on_insufficient`（默认`false`），开启后`insufficient_data`仍记`RuleHit`并入队`Outbox`（任务名附`（信息不足）`）；匹配前对帖子文本与规则词统一做Unicode NFKC与连续空白折叠；批次摄取预编译`Rule`并缓存整词正则。
4. **RSS良性`bozo`兼容与空轮询收敛**：`defusedxml`安全校验通过且`feed.entries`数量与原始`<item>`一致时，将`feedparser` `bozo`记为`feed_bozo_warning`诊断而非整批失败；无新帖、无基线/缺口/诊断的空成功轮询仅更新`SourceState`，不写`SourceRun`。单次只读探测`https://rss.nodeseek.com/`返回HTTP 200、20条合法（3条无摘要）、0诊断。
5. **系统故障/恢复告警与载荷时间统一**：`ApplicationSettings`新增可选`alert_target_id`（`0007_settings`及启动`migrate()`幂等补列），后台异常、RSS连续失败≥5次或窗口缺口单次告警，恢复时单次通知；`Outbox`与`TargetTesting`载荷`post.first_seen_at`统一为ISO 8601 UTC字符串。
6. **全屏左侧边栏控制台重构与密码长度调整**：管理员初始化与改密最小长度由15位下调为6位（6～128字符）；推翻原居中窄栏布局，重构为全视口左侧深色导航栏（`.console-sidebar`）+ 顶部状态栏（`.console-topbar`）+ 100%全宽流式工作区（`.console-workspace`），未登录态采用全屏左右分栏（`.auth-split-layout`）；`SitePanel.vue`重构为多列紧凑网站卡片矩阵（单张小卡片内融合站点身份、启停/基线标签与实时采集状态，点击卡片弹出右侧抽屉进行采集配置与RSS连接测试）；`OverviewPanel.vue`升级为6列KPI顶栏+双栏状态看板；`TasksPanel.vue`升级为左规则编辑+右实时试匹配沙盒双栏工作台；`DeliveriesPanel.vue`支持主从分栏详情检视；`SettingsPanel.vue`升级为三栏控制台。

## 当前验收实例与验证证据

本机验证通过：402项`pytest`、7项Playwright Chromium E2E（含移动端390px与桌面1280px无横向溢出、点击紧凑网站卡片展开配置抽屉）、`ruff check/format`、`prettier`、`vue-tsc --noEmit`、`vite build`及`scripts/check_privacy.py`全部通过。

本机验收实例`http://127.0.0.1:18080/`（Docker项目`seekbell-acceptance`、卷`seekbell-acceptance_data`）保持原数据卷未重置，并按最新提交重建本地镜像热更新。

## 下一步及授权

继续M5用户验收（U01～U10）或按需更新本地验收容器镜像；PVE/真实HTTPS、四渠道真实接收及原生arm64仍待统一实机验证。[操作手册](DEPLOYMENT.md)、[M5用户清单](M5_USER_ACCEPTANCE.md)。沿用本地开发、noreply、私有main推送及本机验收授权；未授权GHCR发布、远端部署或真实发送。
