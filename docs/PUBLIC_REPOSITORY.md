# 公开仓库维护

源码：[Aspeternity/seekbell](https://github.com/Aspeternity/seekbell)；
镜像：[GHCR seekbell](https://github.com/Aspeternity/seekbell/pkgs/container/seekbell)。
两者public已核实。许可证按用户2026-10-29选择暂不决定，不擅自补LICENSE。

## 合并与检查

main要求PR、baseline成功、分支同步main、讨论全部解决，禁止强推/删除，无绕过名单。
单维护者阶段批准人数为0，避免要求作者批准自己的PR；仍须完整CI。
只允许squash，使用PR标题/正文，合并后删分支，允许更新PR分支。
v*标签禁止更新/删除，发布见[镜像流程](IMAGE_RELEASE.md)。

PR执行完整baseline和原生双架构检查；main push执行baseline。
main规则当前强制baseline，两平台检查在本次PR实际运行后核实名称，再加入必需检查。
依赖更新同样走PR，不自动合并，不用skip ci绕过必需检查。
第三方Actions固定完整SHA，Dependabot每周检查GitHub Actions、uv和pnpm/npm，每生态最多5条PR。

## 安全配置

已启用密钥扫描/推送保护、Dependabot漏洞告警/安全更新、私密漏洞报告。
CodeQL默认设置首次初始化扫描成功，后续按PR及每周扫描；启用功能不代表没有漏洞。
私密报告入口见SECURITY.md，公开Issue模板要求脱敏。

Actions默认token只读、禁止工作流批准PR，所有外部贡献者的fork工作流须经审核。
不使用pull_request_target执行贡献者代码，不把registry写权限或真实通知凭据交给PR检查。
当前允许Actions来源策略未变；通过完整SHA固定和评审控制，避免阻断GitHub托管CodeQL默认流程。

## 只读核对

本机在SeekBell-Dev使用已登录的Windows GitHub CLI，不打印token。
有gh的维护环境可运行：

```bash
gh api repos/Aspeternity/seekbell --jq '{visibility,delete_branch_on_merge,security_and_analysis}'
gh api repos/Aspeternity/seekbell/rulesets
gh api repos/Aspeternity/seekbell/rules/branches/main
gh api repos/Aspeternity/seekbell/actions/permissions/workflow
gh api repos/Aspeternity/seekbell/actions/permissions/fork-pr-contributor-approval
gh api repos/Aspeternity/seekbell/code-scanning/default-setup
gh api repos/Aspeternity/seekbell/private-vulnerability-reporting
```

配置回读证据见[本轮记录](history/2026-10-29-公开仓库治理.md)。
隐私扫描只为官方Dependabot noreply作者的固定服务尾注提供例外；个人地址与源码扫描约束不变。\n个人CLI授权范围与Actions GITHUB_TOKEN独立；
个人CLI缺read:packages时使用匿名registry核对公开拉取，不为此扩张token权限。

依据：[规则](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)、
[CodeQL](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configure-code-scanning)、
[Dependabot](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories)。
