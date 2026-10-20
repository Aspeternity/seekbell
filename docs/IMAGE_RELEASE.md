# 双架构镜像候选与GHCR流程（M4第五子阶段）

本流程准备可审阅的镜像候选，不部署服务。`.github/workflows/images.yml`只有`workflow_dispatch`入口；普通push/PR不登录或写GHCR；codex/开发分支的push在完整CI成功后调用同一原生双架构检查，便于合并主分支前验证。新流程默认`publish=false`，分别使用`ubuntu-24.04`和`ubuntu-24.04-arm`原生构建Linux amd64/arm64，不安装QEMU或修改本机Docker。私有仓库使用账户Actions额度，runner/额度是否可用须实际运行确认。

## 候选检查与产物

手动启动时必须填写所选分支当前完整40位小写SHA，和事件SHA不一致立即失败；没有任意外部ref参数。开发分支push由事件SHA确定候选，不提供发布入口。原生构建/演练/归档集中在native-images.yml复用，只有contents:read权限。先调用原有完整CI（Python/前端/浏览器/禁外网容器），通过后再执行双架构构建。每个平台检查Docker daemon原生架构，镜像写入同一代码SHA及GitHub source标签，再分别运行包内服务/重启持久化、加密备份独立恢复、合成迁移/新卷切换/失败显式回退、真实隔离TLS反代演练。所有业务检查使用临时数据/合成目标，禁论坛和真实通知。构建所需基础镜像/软件依赖仍需网络。

检查全部通过才从固定image ID建立私有产物标签并保存`image.tar`和`image.json`，保存后再核对配置及层指纹，上传`image-amd64`、`image-arm64`，保存3天。JSON记录平台、完整SHA、source、image ID、运行配置digest和归档SHA256；证据包括对应Actions日志。归档只含构建镜像，不含演练数据卷/会话/备份。产物可用于候选审阅，不能把工作流定义或本地amd64检查当作远程CI/arm64运行已通过。

两平台使用各自原生Python环境构建虚拟环境；不跨平台复制本机`.venv`。前端和Python依赖使用现有锁文件，基础镜像沿用当前Dockerfile；标签构建的基础镜像可能更新，重新构建同一代码SHA不保证逐字节一致。因此实际部署固定最终registry digest，发布复用已测试归档，不重新构建。现阶段无镜像签名、SBOM或独立供应链证明，产物校验和用于传输一致性，不等同密码学来源签名。

## 实际执行前的授权与开关

实际执行进度与授权以PROJECT_STATE为准；规格中的GHCR规划不代表操作授权。原生候选与产物往返已有远程证据，实际发布仍须本次明确授权。

获授权后先审阅/合并相应代码，并核对GitHub Actions及两个原生runner额度。先对明确SHA手动运行`Native image candidates`，保留`publish=false`；检查完整baseline及两平台日志。[GitHub的workflow_dispatch入口须先存在于默认分支](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)；本流程尚未合并时，先推送codex/开发分支，通过普通CI后的native-candidates检查取得两平台产物，不为派发而合并main。合并另获授权后，才可手动选择分支/SHA运行候选或显式发布。

真正写GHCR还必须同时满足：

- 仓库管理员在Actions repository variables设置`SEEKBELL_GHCR_ENABLED=true`；默认缺失即关闭。
- 手动运行时显式选择`publish=true`，填写所选默认分支当前完整SHA。
- 事件ref必须是仓库默认分支，且完整CI和双架构检查全部成功。

开关检查失败会直接报错，不伪装成发布成功。未配置环境审核门禁；私有仓库的environment/reviewer功能受GitHub账户计划限制，不能假定存在自动人工审批。上述显式开关、手动选择和默认分支限制用于减少误操作，不能替代仓库写权限管理与实际授权；不配置/提升账户计划或权限来绕过限制。

发布前preflight仅有packages读取权限，先核对目的包访问，失败不浪费后续构建；只有publish job获得`packages: write`，用短期`GITHUB_TOKEN`登录GHCR，不要求长期PAT，不向build job提供registry写权限。包名固定为`ghcr.io/<小写owner>/<小写repo>`，不接受外部registry/命名空间输入。发布job在写registry前用短期令牌检查仓库私有、已有包私有；API若报告仓库则核对一致；404仅允许继续尝试创建，不当作“包不存在”的证明，不改变他包权限。首次推送按GHCR默认私有创建，成功后再次确认私有并保存package.json；仓库字段可选/可空，缺失标记not-reported、不当作关联失败，镜像source配置仍独立核对本仓库。未知/公开或明确报告其他仓库的包均失败停止，不自动改可见性。首次包或已有包的Actions写权限、可见性和访问继承须核对；工作流不改变包可见性、不创建GitHub Release、不更新latest或语义版本标签，也不自动部署。

