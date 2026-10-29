# 当前状态

更新：2026-10-29（Asia/Shanghai）。发布分支codex/release-0.3.0（自main a34e6f3），bump_version 0.3.0与CHANGELOG已写，正在发布v0.3.0。

## 开局

先运行`python3 scripts/dev_status.py`取得分支、工作区、版本一致性和最新CI，不再逐条手工核对。与本文不符时以实际为准并先更新本文。

## 计划位置

M0–M4已完成，v0.2.0已公开发布：双架构索引sha256:87d415bb…，0.2.0/latest与6附件经匿名核对一致，见[发布归档](history/2026-10-29-v0.2.0发布进度.md)。现用实例尚未部署0.2.0。下一阶段为M5实机验收（ROADMAP“当前阶段”表），需另行授权。

## 进行中：发布v0.3.0（三步流程首次实跑）

1. 设置单列布局与时区修复：七分类保留，“概览”改名，故障/告警记录移至关于与诊断。证据见[单列布局记录](history/2026-10-29-系统设置单列布局与时区修复.md)。
2. 发布流程精简：三步发布；CI按源码tree复用已通过基线；容器演练只在原生构建中运行，与基线并行；Release末尾匿名核对。新增bump_version/ci_reuse/verify_release/dev_status脚本。本地后端887项及新增19项测试通过，ruff通过，工作流YAML可解析；actionlint被本机权限拒绝未执行。新工作流尚未在GitHub运行，首个PR是实际验证点。

## 下一步

1. 用户2026-10-29验收通过设置页面（单列布局、时区修复）。发布步骤：PR合并→`gh release create v0.3.0 --target <main SHA>`→`gh run watch`；Release运行中baseline应因tree复用而跳过。
2. 已验证：PR CI 40866434238/40868923522全绿；合并后main push 40871117351仅11秒，reuse复用40868923522，baseline与native均skipped。下一次Release是三步流程的首次实跑，留意baseline应同样跳过。
3. 以后发布按IMAGE_RELEASE“正式发布（三步）”执行，等待CI用一次`gh run watch`（gh已装在SeekBell-Dev）。

## 授权

用户2026-10-29授权v0.3.0全流程：推送、PR合并、创建Release、GHCR双架构镜像及latest与Release附件。无部署或真实发送授权。

## 按需读取（只读与任务相关的项）

- 设置界面：UI_DESIGN末节、SPEC第175行、frontend/src/pages/*Settings.vue
- 发布/CI：IMAGE_RELEASE“正式发布”、.github/workflows/*.yml、scripts/{bump_version,ci_reuse,verify_release}.py
- 实机验收：ROADMAP“当前阶段”、ACCEPTANCE、RELEASES
- 其他历史只在本文链接指向时阅读。
