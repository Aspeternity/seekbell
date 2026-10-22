# 当前状态

更新时间：2026-10-23（Asia/Shanghai）。M0～M3完成、M4工程退出通过，M5实测修正。内容闪烁/时间展示修复已提交，保留原卷更新本地8001供复测；统计数字点击仍搁置。

## 环境、代码与授权

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。分支codex/content-loading-and-source-time，最后产品实现e3cfbf80048735b57a16ea877da517ac0429cfc5，其后仅证据文档。保持批准UI/统计口径，不实施拒绝的改版/结果按钮组。用户授权持续修复、本地Docker实测、此前结构清理/旧实例退役；无推送、公开发布、远程部署或代用户真实发送授权。不组织多代理，不动旧D盘/Ubuntu/全局WSL。

## 当前本地实例

http://localhost:8001/（127.0.0.1亦可），项目seekbell-local、容器seekbell-local-seekbell-1、原卷seekbell-local_data。镜像seekbell:local-e3cfbf800487，索引sha256:7348affa9eb9da4717b98b920b3426f8240bff7e903702018c25618520461d0f，healthy/unless-stopped，保持运行。管理员已由用户创建，账号/配置/任务/历史保留，不得重置。保护此容器/卷/新镜像及8001；旧local-34aedc41ddf2仅留回退镜像。

[启动与管理命令](history/2026-10-23-最新代码本地Docker实测启动.md)仍有效，仓库外compose.env已改新镜像。隐藏wsl.exe保活沿用，身份在local-runtime/windows-keeper.json，重启Windows后的运行方式见记录；未改全局设置。

## 当前修复与证据

[根因/修复/更新记录](history/2026-10-23-内容加载闪烁与RSS时间核对修复.md)：原查询清数据、180ms防抖、提示和异步选项宽度造成闪白。现内容列表保留明确标注且禁交互的旧快照，原子更新统计/行/页码，徽标/控件几何稳定，提示覆盖显示。主时间标发布，源缺失标发现；发现日期不变，同批按发布时间排序。1002626发布05:36:15、发现07:05:41，ID/链接相符；源采集成功，帖子编辑保持首次快照。不改规则/判定/队列或历史时间。

SeekBell-Dev、e3cfbf8：后端660、浏览器64（新增6、TLS2）、类型/构建、Ruff/Prettier/隐私/diff和容器/TLS通过；失败复现已存。证据/home/dev/.local/state/seekbell/acceptance/2026-10-23-content-loading-rss。全量测试用合成服务；另有一次官方RSS及真实库只读核对，不冒充真实通知/长期运行、Safari/真机或用户验收。

更新前完整归档原卷到/home/dev/.local/state/seekbell/local-runtime/backups/before-e3cfbf800487.tar.gz（0600，SQLite/SHA通过，未入Git）。更新后8配置表指纹一致，Windows两地址/版本/健康通过，实际服务验证历史时间不变与同批顺序正确。用户刷新页面即可复测。

## 既有结构、退役与下一步

[d224853结构清理](history/2026-10-23-单一正式前端结构清理.md)统一正式前端、演示产品退役，含a7435a2筛选/日期/计数修复。[旧Docker](history/2026-10-23-旧Docker实例退役清理.md)3容器/3卷/2网络/2镜像已删，18080/18081释放，旧数据归档maintenance/2026-10-23-retired-docker/archives。

公开仍ui-restore-5，代码c8be41c9a1f85650be6447e773b73a204dba9b88，digest sha256:089289552719774057aa527bbd055e7c33370e6cc5c1811c0da4583b0675f7ff。远程Stack及8000/4175未动。下一步用户在8001复测反馈；发布/远程部署需明确指示。恢复读本状态、当前修复记录与受影响代码。
