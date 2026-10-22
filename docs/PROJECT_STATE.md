# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5实测修正。筛选/日期/通知计数修复、单一正式前端清理已提交；用户已授权并启动最新代码的本地Docker实例供实测。统计数字点击仍搁置。

## 环境、代码与授权

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。当前修复分支codex/content-loading-and-source-time，基于8bd7083；此前分支codex/single-production-frontend，最后产品实现d224853a2f24cd003ff02eafb27a1532e78e54bf；本地镜像源34aedc41ddf2d2c2cd7f5f6d1a138f83254f6b76，其后仅启动记录。保持批准UI/统计口径，不实施拒绝的改版或结果按钮组。用户已授权结构清理、旧Docker退役和最新代码本地Docker实测；没有推送、公开发布、远程部署或代用户采集/消息授权。不组织多代理，不动旧D盘/Ubuntu/全局WSL。

## 当前本地实例

[启动记录与管理命令](history/2026-10-23-最新代码本地Docker实测启动.md)：访问http://localhost:8001/（127.0.0.1亦可），Compose项目seekbell-local、容器seekbell-local-seekbell-1、独立新卷seekbell-local_data，镜像seekbell:local-34aedc41ddf2，索引sha256:22ceca76da2093a5ec3d9cd70243df934cbeff82bde385dab0228abd3cc37cc6。healthy、unless-stopped，保持运行供用户验收；首次由用户创建管理员，未载示例/旧库，不可重置其后用户数据。当前应保护此容器/卷/镜像及8001。

WSL空闲退出曾导致访问中断，现用独立隐藏wsl.exe保活，仅当前进程、不改全局设置；身份在仓库外windows-keeper.json。Windows两地址首页/ready/version通过，连续70秒/8次ready；容器启动时间保持、重启0。打包页面Chromium只读打开无错误。证据/home/dev/.local/state/seekbell/local-runtime；重启Windows后运行方式见记录。

## 实现与证据

[结构清理](history/2026-10-23-单一正式前端结构清理.md)：唯一正式入口，pages/components/styles及真实API状态；演示入口/构建/账号/备份/JS规则引擎、重复页面退役。测试用同一正式界面配临时库，离线合成运行器继续供CI；既有UI/业务/迁移不变。

SeekBell-Dev、d224853：后端659、浏览器58、类型/正式构建、Ruff/Prettier/隐私/diff、离线核心/后台/加密备份、wheel及容器/TLS通过。23个迁移组件/页面仅导入路径变化，CSS有效声明相同。证据/home/dev/.local/state/seekbell/acceptance/2026-10-23-single-frontend。包含[a7435a2筛选修复](history/2026-10-23-筛选日期与通知计数修复.md)。不冒充远程CI、真实RSS/通知、Safari/真机或用户验收。

## 退役、公开状态与下一步

[旧Docker清理](history/2026-10-23-旧Docker实例退役清理.md)已删除3容器/3卷/2网络/2镜像，18080/18081释放。旧数据归档/home/dev/.local/state/seekbell/maintenance/2026-10-23-retired-docker/archives（0600，SQLite/SHA校验），未入Git；该记录的容器清单为空是新实例启动前事实。

公开镜像仍ui-restore-5，代码c8be41c9a1f85650be6447e773b73a204dba9b88，digest sha256:089289552719774057aa527bbd055e7c33370e6cc5c1811c0da4583b0675f7ff。未更新远程Stack或8000/4175。下一步用户在8001实测并反馈；本地实例继续保留，发布/远程部署需明确指示。恢复读本状态、启动记录及受影响代码。

## 当前内容修复待本地更新

[根因/修复/验证记录](history/2026-10-23-内容加载闪烁与RSS时间核对修复.md)：查询清空数据、防抖、提示和异步控件宽度导致闪白；现内容列表保留带说明且禁交互的旧快照，原子更新统计/行/页码，固定控件和徽标几何。主时间标发布、源缺失标发现，发现日期不变，同批按发布时间排序。1002626发布05:36:15、发现07:05:41，ID/链接对应；官方RSS和当前采集成功，标题后续编辑保持首次快照。规则/队列/历史库未改。修复前失败复现、新增6浏览器、全部62正式浏览器及660后端、类型/构建/Ruff/Prettier/diff通过，证据/home/dev/.local/state/seekbell/acceptance/2026-10-23-content-loading-rss。实现与状态同本地提交；下一步固定SHA构建检查，备份并保留原卷更新8001供用户复测。
