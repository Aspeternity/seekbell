# 当前状态

更新时间：2026-10-21（Asia/Shanghai）。M0～M3实现/本地自动检查完成，M4工程退出通过；当前M5由用户在Portainer自行部署验收。RSS连接测试独立计时修复已公开交付，待用户更新反馈。Codex未部署其环境、真实采集或发送。[阶段顺序](ROADMAP.md)。

## 环境与代码

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发，[入口](DEVELOPMENT_ENVIRONMENT.md)。main/origin实现基准e658b465159a24800887c30de5a645831615301b，已普通合并/推送；本地修复分支f94eae8保留。当前收尾仅状态/镜像说明/验收/history回执文档，与状态同次提交，不改已测实现。原D盘/Ubuntu工具及全局WSL未改。

## 当前交付与证据

用户反馈启用网站/10秒配置时测试一直被本地429拦截，概览连续失败0；明确要求手动诊断独立于正常采集周期。后台按网站保存的间隔运行，10秒仅默认，已补10/37/3600秒场景；测试独立2秒防连点，成功测试不延后后台，保留在途互斥/实际错误退避。兼容旧成功probe长计时，不改健康/基线/历史/账本，无依赖/迁移。预约等待旧方案已移除并归档。

[39502064791](https://github.com/Aspeternity/seekbell/actions/runs/39502064791)对e658b46整体success：后端528项188.19秒、浏览器64项，格式/锁/隐私/构建/迁移、容器/加密备份独立恢复/新卷升级回退/真实TLS全过；amd64/arm64各原生构建/运行/归档通过，无QEMU。发布复用已测产物，公开包/两个manifest/config/索引及固定digest拉取复验通过。

短标签：`ghcr.io/aspeternity/seekbell:rss-fix-1`。固定digest：`sha256:4fa567debf73686fa0486eacee2fd4e53e415178ae3084c25d86de25f2a7d463`。短标签在完整验证后复制同一索引并重读核对，不更新latest；空凭据匿名pull amd64、两平台索引及镜像版本e658b46核对通过。源码API仍private，包public/visibility_verified=true；repository可选字段记not-reported。[完整记录](history/2026-10-21-RSS修复镜像发布.md)、[发布回执](history/2026-10-21-RSS修复镜像发布回执.json)、[匿名证据](history/2026-10-21-RSS修复匿名拉取.json)。回执ZIP SHA与Actions上传日志一致，artifact仅30天。临时发布开关恢复缺失，cache恢复记录移除。

## 部署交接与保留

交付deploy/compose.portainer.yaml，使用rss-fix-1和seekbell_data卷键，Compose config通过；用户在原Stack更新并沿用原端口/数据卷，Codex未代升级。下一步用户确认版本e658b46，核对刚完成正常采集即可测试、配置间隔持续运行、真实RSS/四渠道、HTTPS/Safari/真机、重启/恢复及观察；不能把CI等同用户验收。跨版本加密恢复仍未验证，回退可能重复发送，保留原卷、不降级新库。

旧公开afab5870...及首轮部分发布保留，旧本地候选/ci-34cf183均保留，指纹见历史。18081本机验收项目seekbell-acceptance-b45fc2c-20261020、-seekbell-1容器、_data卷、backup-local镜像不动；最近running/重启0。旧不兼容卷及4175/18080保留。

## 恢复与授权

用户本轮明确授权修复合并/公开镜像及Compose交付，临时开关恢复已完成；沿用独立WSL/noreply，不组织多代理。无远程部署、真实发送、源码公开、正式GitHub Release或旧环境/全局WSL变更授权。恢复读AGENTS、本状态、本轮发布及独立限频记录，部署按需读IMAGE_RELEASE/PROXY_DEPLOYMENT/RELEASES。仅文档收尾skip ci复用e658b46，不循环写自身SHA。
