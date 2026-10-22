# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5用户实测修正。ui-restore-5已公开发布并匿名拉取通过，待用户更新实机验收。

## 环境、代码与授权

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。当前main，镜像代码基准c8be41c9a1f85650be6447e773b73a204dba9b88（实现b7ae06e907977cc3f4189bad8414cbbc7b9855aa），其后仅发布回执/Compose文档提交；原功能分支保留。用户明确要求发布新镜像供实机测试，授权必要合并/推送、公开GHCR发布及临时开关；不代部署、不真实采集发送。源码private、包public，不组织多代理；原D盘/Ubuntu/全局WSL不动。

## 实现与边界

通知管理四标签正确透传路径，当前态/切换/前进后退/刷新正常。文字输入/原生下拉改自身细边框与浅阴影，搜索由外壳统一反馈、内部填满；按钮/链接/复选单选保留键盘焦点，标题无外框。正式/演示概览与任务列表共享点击保护，信息格与空白打开配置；开关/状态区/按钮、修饰键和拖选文字独立。原UI布局/比例保持，稳定约定见UI_DESIGN。

前轮删除确认仅列无目标任务，确认后解除引用、无目标者暂停并保留规则/历史；RSS联合范围缺摘要按标题判断；TG去两Emoji、发布时间、真实预览与整卡配置（保留SEEKBELL）均包含。历史不回算不补发，本轮无数据库/接口语义改动。

## 验证与发布

[本轮实现/命令/证据](history/2026-10-23-通知导航焦点与概览任务行修复.md)。修复前新增三例均准确复现；本地正式UI8项32.8秒、history4项19.1秒、原型44项45.2秒共56浏览器及两版类型/构建/格式通过，桌面/手机截图已核对。新增UI套件与管理员轮换使用独立临时服务，未放宽产品登录限流。

[最终工作流](https://github.com/Aspeternity/seekbell/actions/runs/39847575735)同SHA完整616后端/88浏览器、类型/格式/隐私、wheel/迁移、容器持久化/锁、加密恢复/升级回退/隔离TLS，以及原生amd64/arm64通过；复用已测归档发布，发布后digest拉取再验容器。均独立库与模拟服务，不等同真实论坛/通知、Safari/手机真机验收。

当前ghcr.io/aspeternity/seekbell:ui-restore-5，索引sha256:089289552719774057aa527bbd055e7c33370e6cc5c1811c0da4583b0675f7ff。空Docker配置实际匿名拉取amd64并核对代码/UID/两平台manifest/config；arm64运行证据来自原生CI。五旧标签ui4/ui3/ui2/ui1/ui-fix-1 digest未变，临时发布开关已恢复原缺失。回执/匿名JSON在本轮记录旁，原始日志/ZIP在/home/dev/.local/state/seekbell/releases/ui-restore-5。

## 保护与下一步

Compose已更新，8001:8000与seekbell_compare_data沿用原Stack/卷，禁双实例共用SQLite卷。保护18081项目seekbell-acceptance-b45fc2c-20261020及容器/卷/backup-local、旧Stack/卷/8000/4175/18080；本地5174/8012/8019已退出，未代部署。仅NodeSeek。无外部阻塞，下一步用户重新拉取/更新原Stack，验收四标签、完整焦点与整行交互。交接读本状态/本轮记录，发布维护按IMAGE_RELEASE。
