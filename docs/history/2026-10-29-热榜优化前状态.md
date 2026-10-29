# 当前状态

更新时间：2026-10-29（Asia/Shanghai）。阶段：v0.1.0正式版本、双架构镜像及8份Release附件已交付；原附件漏传已恢复，根因修复已合并；实机部署/用户验收待进行。

## 环境与版本

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe执行。
应用标签v0.1.0/发布代码dffce718c97f3bbe59c8cbdca72edfd7ff3c9f9e，
ghcr.io/aspeternity/seekbell的0.1.0与latest均为索引
sha256:9b2bb08a82a232a2074c997941a179a4e84a8b2bffc95d9931ce36914c7a65b4，linux/amd64、linux/arm64。
main=origin/main ae5eff0，仅后续CI/测试/说明修复，应用目录及原标签/镜像未改写。

当前本地codex/v0-1-0-published-handoff仅保存最终状态、阶段记录及5份JSON回执，未推送；
后续随相关PR同步，不为补交接强行合并。D盘交接副本未动。

## 证据与恢复

[Release](https://github.com/Aspeternity/seekbell/releases/tag/v0.1.0)为最新正式版。
PR #20/40732294202完整860后端、174浏览器、原生双架构及CodeQL通过；
main40735701320通过。发布40735980970的baseline/native/publish成功，
最后附件job失败，原因是产物清单字面反斜杠n漏选四文件，不称该原运行全绿。
原ZIP12839060982校验一致，release/package原字节保留；缺失版本观测回执明确标注重建，
两份Compose与原publish日志SHA256一致，6文件已补传，另附恢复/匿名核验JSON。

已用空Docker配置实际匿名拉取固定digest及0.1.0/latest，
核对两平台manifest/config、原层指纹、UID10001、代码版本；
实际容器SeekBell0.1.0/cryptography50.0.2/certifi2026.10.18，禁外网服务/重启检查通过。
8附件散列、更新回执匿名下载及远端标签再次核对通过；细节见正式发布记录/JSON。

PR #21清单契约回归先失败后通过；另修旧浏览器Clock暂停过去时间的竞态，
保留199/200ms断言，未改业务。最新40774483932通过861后端/174浏览器/原生两架构，
CodeQL40774478950全过，合并ae5eff0且tree与已测a48cf111一致。
main自动复跑40776950203记录时进行中，不冒称已过；复用的是相同tree的PR证据。

## 安全、运行与下一步

原9条依赖告警已回读为0，安全PR #4/#5由正式版本替代关闭，普通更新未合并。
46.0.7与50.0.2双向整库/凭据兼容通过；无新迁移，schema0017。许可证按用户选择仍待定。
没有部署Portainer/8001、读取实际库或主动真实发送；旧镜像/原卷/备份和来源429限制保留，
原实例资料见正式发布前状态归档及其链接。

下一步用户在原Stack升级前完整备份原卷和credentials.key，保留Stack名、端口和实际卷，
使用Release对应8000/8001的固定digest附件；自定义Stack只替换image更稳妥。
真实RSS/通知和目标部署验收须独立验证。此次发布及必要PR合并已明确授权并完成，
不产生后续持续发布、部署或真实试发授权。不改旧Ubuntu/全局WSL，不组织多代理。

读取：IMAGE_RELEASE、RELEASES、本轮正式发布/恢复记录与回执；其余规格不重读。
私有原始ZIP、旧依赖环境、验证脚本/日志在/home/dev/.local/state/seekbell/releases/v0.1.0。
