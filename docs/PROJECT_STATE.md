# 当前状态

更新时间：2026-10-24（Asia/Shanghai）。正交付Linux DO每日榜单短等、首次连接测试伪限频及网站顺序修复；代码完成，后端750/浏览器48项通过，待容器验证和本机更新。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发。分支codex/linuxdo-integration，当前基于0741529，上一产品30252cea8e88df76fe8b807a3721562289e84ba5；均未推送/合并。用户要求继续三项修复，沿用本机8001保留数据更新授权；公开发布/远程部署/主动真实发送另计。无多代理，不改D盘/旧Ubuntu/全局WSL/8000/4175。

## 本任务读取与实现

先读[多站验收修正](history/2026-10-24-LinuxDO验收修正.md)，需追溯再读同日退避/HTTP2记录。SPEC6.2、ARCHITECTURE/DECISIONS、UI_DESIGN已同步。相关代码services/request_budget/source_probe/hotlists/overview_preferences、api/management、WebsiteInstallation、0013迁移、CommunityHotlist与linuxdo测试。
自动失败曾错误占60秒人工配额；现仅真实人工预算reserve占配额，未发请求的延期短等2秒。0013从真实测试证据修正旧伪配额，服务器等待保持。HTTP/2、原退避阶梯/保护、NodeSeek和概览22px间距保持。
Linux DO热榜关闭跨周期预取，短暂忙碌/间隔返回waiting并自动重试、保留旧条目，真实来源异常据实展示。08:20只读已有成功每日快照，不能推断所有历史错误均同因。网站排序原按ID，现position按添加顺序、移除重加置末；正式旧库原rowid确认NodeSeek在先。

## 证据与下一步

私有acceptance/2026-10-24-linuxdo-followups：status-before.json、backend-final.log（750通过）、linuxdo-browser-final.log（16）、hotlist-browser.log（26）、operations-browser.log（6）；格式/类型/构建/锁/隐私/wheel通过。全部合成服务，无额外论坛或真实发送。
本轮改动路径见git status，均为上述修复、对应测试/权威文档及新迁移/验收记录。先提交实现，构建固定SHA镜像，执行check_container/check_backup_container/check_release_container。通过后停服整卷备份、解包/SQLite/副本纯迁移验证，再更新原8001并验Windows/版本/顺序/状态。长期/PVE/arm64和用户验收未完成。

## 当前运行与回退边界

本机仍seekbell:retry-controls-30252cea8e88，镜像sha256:28bb4103cd3a8c2c65e6670d6040facb5ae3d8ed0156f8e2b79bf3d699d61e73、schema0012；同一seekbell-local/seekbell-local-seekbell-1、卷seekbell-local_data、127.0.0.1:8001。原账号/配置/密钥保留；Windows保活PID32480、创建2026-10-23T23:39:27.9859010Z。私有local-runtime/runtime.json为运行元数据。
旧交付备份before-retry-30252ce-20261024-081237.tar.gz匹配更早0011，不能用于直接回退本次0013。更新前必须新备份当前0012整卷；失败归档候选后恢复匹配0012卷与30252ce旧镜像，禁止旧镜像直接读0013。
