# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5实测修正。本轮筛选/日期/通知计数已本地实现并验证，未发布；数字点击按用户要求搁置。

## 环境、代码与授权

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu通过wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。本轮基于main ee3bc8d853f0b80461b1a6058a1bc91f0e2ae598，分支codex/history-filter-stability-fixes，状态与实现同提交。用户授权先修复此前批准四项及新增四项；不重设计UI、不改统计口径、不加数字点击。两套版式/新增结果按钮组均拒绝并撤回，[讨论存档](history/2026-10-23-内容筛选统一优化设计.md)不可实施。内嵌可视化通道不可用，后续用文字/实际页面截图。无本轮推送、公开发布、部署或真实采集/发送授权；源码private、包public，不组织多代理，原D盘/Ubuntu/全局WSL不动。

## 本轮实现与证据

[根因、修改路径、检查命令与证据](history/2026-10-23-筛选日期与通知计数修复.md)：任务说明对齐筛选区；统计外壳保持、读取中保留列表高度，防搜索/下拉跳动；帖子详情立即读取、反馈延迟200ms。内容/投递/手动重发/测试四处恢复“全部日期”下拉，真实日期按保存时区游标读取。网站搜索/状态同高且手机输入16px。普通任务选项排除软删除，历史快照保留；中文版块显示与原始值分离。通知共享计数/在途合并/写后更新/会话隔离，切标签不回退“—”。无迁移、规则或后台发送变更，原布局/配色/统计保持。

修复前两例复现失败已归档；最终SeekBell-Dev后端history15项、浏览器76项（正式22、演示44、合成sending4/operations6）、两版类型/构建、Ruff/Prettier/隐私/diff检查通过。覆盖实际滚动下筛选几何稳定、详情199/200ms反馈、四处日期/时区与DST、通知跨标签/失败/写后更新/注销迟到响应。新增6浏览器独立8021临时服务并接入CI，未放宽登录限流。全部临时库与模拟服务，不冒充远程CI、真实RSS/消息、Safari/手机真机或用户验收。

证据在/home/dev/.local/state/seekbell/acceptance/2026-10-23-filter-fixes；本聊天filter-fixes目录含实际页面截图副本，已核对。原始问题与批准边界见[最初审查](history/2026-10-23-五项界面问题审查方案.md)。新增截图未入Git。

## 当前公开镜像与保护

仍为ghcr.io/aspeternity/seekbell:ui-restore-5，代码c8be41c9a1f85650be6447e773b73a204dba9b88，索引sha256:089289552719774057aa527bbd055e7c33370e6cc5c1811c0da4583b0675f7ff；其后仅文档。本轮本地修复尚不在镜像内。[旧发布/匿名拉取回执](history/2026-10-23-通知导航焦点与概览任务行修复.md)及日志/home/dev/.local/state/seekbell/releases/ui-restore-5保留，旧CI616/88不作为新修复证据。

Compose沿用8001:8000/seekbell_compare_data，禁双实例共用SQLite卷。保护18081项目seekbell-acceptance-b45fc2c-20261020及容器/卷/backup-local、旧Stack/卷/8000/4175/18080。仅NodeSeek；临时测试服务已退出，未操作部署。无技术阻塞，下一步审阅修复；本轮发布需用户明确指示。交接先读本状态/本轮记录/受影响代码，发布再读IMAGE_RELEASE。
