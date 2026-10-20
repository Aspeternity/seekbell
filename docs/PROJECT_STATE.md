# 当前状态

更新时间：2026-10-21（Asia/Shanghai）。M0～M3实现及本地自动退出已完成；当前M4部署恢复，第五子阶段双架构候选/GHCR流程已实现并完成本地验证。M4远程双架构/GHCR及M5实机/用户验收尚未完成。[本次证据](history/2026-10-21-双架构镜像候选与GHCR流程.md)，[HTTPS前阶段](history/2026-10-20-外部HTTPS反代与部署检查.md)。

## 环境与代码

只在SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发。[入口](DEVELOPMENT_ENVIRONMENT.md)。分支codex/frontend-backend-integration，本段起点dd4eccf；产品代码仍等同faa991d，本次仅CI/镜像工具/测试和文档，无依赖/迁移/产品UI变化。原D盘、Ubuntu工具及全局WSL未改。

## 本阶段与证据

images.yml仅手动触发，默认不发布；核对完整SHA，复用完整CI后由原生amd64/arm64 runner各自构建、禁外网演练并保存产物。GHCR需单独授权、仓库开关、手动选择、默认分支及全部检查成功；只发布job有packages写权限，不部署。校验归档、平台/版本/source/UID/环境、配置及层；复用测试内容按两个digest合成并重读索引，输出固定部署引用。区分containerd/classic本机ID与配置digest；不解析push人类输出。[操作/失败边界](IMAGE_RELEASE.md)。

34项合成Docker专项0.29秒、全仓Ruff/format、新workflow格式、两个workflow的actionlint1.7.12通过；隐私/noreply已检查，提交前复查。未改产品代码，复用前阶段433项后端及真实隔离TLS/浏览器/备份升级证据。本轮d3c44803da35f4dcf817ccc05e5780c9253c44fd已推送开发分支；首轮远程CI 39460104809：后端全量/离线演示、前端类型构建通过；prototype套件错误收集backup/proxy专项目录，40过4失败，native按门禁跳过。正修复原型收集为tests根目录正向匹配，避免以后新增专项再误收；SeekBell-Dev本机40项39.9秒复验通过，列表确认原型40/备份2/HTTPS2各自独立；下一步提交并推送修复。

本机rootless/amd64镜像seekbell:images-local，revision dd4eccf，image ID sha256:ed2fcc2bae3c9f867ccb2af146c6fcf00bf4669faa2f39ecba5c0d7b71567ea8，配置digest和归档SHA见本次证据。实际导出/校验/加载、禁外网服务/重启持久化/实例锁/离线闭环通过，临时归档与容器清理；未发布。只读确认基础镜像声明双架构，本机无arm64执行能力，未装QEMU/改daemon。

## 用户验收实例

保留项目seekbell-acceptance-b45fc2c-20261020、容器后缀-seekbell-1、卷后缀_data，镜像seekbell:backup-local（b45fc2c），http://localhost:18081/。只读核对running/重启计数0，未替换/重置/代配置。旧seekbell-acceptance不兼容卷保留、容器已停；勿复用旧名/改迁移号。旧4175/18080未动。[故障记录](history/2026-10-20-本机验收启动修复.md)。

## 下一步与恢复

本轮推进中：已提交d3c4480并推送；手动入口未在默认分支，抽出只读native-images复用流程，由开发分支push在完整CI后调用，未合并main。下一步跟踪[远程CI](https://github.com/Aspeternity/seekbell/actions/runs/39460104809)并修复实际失败，核对两平台产物；未提交为prototype测试配置、本状态及远程证据记录，意图为修复CI收集根因。核对包权限/可见性后再决定GHCR发布。后续M5：授权PVE实机、真实RSS/四渠道、Safari/真机、运行观察和用户验收，确认后正式发布。[阶段顺序](ROADMAP.md)。实际目标代理/证书、原生arm64、GHCR、跨版本加密恢复未验证；恢复/回退可能重复发送，保留原卷，不直接降级新库。

恢复读AGENTS、本状态、IMAGE_RELEASE；按需读images.yml/release_images及专项测试、RELEASES/PROXY_DEPLOYMENT，不全仓重读。状态与本段实现同批本地提交，提交基准以git log为准。

## 授权

用户在明确下一步为推送及远程构建验证后要求继续，本轮据此执行当前开发分支推送和不发布的远程CI；沿用独立WSL/noreply。不授权合并main、GHCR写入、远程部署、真实发送/公开发布、原环境清理/全局WSL变更。不组织多代理；保留用户验收实例及其配置。
