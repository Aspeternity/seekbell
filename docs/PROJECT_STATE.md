# 当前状态

更新时间：2026-10-25（Asia/Shanghai）。阶段：网站连接测试旧记录展示修正已实现，32项相关桌面/手机检查通过，待构建并保留数据更新本机8001。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe执行。分支codex/hotlist-settings，开始时HEAD aee47ea、工作区干净；本轮只改前端测试展示与文档。沿用修复后保留数据更新本机Docker授权；无GitHub推送/合并、公开发布、远程部署或主动真实试发。无多代理，不在旧Ubuntu/D盘构建。之前整体WSL恢复的单次授权已执行，不再沿用；保活PID30200、创建2026-10-25T10:18:02.5636430Z仍有效。

## 当前本机及待更新

8001仍为seekbell:hotlist-followups-ebea3fe3ba23，代码ebea3fe3ba237006e88c884df714cd688ea58588，Image ID sha256:c8e7f495d5f52a0eebb3bc70befa0785d701cf41d5c61ed85c6f143801fb7bde。schema 0017_hotlist_settings；seekbell-local/seekbell-local-seekbell-1/seekbell-local_data及127.0.0.1:8001，healthy/read-only/unless-stopped。私有metadata在/home/dev/.local/state/seekbell/local-runtime/runtime.json。
最近17卷备份before-hotlist-followups-ebea3fe-20261025-192014.tar.gz，SHA256 bc6c9b4a217ba090d0ca6ce4a81331a628dd08a6e344dc43c7effc008f89ab1b；位于local-runtime/backups。新更新仍先停机整卷备份、副本预检与配置指纹验证；本轮无DDL，同schema回旧镜像保留当前卷，不拿16备份覆盖17数据。

## 当前改动与证据

先读[连接测试修正](history/2026-10-25-连接测试状态修正.md)、SPEC末尾补充及ARCHITECTURE末节；代码为WebsiteConnectionTest/WebsiteConnectionResult、Websites及linuxdo/operations浏览器测试。GET的持久上次记录折叠、明确时间与历史语义；本次手测单独展示，开始重测移除旧结果，接口失败不残留绿色成功；到期等待提示自动消失。组件关闭卸载隔离迟到GET/POST，不改服务端记录、预算/退避或自动请求论坛。工作区未提交路径即上述前端文件与本轮文档。
构建/类型/格式过；Linux DO 26项、operations 6项桌面/手机过，含两天前记录、重开折叠、取消无POST、失败清绿、冷却到期和异步竞争。合成截图已视觉检查。后端未改，复用ebea3fe的819项证据；本轮未探测真实RSS或发送通知。

## 后续与保留限制

下一步提交实现，构建镜像并完成离线检查、整卷备份/副本预检、本机8001更新与Windows验证，再记录镜像/备份证据。热榜上轮修正与实源证据见[热榜验收修正](history/2026-10-25-热榜验收修正.md)：日榜两次匿名访问429+Cloudflare验证，最后19:11，尚未恢复，勿当作本轮UI修复结果。V2EX仍仅导航大类范围确认，未开发；GitHub main e23749a与GHCR ui-restore-6独立未更新。
