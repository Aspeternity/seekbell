# 当前状态

更新时间：2026-10-29（Asia/Shanghai）。阶段：v0.1.0代码/镜像已发布；附件已恢复并通过真实匿名验收；PR #21首轮被旧虚拟时钟竞态拦住，Clock初始化已修并通过本机重复/完整检查，待标准CI复验。

## 环境与发布身份

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe执行。
main及v0.1.0为dffce718c97f3bbe59c8cbdca72edfd7ff3c9f9e，PR #20已授权合并。
当前codex/fix-release-artifact-bundle，只修复CI清单/回归测试及文档，不改应用或镜像。
Release id426978304，非草稿/非预发布且为GitHub latest；许可继续待定。

## 已通过与部分失败

PR #20运行40732294202：860后端/174浏览器/双原生架构全过，CodeQL 40732286961全过。
main运行40735701320全过。发布40735980970的完整baseline、原生amd64/arm64、publish成功；
release-receipt最后上传失败，不称整轮发布工作流成功。
索引sha256:9b2bb08a82a232a2074c997941a179a4e84a8b2bffc95d9931ce36914c7a65b4，已生成0.1.0/latest。

根因是artifact清单version.json与release-assets/之间为字面反斜杠n，
原artifact12839060982只有release/package两个JSON。原publish日志含部署文件校验和。
新增契约测试已在旧清单下准确复现缺失四文件；修复后80项发布测试、Ruff、actionlint通过；PR #21已推送af2225b，CI 40771852239在history-ui-fixes因clock.pauseAt过去时间失败，CodeQL 40771848738已过。
恢复方案/边界见history/2026-10-29-v0.1.0附件恢复.md。

## 安全与运行边界

0.1.0锁cryptography50.0.2、certifi2026.10.18，原9条依赖告警已回读为0，安全PR #4/#5已关闭。
46.0.7与50.0.2双向加密配置/整库备份兼容通过，报告在本轮加密兼容JSON；
189项专项、79项发布检查及12重复/40完整热榜本机检查已过。
旧main热榜收尾竞态已修，未改业务行为/限流；无新迁移，schema0017。

没有部署或操作现有Portainer/8001实例，没有真实论坛请求/通知。
旧镜像、原卷/备份及来源429限制按正式发布前状态归档保留。
不组织多代理，不改旧Ubuntu、D盘交接副本或全局WSL。

## 下一步与授权

用户已明确授权正式版本和镜像发布及必要修复/PR合并，不重复询问。
清单修复PR #21待标准检查完成并合并；原ZIP校验807a9179…一致，六个附件已恢复，另上传recovery/anonymous-verification两份核验JSON。
真实匿名拉取/双平台配置层/容器0.1.0及附件原始校验和均通过；镜像9b2bb08a…保持不变。待PR21合并后记录完整交付。
不重建已占用0.1.0，不改写标签/历史，不将修复授权扩大成部署或真实发送。

本次提交另修frontend/tests/history-ui-fixes/history-ui-fixes.spec.ts的两处Clock初始化：共享目标并在其前一分钟安装；6项重复/6项完整用例全过，不改199/200ms断言、业务或已发布镜像。恢复说明和PROJECT_STATE同步留证，随后推送PR21复验。
私有原始材料/检查脚本在/home/dev/.local/state/seekbell/releases/v0.1.0。
读取仅需本轮恢复记录、IMAGE_RELEASE及相应CI/发布脚本；其余既有证据复用。
