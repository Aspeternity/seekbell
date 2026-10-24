# 当前状态

更新时间：2026-10-24（Asia/Shanghai）。任务级按站版块范围已实现并保留数据更新8001；后端789、相关浏览器54、3项离线容器检查及Windows核验通过，待用户验收。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发。分支codex/linuxdo-integration，最后实现9becf75730e4e4c9accb35ed6f572529aa590c60，本轮用户明确授权把全部已完成修复优化推送并合入GitHub主分支，正在准备PR及远端CI。用户批准仅任务级按站版块/列表UI，沿用本地提交及8001保留数据更新授权；不做网站级总范围，不改RSS源。授权仅推送/PR/合并及既有本机操作，不含公开镜像发布、远程部署或主动真实试发；无多代理，不改D盘/旧Ubuntu/全局WSL/8000/4175。

## 实现与读取

先读[按站版块记录](history/2026-10-24-按站版块范围.md)，再看Rule/rule_values、配置/采集/试算/诊断与TaskCategoryScopes/TaskEditor/store/model。site_categories按站保存all/specific；指定非空、最多64值，与非空旧categories互斥，键必须等于任务网站集合。纯引擎按帖来源取范围，缺站拒绝，不联网。NodeSeek别名仅在本站输入规范化，不改其他站值或原帖。
旧共享数组保持原执行语义，前端复制到原有各站，未知旧值保留；首次保存生成新版本后使用按站结构，旧快照不动。0016_site_categories仅推进兼容标记，无DDL/数据修复，防止旧程序误读新JSON。
网站选择下按站摘要行，默认收起，一次展开一站；搜索/计数/230px限高候选、轻选中与细键盘焦点、空集校验/取消恢复。编辑即时进入任务草稿，完成只收起，直接保存不丢开放编辑。新加站默认全部，取消/重选保留本次草稿，序列化只写最终所选站；右侧按站汇总。

## 证据与运行

私有acceptance/2026-10-24-site-categories：后端789（新增15）、ruff、类型/构建/格式通过；诊断18/判定8/Linux DO20/工作空间8共54浏览器通过，桌面/手机截图已看。固定镜像启动/重启/合成账本、加密备份恢复、升级失败回退3项离线检查通过。均合成，无主动真实试发。
19:37先新备0015整卷；隔离副本全部旧表原列原值、配置、密钥凭据不变，仅schema推进0016，280组本地帖试算确认旧规则与按站投影结果一致。生产任务版本/历史/安装顺序保留，副本已删。19:38 Windows localhost/127.0.0.1的8001主页/就绪/完整SHA/0016/资源通过，同容器持续healthy/read-only/unless-stopped。长期/PVE/arm64及用户验收未完成。

## 回退与下一步

8001镜像seekbell:site-categories-9becf75730e4，digest sha256:0dcbf6aee3736356cf69ffeea334bd151c22acbb9031608c186844e4bee36957；项目seekbell-local/容器seekbell-local-seekbell-1/卷seekbell-local_data。私有local-runtime/runtime.json已同步；保活PID24204/创建2026-10-24T10:28:33.7894500Z不变，25268是其子进程，未新增/清理。
新备before-site-categories-9becf75-20261024-193727.tar.gz，完整路径/校验见记录。回退旧02d996d前先停并归档当前卷，再恢复匹配0015备份，不能让旧镜像直接读0016；更新后用户修改须保留。本轮合并范围为origin/main之后完整当前分支（包含热榜、Linux DO、退避/排序、多站任务、诊断及按站版块）；加入CI诊断套件后推送，创建PR并待检查通过合入main。远端默认分支当前2c682de，旧备份分支不属于本次成品改动。合并不触发手动GHCR发布/部署；8001仍固定9becf75不重建。PR #2（https://github.com/Aspeternity/seekbell/pull/2）已创建，head a8b489121d407cc50be9b4d2cd6909c6b6178261、35个提交，无冲突。PR run40100070383/push run40100027043均在test:history失败：旧测试仍期待改版前信息不足/基线文案。已核对新诊断保留信息不足、旧版本与未知条件，更新对应断言；另有早期approved-ui键盘断言跳过新增版块入口，已补Enter/Tab/Escape/焦点恢复检查。13套追加浏览器84项最新结果全通过、前端格式通过，生产代码不变；提交两处用例及交接后推送同PR，等新head CI再合并，不绕过检查。工作区未提交为frontend/tests/history/history.spec.ts、frontend/tests/approved-ui/collection.ts及本状态/合并记录，意图同步已批准诊断UI的语义断言与证据，无生产代码变更。最终SHA待确认。
