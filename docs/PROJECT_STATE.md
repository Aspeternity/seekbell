# 当前状态

更新时间：2026-10-24（Asia/Shanghai）。任务多站编辑与章节滚动高亮已保留数据更新本机8001；后端761/浏览器42项及容器检查通过，用户验收待。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发。分支codex/linuxdo-integration，最后实现9fb949ab9e1e19601916e3aab8e98dbaa0f547b2；后续仅交付文档提交，均未推送/合并。用户明确要求原任务可增减多个网站，替代旧单站锁定；沿用本机8001保留数据更新授权。公开发布/远程部署/主动真实发送另计。无多代理，不改D盘/旧Ubuntu/全局WSL/8000/4175。

## 读取与实现

先读[任务多站与章节导航](history/2026-10-24-任务多站与章节导航.md)，追溯才读同日Linux DO验收/退避记录。权威SPEC3/6.2、ARCHITECTURE/DECISIONS/UI_DESIGN已同步。本任务相关TaskEditor/model/store、任务列表/概览/Websites，management/configuration/ingestion/rule_trial/task_websites及0014。
章节原只记点击，现scroll/resize+rAF和布局观察同步实际位置，页底短末节补偿，卸载清理。网站为可编辑复选，至少一站；原任务增减保存成新版本，保留ID/规则/目标，历史/已生成通知不改，不补发。
0014仅给TaskVersion加website_ids，旧全部版本回填原单站，不自动扩大范围。物理Task.website_id保留创建来源，ORM为origin_website_id；当前匹配与依赖只读版本集合。删除目标版本同样复制范围；API集合为主兼容单站。Linux DO作者冲突显式提示，版块原名精确匹配；历史试算合计限量并标来源，只读无网络。

## 验证与限制

私有acceptance/2026-10-24-task-multisite：backend-full.log（761，新增11）、task-websites.log；Linux DO20/已批UI8/操作6/UI8共42项浏览器通过。格式/类型/构建/锁/隐私/wheel通过。container/backup-container/release-container.log证明离线启动、加密备份、未来迁移失败与完整回退通过，均合成/禁外网。
12:45只读正式核对0014、网站顺序/旧任务范围和外键完整，原配置不变；两站自动采集成功且错误/失败数0。Windows两地址/完整SHA/静态资源通过，新任务资源及概览22px保持，保活PID32480/创建2026-10-23T23:39:27.9859010Z不变。未额外人工RSS/测试/真实发送；长期/PVE/arm64与用户界面验收未完成。

## 运行与回退

同一seekbell-local/seekbell-local-seekbell-1、原卷seekbell-local_data、127.0.0.1:8001。镜像seekbell:task-multisite-9fb949ab9e1e，ID sha256:f72df5e8348e82ad0c4684b49100b812336666104420a49907f1e3dea3ed310c，schema0014，healthy/read-only/unless-stopped；账号/配置/密钥及HTTP/2保留，local-runtime/runtime.json已更新。
新整卷备份before-tasksites-9fb949a-20261024-124450.tar.gz；SHA/逐文件/SQLite及副本纯迁移证据见交付记录。全部原列/行和12类原配置、密钥/凭据一致，新增各版本范围逐项核对，正式再次比较通过，临时卷已清理。
旧9597083/0013镜像与匹配新备份保留，回退须恢复匹配整卷再启旧镜像，禁止旧镜像直接读0014。下一步用户刷新8001、编辑原任务勾选Linux DO保存；两站共用规则，检查已有版块限制。推送/合并待授权。
