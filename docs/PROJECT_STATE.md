# 当前状态

更新时间：2026-10-25（Asia/Shanghai）。阶段：热榜验收代码修正已更新本机8001；下拉定位与来源等待/验证误报已修，日榜匿名访问仍遭Cloudflare验证，不能声称稳定获取已解决。V2EX仍仅导航大类范围确认。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe执行。分支codex/hotlist-settings，最新实现ebea3fe3ba237006e88c884df714cd688ea58588；本轮修复后沿用保留数据更新本机Docker授权，无推送/合并/公开发布、远程部署或主动真实试发。无多代理，不在旧Ubuntu/D盘构建。前轮获准整体重启WSL的单次恢复已完成，本轮未重启/改变全局配置；Dev保活PID30200、创建2026-10-25T10:18:02.5636430Z继续有效。

## 本机运行及备份

8001现为seekbell:hotlist-followups-ebea3fe3ba23，amd64 Image ID sha256:c8e7f495d5f52a0eebb3bc70befa0785d701cf41d5c61ed85c6f143801fb7bde，schema仍0017_hotlist_settings。原seekbell-local/seekbell-local-seekbell-1/seekbell-local_data、127.0.0.1:8001及安全限制保持，healthy/read-only/unless-stopped。Windows localhost/127.0.0.1首页、ready/完整SHA/资源、保活及同容器稳定检查通过；metadata在私有local-runtime/runtime.json。
本轮17卷完整备份local-runtime/backups/before-hotlist-followups-ebea3fe-20261025-192014.tar.gz，SHA256 bc6c9b4a217ba090d0ca6ce4a81331a628dd08a6e344dc43c7effc008f89ab1b。32张原表原列原值及任务/热榜配置/密钥/凭据在副本预检与部署后指纹验证保留。无新DDL，同schema回旧77675c8镜像保留当前卷；仍先另存失败候选。之前16卷备份保留，不能用于直接回退当前17数据。

## 修复、实源与证据

优先读[验收修正](history/2026-10-25-热榜验收修正.md)、SPEC 6.4/验收补充、ARCHITECTURE末节；按需读collectors/http/rss、services/hotlists、AppSelect/CommunityHotlist及测试。
旧代码只在403识别cf-mitigated=challenge，导致429验证页被当普通限频。共享source_failure现按明确响应头识别200/403/429挑战，普通429仍限流，保留服务器等待、不读取/回显挑战HTML。Hotlist进程状态区分deferred与真正尝试，未发请求的同站等待不冒充本榜失败，来源恢复可释放纯延期，不抹掉真实失败退避。未改Cookie、HTTP/2、固定端点或增加客户端依赖。
dialog内NPopover视口坐标被workspace zoom再次缩放；新门户层抵消祖先缩放，菜单阅读尺寸只缩放一次，卸载清理。默认/125%缩放、滚动和手机响应式距离检查过。
819后端、76相关桌面/手机、2离线容器检查通过，类型/构建/Ruff/Prettier过。有限真实HTTP/2核验共3次GET：热门200/30项，日榜两次均429+cf-mitigated=challenge，最后19:11；其他核验因冷却/采集优先延期，未发请求。无持续实源轮询、Cookie/浏览器兜底或清退避。私有acceptance/2026-10-25-hotlist-followups留响应头/计数和完整部署证据，无帖子内容/凭据入Git。源码修复通过不等于日榜访问恢复。

## 下一步

用户刷新http://localhost:8001查看菜单和新提示；日榜仍需来源放行或另行评估获准的访问方案，不靠改URL/伪造成功掩盖。未确认新的采集客户端方案，保留当前固定匿名HTTPX边界。GitHub main e23749a与GHCR ui-restore-6独立未更新。V2EX先读导航大类方案，updated回顶/归属/后到匹配未决，迁移号以实际head选；旧咨询/授权恢复记录均已归档。
