# 当前状态

更新：2026-11-10（Asia/Shanghai）。

## 开局

正式环境为SeekBell-Dev的`/home/dev/projects/seekbell`，先运行`python3 scripts/dev_status.py`。main `85618ba`（PR #37），已发布版本0.8.0。

## 计划位置

M0–M4完成；v0.8.0（运行中心）已发布，证据见[v0.8.0记录](history/2026-11-09-v0.8.0运行中心.md)。系统设置重组已在本地实现、未提交，契约见SPEC 6.5.2，方案与取舍见[重组方案](plans/2026-11-10-系统设置重组方案.md)。运行中心阶段三（[方案](plans/2026-11-09-运行中心方案.md)第6节）未开始；M5真实RSS、四渠道和恢复验收未完成。既往证据见[阶段归档](history/2026-11-08-关于页整改前状态.md)。

## 进行中

系统设置重组，main工作区未提交，基于`85618ba`：
- 后端：迁移`0019_settings_reorganization`；新`api/settings.py`（设置接口迁入）、`services/disk.py`；alerts（延迟、测试发送）、authentication/auth（保持登录30天、按会话起点算免确认）、backups/maintenance（恢复残留列表与删除`/manage/backups/leftovers/{name}`）、operations/fault_guide（磁盘问题）、rendering（test阶段）。
- 前端：`settings.ts`、`backups.ts`、`SettingsSaveBar.vue`、`DataSettings.vue`、`RestoreLeftovers.vue`、`AccountSettings.vue`；重写设置各页、StorageSummary、Auth“保持登录”、App旧地址重定向。
- 测试：新增`tests/test_settings_reorganization.py`，调整既有后端与端到端测试；schema头改为0019（含Portainer模板注释与check_release_container）。
- 用户审阅后调整（11-10）：备份从数据页拆出为独立“备份”标签（六类），恢复残留卡移入备份页，数据页存储占用只显示残留占用并链接`#/settings/backup?section=leftovers`；`/settings/backup`不再重定向；磁盘故障指引文案同步；登录/初始化页显示密码按钮`tabindex=-1`，live测试校验Tab顺序；`main.py`给`/`与`*.html`加`Cache-Control: no-cache`（用户确认，防升级后浏览器沿用旧界面），test_baseline覆盖。
- 文档：SPEC 6.5.2、UI_DESIGN末节、ARCHITECTURE末节、DECISIONS、README、重组方案已回写（含六类调整）。
- 其余未提交：v0.8.0发布记录（随下个PR提交）；`assets/brand/`图标（未接入，待审）。

证据（本机，未提交工作区）：六类调整后 build、prettier、ruff通过，pytest相关72项与test_baseline 11项通过，Playwright system 26、backup 2、approved-ui 8、ui 8、live 6（含Tab顺序）、retention 2 通过；此前全量：`uv run --frozen pytest tests -q` 990 passed；前端build、prettier、ruff check/format、check_privacy通过；Playwright system 26、backup 2、retention 2、history 4、approved-ui 8、ui 8、hotlist 50、live 6、operations 8、workspace-stability 8、sending 4、runtime 2、first-entry 8、loading 4、diagnostics 18、content-stability 8、evaluations 8、linuxdo 26、history-ui-fixes 6 全部通过。proxy套件需固定本地镜像（SEEKBELL_IMAGE/REVISION），本机未跑，交CI。

## 下一步

1. 用户审阅界面与改动；确认后获授权建分支、提交、开PR（CI含proxy与容器升级检查）。
2. 发版时`bump_version.py`，CHANGELOG写明六类重组、新功能、迁移0019（回退需0018备份）；IMAGE_RELEASE“安全升级与历史”补一行。
3. 备份重构：[方案](plans/2026-11-10-备份重构方案.md)第二稿待用户审批（用户已定：不加密、不兼容旧格式；标准tar.gz不含管理员与会话、服务器端备份库、恢复三步向导、自动备份，分三期）；获批后回写SPEC/ARCHITECTURE/BACKUP_RESTORE再实施。
4. 运行中心阶段三；程序日志做法待议；热榜真实观察、图标采用与M5实机验收待推进。

## 授权

用户确认重组方案并要求实施；无提交、推送、PR、发布、部署或真实发送授权。实例只读命令的既有授权为用户本人执行。

## 按需读取

- 设置：SPEC 6.5.2、UI_DESIGN末节、ARCHITECTURE“系统设置重组”、`frontend/src/settings.ts`及`pages/*Settings.vue`、`api/settings.py`。
- 运行中心：docs/plans/2026-11-09方案、pages/{Operations,OperationsStatus}.vue、services/{operations,fault_guide,alerts,runtime}.py。
- 发布/实机：IMAGE_RELEASE正式发布段、ROADMAP当前阶段、ACCEPTANCE；图标见assets/brand/README.md。
