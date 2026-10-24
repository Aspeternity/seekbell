# 当前状态

更新时间：2026-10-24（Asia/Shanghai）。任务级按站版块范围已实现并保留数据更新8001；后端789、相关浏览器54、3项离线容器检查及Windows核验通过，待用户验收。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发。分支codex/linuxdo-integration，最后实现9becf75730e4e4c9accb35ed6f572529aa590c60，未推送/合并。用户批准仅任务级按站版块/列表UI，沿用本地提交及8001保留数据更新授权；不做网站级总范围，不改RSS源。无公开发布/远程部署/主动真实试发授权；无多代理，不改D盘/旧Ubuntu/全局WSL/8000/4175。

## 实现与读取

先读[按站版块记录](history/2026-10-24-按站版块范围.md)，再看Rule/rule_values、配置/采集/试算/诊断与TaskCategoryScopes/TaskEditor/store/model。site_categories按站保存all/specific；指定非空、最多64值，与非空旧categories互斥，键必须等于任务网站集合。纯引擎按帖来源取范围，缺站拒绝，不联网。NodeSeek别名仅在本站输入规范化，不改其他站值或原帖。
旧共享数组保持原执行语义，前端复制到原有各站，未知旧值保留；首次保存生成新版本后使用按站结构，旧快照不动。0016_site_categories仅推进兼容标记，无DDL/数据修复，防止旧程序误读新JSON。
网站选择下按站摘要行，默认收起，一次展开一站；搜索/计数/230px限高候选、轻选中与细键盘焦点、空集校验/取消恢复。编辑即时进入任务草稿，完成只收起，直接保存不丢开放编辑。新加站默认全部，取消/重选保留本次草稿，序列化只写最终所选站；右侧按站汇总。

## 证据与运行

私有acceptance/2026-10-24-site-categories：后端789（新增15）、ruff、类型/构建/格式通过；诊断18/判定8/Linux DO20/工作空间8共54浏览器通过，桌面/手机截图已看。固定镜像启动/重启/合成账本、加密备份恢复、升级失败回退3项离线检查通过。均合成，无主动真实试发。
19:37先新备0015整卷；隔离副本全部旧表原列原值、配置、密钥凭据不变，仅schema推进0016，280组本地帖试算确认旧规则与按站投影结果一致。生产任务版本/历史/安装顺序保留，副本已删。19:38 Windows localhost/127.0.0.1的8001主页/就绪/完整SHA/0016/资源通过，同容器持续healthy/read-only/unless-stopped。长期/PVE/arm64及用户验收未完成。

## 回退与下一步

8001镜像seekbell:site-categories-9becf75730e4，digest sha256:0dcbf6aee3736356cf69ffeea334bd151c22acbb9031608c186844e4bee36957；项目seekbell-local/容器seekbell-local-seekbell-1/卷seekbell-local_data。私有local-runtime/runtime.json已同步；保活PID24204/创建2026-10-24T10:28:33.7894500Z不变，25268是其子进程，未新增/清理。
新备before-site-categories-9becf75-20261024-193727.tar.gz，完整路径/校验见记录。回退旧02d996d前先停并归档当前卷，再恢复匹配0015备份，不能让旧镜像直接读0016；更新后用户修改须保留。下一步刷新8001验收逐站设置；完成交接文档提交，允许文档HEAD与实现SHA不同，无未提交产品改动。
