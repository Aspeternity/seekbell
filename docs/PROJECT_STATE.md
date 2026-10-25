# 当前状态

更新时间：2026-10-25（Asia/Shanghai）。阶段：热榜优化已更新本机Docker 8001，等待用户界面/长期验收。V2EX仅导航大类范围确认，技术/开发未批。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe执行。分支codex/hotlist-settings，实现77675c8592417726a5392df71d6709d437c3d629；后续文档提交不改变镜像。用户明确要求保留数据更新本机Docker，另批准为本次HCS_E_CONNECTION_TIMEOUT故障重启整个WSL；已执行一次并恢复原Ubuntu/SeekBell-Dev，未改默认发行版/全局配置。无多代理，不在旧Ubuntu/D盘构建；无本轮GitHub推送/合并、公开发布、远程部署或主动真实试发授权。

## 当前运行与备份

http://localhost:8001/#/websites已运行seekbell:hotlist-settings-77675c859241，amd64 Image ID sha256:44f5a91cf2ec46173d59db0469051f277d280e1c63e88d6f7b8744a1a5d152b4，schema0017_hotlist_settings。原seekbell-local/seekbell-local-seekbell-1/seekbell-local_data及127.0.0.1:8001保持，healthy/read-only/unless-stopped。Windows保活PID30200、创建2026-10-25T10:18:02.5636430Z已验，旧PID24204失效；详见私有local-runtime/runtime.json。
停服完整备份0016卷：local-runtime/backups/before-hotlist-settings-77675c8-20261025-184632.tar.gz，SHA256 fe4b8522875c85a3ec294442b0e933c220f47883eadfebece024d6075aa5c32f，0700/0600。回退须旧9becf75镜像＋此备份，不能用旧15快照或让旧程序读17；完整步骤见[本机更新](history/2026-10-25-热榜本机更新.md)。

## 实现与证据

先读[SPEC 6.4](SPEC.md)、ARCHITECTURE末节及[开发记录](history/2026-10-25-热榜配置开发.md)；按需读hotlist_settings/hotlists、api/management、WebsiteHotlistSettings.vue、Websites.vue、CommunityHotlist.vue及测试。
网站内采集配置之后新增热榜区，按能力显示来源/推荐/自定义/恢复。推荐NodeSeek实时10/日30/周60分钟、Linux DO热门15/日30/周60，最小5/15/30、最大一天。设置独立持久化，单改不重排采集/基线；新鲜期与退避分离，取消其他周期预取，采集优先，区分刷新/等待/429/失败和预计重试/旧榜时间。原生dialog下拉门户已修复，旧节点目录不在本次范围。
同一实现/镜像809后端、72桌面/手机浏览器、3离线容器检查通过，本轮复用未重复全套。真实卷备份副本纯迁移验证32张原表原列原值、历史/配置/密钥/凭据保留，新增字段{}。Windows两个地址ready/版本/资源与后续容器稳定检查过；私有acceptance/2026-10-25-hotlist-local留回执。未重置账号或提取会话，无人工RSS核验/真实试发。实际UI、来源429和长期表现待用户验收。

## 其他待办与下一步

本轮未合并/发布GitHub；main e23749a及此前GHCR ui-restore-6保持，Portainer/PVE验收独立。用户现在刷新8001查看各站热榜设置，后续按授权处理问题或合并发布。V2EX先读[导航大类方案](history/2026-10-25-V2EX导航大类方案.md)：8候选、6源200/2超时，updated回顶/归属/后到匹配待审，迁移号按实际head选。候选网站咨询及先前交接保留[开发前快照](history/2026-10-25-热榜开发前交接.md)。
