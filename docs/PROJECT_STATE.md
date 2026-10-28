# 当前状态

更新时间：2026-10-28（Asia/Shanghai）。阶段：用户已授权推送、PR合并main、GitHub发布双架构Docker镜像并生成Portainer Compose，进行发布验证中。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe执行。分支codex/hotlist-settings，最近产品实现a0e2b6f，发布适配1d7afcd。PR #3合并main时发现仅Compose标签/状态冲突，已保留新标签与本轮状态，合入main全部历史发布回执；产品代码无冲突。用户本轮明确授权GitHub推送/创建PR/合并main、GHCR发布及Compose交付；Portainer实机由用户测试。本轮不部署本机或远端、不主动请求论坛或真实发送。禁止多代理，保持原Ubuntu/D盘和全局配置。

## 已有本机版本与证据

本机8001记录版本seekbell:connection-test-ui-a0e2b6f51042，Image ID sha256:dcb0bfee42c36a182533c658e3bf36ce01e9143c4ce31e6a1c3f4b533ecbc2dd，schema0017；本轮未重新验证其运行状态。备份local-runtime/backups/before-connection-test-ui-a0e2b6f-20261025-201736.tar.gz，SHA256 dd4298533e67820058f7f8cdf6b12357a81d03d092d7378b401be5d2076f54b0。原服务/卷与密钥保持。私有runtime.json和验收证据位于/home/dev/.local/state/seekbell。

a0e2b6f的类型/构建/格式、Linux DO 26项与operations 6项浏览器、2项离线容器/恢复通过；后端沿用ebea3fe的819项。本机保留数据更新与用户体验验收分开。连接测试根因与证据见history/2026-10-25-连接测试状态修正.md；热榜与迁移见history/2026-10-25-热榜验收修正.md、2026-10-25-热榜本机更新.md。

## 本轮发布准备

仓库API确认public，远端main e23749a，当前PR #3。旧镜像ui-restore-6发布SHA987beda，digest 6fd13c6fc1e722b2477405851536526abb9bab6aed3ee2723b36f26897c96f6d，完整回执见history/2026-10-25-ui-restore-6发布.md。原本地HEAD f67a6cf领先main12提交、48文件；涵盖热榜独立刷新设置/0017迁移、挑战处理与选择框、连接测试历史/本次结果分离及V2EX方案文档。其他本地分支无额外独有提交。检查前工作区干净，上轮仅状态文件未提交。

旧镜像元数据检查强制私有源码，会阻断现公开仓库；本轮新增明确的源仓库可见性参数，默认仍private，发布工作流显式public，保留包名/链接/包可见性检查。发布适配85项测试和Ruff通过（1d7afcd）。5328186完整CI运行40712297222后端/构建通过，历史UI测试发现请求数竞态：未等异步标签切换完成便放行计数响应，正常刷新多一次；本轮只补等待aria-current后再放行，产品不变。CI失败未合并/发布。修正后本机完整6项及双端各重复2次共4项通过；扩大重复至6用例会因每用例两次登录触发临时服务10次/分钟登录限频，未修改限频。一次误并行复验导致端口/trace冲突，已排除并顺序重验。两份Portainer模板候选标签hotlist-20261028，保留8000/8001及各原卷键，发布后核对digest。发布变量当前缺失，授权范围内临时启用，结束恢复。

ad010e5的push CI 40714503115在Linux DO beforeEach重置选择失败（25/26过），同提交PR CI 40714514493已通过此项继续执行，符合跨用例迟到选择写入竞态。本轮仅测试afterEach等待网络空闲再交接共享偏好，重置断言保留状态/错误信息；本机26项过。产品代码未变，复用已有产品证据；最终main发布流程仍须完整CI与双架构全过才写GHCR。

## 下一步与限制

审查并提交上述改动，推送分支/创建PR，核对可复用CI和本机测试等待修复证据后合并main；按合并SHA显式发布（完整CI及双架构全过才写镜像），保存回执并核对匿名拉取后交付Compose。升级先完整备份原卷和密钥；0017库不能直接用旧镜像回退，须匹配旧备份。此前Linux DO日榜429/Cloudflare限制未证明恢复，实机由用户验收。V2EX仅导航大类方案，未开发。读取清单：docs/IMAGE_RELEASE.md、docs/RELEASES.md、deploy两份模板、本轮发布脚本与测试。
