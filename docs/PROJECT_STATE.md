# 当前状态

更新时间：2026-10-25（Asia/Shanghai）。阶段：按网站热榜配置本地开发及验证完成，待合并/发布与实机验收。用户已批准推荐/自定义周期及网站内入口；V2EX仅导航大类范围获确认，技术/开发未批。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe执行。分支codex/hotlist-settings，实现提交77675c8592417726a5392df71d6709d437c3d629，起点6661190（原V2EX文档分支；产品代码与main987beda相同）；继承的未提交咨询/发布/入口记录完整存[开发前交接](history/2026-10-25-热榜开发前交接.md)。本轮本地实现/验证/提交，不推送、合并或发布，不代部署/真实试发，不动旧Ubuntu/D盘/全局WSL/8000/4175及正式卷，无多代理。此前ui-restore-6发布授权已完成，不代表持续发布授权。

## 本轮变更与读取

权威需求[SPEC 6.4](SPEC.md)，实现结构见[ARCHITECTURE末节](ARCHITECTURE.md)；优先读services/hotlist_settings、hotlists、sites/hotlists、api/management、WebsiteHotlistSettings.vue、Websites.vue、CommunityHotlist.vue及对应tests。网站配置在采集之后增加热榜区，按本站支持项展示来源、推荐值、自定义/恢复推荐、统一保存及未保存保护。推荐NodeSeek实时10/日30/周60分钟，Linux DO热门15/日30/周60；自定义下限5/15/30分钟，上限一天。
0017_hotlist_settings仅向website_installations加默认{}的JSON，推荐/自定义独立持久化；单改热榜不重排采集/基线。服务将成功新鲜期和失败等待分开，每次读取按当前配置计算；并发在预算读取后重查缓存/任务，已知等待不伪造后台刷新。Linux DO后台采集到期优先，其余周期取消预取。UI区分刷新/等待/429/失败与重试/成功获取时间，长等待不硬套10分钟轮询。原生dialog内AppSelect弹层改挂最近dialog，修复新增下拉被顶层遮挡。
本轮产品及测试路径见开发记录/提交差异；新文件为0017迁移、hotlist_settings.py、hotlistSettings.ts、WebsiteHotlistSettings.vue、test_hotlist_settings.py。已归档继承状态，无用户内容丢弃；V2EX旧节点缓存退出推荐，不夹带实现。

## 证据与下一步

SeekBell-Dev当前产品树完整后端809通过；热榜36/Linux DO20/approved-ui8/workspace-stability8共72项桌面/手机检查通过（能力夹具最后2项单独修正后过，产品未变）。前端类型/生产构建、Ruff/格式/Prettier/锁/隐私与空白检查过。完整命令、失败修复与覆盖见[开发记录](history/2026-10-25-热榜配置开发.md)。均为临时合成数据，无真实论坛轮询/通知，不冒充实机验收。候选镜像seekbell:hotlist-settings-77675c859241，amd64 Image ID sha256:44f5a91cf2ec46173d59db0469051f277d280e1c63e88d6f7b8744a1a5d152b4；离线服务/备份恢复/旧schema16合成卷升级与显式回退3项均过。receipt/日志位于私有acceptance/2026-10-25-hotlist-settings。最终只读核验原容器仍旧镜像/schema16且ready接口200，未替换；本轮未做arm64/远程CI，未推送、合并或部署。下一步经授权合并/发布后实机验收。

## 运行与其他待办

main/origin main e23749a仅此前发布元数据；ui-restore-6镜像digest sha256:6fd13c6fc1e722b2477405851536526abb9bab6aed3ee2723b36f26897c96f6d，原CI40159916595及匿名核验通过，用户Portainer实机验收待定，详情见开发前快照及私有releases/ui-restore-6。本机8001原9becf75镜像/schema0016未替换。0017开发只迁移合成库；若后续获准升级，先新备原0016整卷，回退须旧镜像＋匹配备份。
V2EX下一步先读[导航大类方案](history/2026-10-25-V2EX导航大类方案.md)：8候选、6源200及2超时，updated回顶/归属/后到匹配待审；未来迁移号以实际head再取，不复用热榜0017。NodeLoc/LET等咨询未批准，证据保留在开发前快照。