## 发布行为与失败处理

发布job从同次运行下载两份产物，先核对校验和、平台、代码SHA、source标签、构建环境变量和非root UID，再登录；发布前再次核对两份归档。默认`release`子命令只生成本地计划并加载校验镜像，只有额外`--execute`才写registry。

标签包含`sha-<完整SHA>-<run ID>-<attempt>`，每次重跑attempt不同，两个原生子标签追加`-amd64`/`-arm64`。分别推送已加载且校验过的本机image ID，读取registry单平台manifest确认config digest等于归档内原始配置字节的SHA256；通过两个不可变digest合成索引，严格核对索引恰含linux/amd64和linux/arm64及预期digest，再以索引digest重读确认。classic与containerd的image ID可能分别指向配置/manifest/索引，不能把image ID直接当config digest；加载后比较运行配置及各层指纹，分别留证。回执即使后续校验失败也保留，但不能据此称整轮成功。私有元数据检查后，再从registry按索引digest显式拉取amd64，在禁外网新临时实例执行包内服务/重启/实例锁检查；arm64已在推送前原生验证，发布后不在amd64宿主机模拟运行。成功后Actions summary与`image-release-receipt`（30天）给出代码SHA、索引digest、两个子manifest及`ghcr.io/...@sha256:...`固定部署引用。应另存回执，不能依赖短期artifact永久保留。

标签命名降低工作流自身重跑覆盖的风险，registry中有写权限的人仍可改标签。部署/回退均以回执中的digest及实际本机image ID为准，不依赖标签不可变假设。发布中断可能已留下单平台标签或已创建索引；失败不代表registry无写入，不自动删远程包，也不切换任何运行实例。检查当次日志和registry后重跑，新的attempt使用不同标签；只有全部核对成功才记录成功回执。可重跑失败job；候选归档已过期时须全流程重跑，不能拿其他run产物拼接。

## 部署核对与本地命令

授权部署时在目标宿主机以受控方式登录/拉取回执中的固定digest；registry只读凭据不得进入Compose、Web配置、Git或日志。先确认目标是amd64或arm64及本地image标签/版本，再按[新卷升级回退](RELEASES.md)维护；现有Compose的`pull_policy: never`继续要求事先显式加载/拉取。首次新部署与旧实例升级分别处理，勿复用不兼容旧卷或当前用户验收项目。HTTPS与只读预检按[反代部署](PROXY_DEPLOYMENT.md)，真实RSS/四渠道配置与发送属于M5授权验收。

本地在SeekBell-Dev执行，示例输出目录必须不存在，`SEEKBELL_IMAGE`指向带匹配revision/source标签的已验证镜像；这些命令不写registry：

~~~bash
uv run --frozen pytest -q tests/test_release_images.py
python3 scripts/release_images.py --help
python3 scripts/release_images.py --revision "$SEEKBELL_REVISION" --repository aspeternity/seekbell \
  pack --image "$SEEKBELL_IMAGE" --architecture amd64 --output /tmp/seekbell-image-candidate
python3 scripts/release_images.py --revision "$SEEKBELL_REVISION" --repository aspeternity/seekbell \
  verify --directory /tmp/seekbell-image-candidate --architecture amd64
~~~

两架构归档须分别在独立目录`<artifacts>/amd64`和`<artifacts>/arm64`。`release --artifacts <artifacts> --run <run-id>-<attempt> --report <计划.json>`默认仅核对本地，不写GHCR；别为本地演练添加`--execute`。

依据核对于2026-10-21：[Docker多平台原生runner](https://docs.docker.com/build/ci/github-actions/multi-platform/)、[GitHub私有仓库runner](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)、[GHCR认证与包权限](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)、[environment功能限制](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)。新工作流第三方Actions固定完整提交，版本标签解析记录见本阶段history。

## 已执行候选

2026-10-21已按用户授权完成main d55ee70的私有候选发布，完整CI、两种原生架构及发布后固定digest拉取检查通过。部署候选引用为`ghcr.io/aspeternity/seekbell@sha256:afab58706a30d2b01617f600ab36d09f82f427470a9e4e6bf2bc6f995470dbd4`。回执/两平台指纹和首次后置误判根因见[记录](history/2026-10-21-主分支合并与GHCR候选发布.md)。临时发布开关已恢复原先缺失，不代表永久发布或部署授权。
