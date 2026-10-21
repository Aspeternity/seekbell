# 当前状态

更新时间：2026-10-22（Asia/Shanghai）。M0～M3实现/本地检查完成，M4工程退出通过；现M5用户实测修正。采集卡/异常定位及任务网站下拉已修复，并按用户本轮“发布镜像”授权公开发布ui-restore-2；UI/真实环境验收待用户更新反馈。

## 环境与基准

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发；[环境入口](DEVELOPMENT_ENVIRONMENT.md)。当前main，镜像代码820dc29ce517d89423cc2323eb1b95b0fe621737（正常合并，功能实现d23413d、交付4731476）；后续仅发布记录/Compose注释，不改变代码基准。原codex/collection-card-task-picker分支保留。旧D盘/Ubuntu/全局WSL保留，不组织多代理。

## 已确认与实现

原UI及后来明确批准调整为准；采集卡以1475f5a原稿/用户第一张截图单独校准。fd711e7改成列表后44c5359/上轮cf2706f沿用导致偏离，[根因](history/2026-10-22-采集状态卡片基准核对.md)与UI_DESIGN已纠正。
单站原卡无切换；多站左下/右下箭头，标题旁总数/异常，右上当前站状态；一个异常直接定位、多个小浮窗选择。间隔/保存时区本日首次发现/最近30次取真实配置与记录，缺失灰槽、暂停独立；刷新保留选择，诊断折叠保留卡下。本日计数取耐久SeenPost首次发现，独立于可读内容保留及趋势24h/7d；30次条只含SourceRun，不混入连接测试SourceProbe。失败/未知和缺失分开，不补全绿。任务下拉统一暖橙样式并补22px间距，已修正110%下菜单再次放大，既有任务归属锁定。
无依赖/迁移/适配器/调度/规则/通知变更。保留全局110%、导航顺序、概览无创建、退出/入口收敛、无模式标签绿点、固定任务开关/行编辑/铅笔及通知时间格式；TG紧凑提案未执行。真实认证/历史/分页/加密恢复保留，不擅自融合UI。

## 发布与证据

公开ghcr.io/aspeternity/seekbell:ui-restore-2，索引sha256:b6fc9f5ebbe16d88d93ef2b16c3a72423e06761cad30fdd0d3638fa6f9d5cab6。Actions39691369507全部成功：547后端（143.91秒）/70浏览器、格式/类型/构建/迁移、禁外网容器持久化/备份恢复/升级回退/HTTPS，以及amd64+arm64原生/发布后固定digest检查。空Docker配置实际匿名拉取amd64成功，revision/用户及两平台manifest一致；旧ui-restore-1/ui-fix-1未变。源码private/包public，关联not-reported；临时发布开关已DELETE/GET404恢复原缺失。[发布/回执/匿名证据](history/2026-10-22-采集卡修复镜像发布.md)，[实现与本地证据](history/2026-10-22-采集卡与网站选择实施.md)。

## 部署、保护与下一步

对比模板deploy/compose.portainer.compare.yaml已指新标签，仍8001:8000及独立seekbell_compare_data卷，配置校验通过；已有对比实例保持原Stack名称/卷并重新拉取。旧原模板/8000不动，禁止两个运行实例共用SQLite卷。同IP跨端口Cookie共用，比较新版可用独立浏览器/无痕窗口。
保护18081的seekbell-acceptance-b45fc2c-20261020项目/容器/卷及backup-local、旧Stack/卷/4175/18080；无远程部署/真实发送/公开源码。只在临时合成库验证；多站测试不代表新增内置网站，当前仍仅NodeSeek。Safari/真机未验收。
无外部阻塞；下一步用户在Portainer更新并实测卡片/下拉后反馈，不能把发布成功等同用户验收。交接读本状态、UI_DESIGN卡片段、实施/发布记录，再按影响范围读代码；旧阶段资料按需读。
