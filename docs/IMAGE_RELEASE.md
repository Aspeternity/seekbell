# 公开镜像与版本发布

源码与GHCR包均公开。正式版本、固定digest部署文件和回执以
[GitHub Releases](https://github.com/Aspeternity/seekbell/releases)为准。
自动发布的Release在镜像和标签就绪后才创建；手动创建的Release会先于镜像构建完成，下载前确认对应Actions完整成功。

## 版本与部署引用

Git标签/Release使用vX.Y.Z，镜像使用X.Y.Z，例如v0.2.0对应
`ghcr.io/aspeternity/seekbell:0.2.0`。
GitHub最新正式Release在检查全部通过后同时更新latest；
预发布vX.Y.Z-alpha.N、-beta.N、-rc.N（N从1开始）只生成自身标签。
补发旧正式Release且未被设为GitHub最新版本时，也只生成自身标签。

源码中的[8000](../deploy/compose.portainer.yaml)和[8001](../deploy/compose.portainer.compare.yaml)
模板固定明确版本；Release附件在相同版本上追加已验证的索引digest，例如
`ghcr.io/aspeternity/seekbell:X.Y.Z@sha256:…`。
正式升级优先下载Release附件的同名Compose，核对deployment.json；不会随latest漂移。
更新现有Portainer Stack，保留Stack名、端口和实际数据卷；使用自定义配置时仅替换image更稳妥。

同版本不同digest拒绝覆盖；同版本同digest可从已验证回执恢复。v*标签禁止更新/删除。
SHA、运行编号和架构标签保留供追溯，日常部署使用版本号或Release的固定digest引用。
镜像的真实身份以digest为准，不能假定有写权限的管理员永远不会手动改标签。

## 正式发布

前提：本次发布已获用户明确授权。正式版本随版本号变更的PR合并自动发布：

1. 在发布分支运行`python3 scripts/bump_version.py X.Y.Z`，一次更新pyproject.toml、uv.lock、
   frontend/package.json和两份Portainer模板（含当前schema），并在CHANGELOG补写自动生成的条目
   （不能留TODO）；`--check`通过后随PR提交。其他文档不写死当前版本号。
2. `gh pr merge <PR> --auto --squash`：必需检查通过后自动合并（需仓库开启allow auto-merge；未开启时CI通过后手动squash合并）。
3. 合并后main的“Local baseline checks”成功即触发“Versioned images and manual candidates”
   （workflow_run）：只检出main当前head（不检出事件给出的SHA，避免以特权上下文执行未经信任的代码），且必须等于刚通过基线的提交，否则交给更新的那次推送；preflight发现pyproject的正式版本尚无标签，就构建双架构镜像、发布并加版本/latest标签，
   再以CHANGELOG该版本条目创建Release（标签指向合并提交）、上传固定digest附件并匿名核对。
   用一次后台`gh run watch <run-id> --exit-status`等待该运行即可，失败时只看失败job日志。

预发布（X.Y.Z-rc.N）与补发旧版本不自动发布：版本号合并后手动
`gh release create vX.Y.Z-rc.N --target <SHA> --prerelease --notes-file <说明>`，由release事件走同一发布job。
Release只在镜像与标签就绪后才由自动流程创建；手动Release仍会先于镜像出现。

工作流内部：preflight（scripts/release_preflight.py）核对标签、版本、main祖先关系与包public；
baseline对同一源码tree复用已通过的结果（`scripts/ci_reuse.py`，只认本仓库自身运行的标记），
与ubuntu-24.04/ubuntu-24.04-arm原生构建和离线演练并行。镜像字节含提交SHA，squash合并后的提交须重新构建一次。
publish复用同次测试归档的配置和层，不重新构建；推送并核对双架构索引、按digest禁外网复验后才加版本标签及受控latest；
生成固定digest的两份Compose与deployment.json。独立contents:write job创建Release、上传附件并执行匿名核对
（`scripts/verify_release.py`，也可在tagged检出上本地重跑）。构建/发布job仅持contents:read/packages:write。

CI：基线拆为并行job（静态检查与构建、pytest-xdist多进程、浏览器套件分4组），汇总job名为`baseline`
（必需检查名不变），只在全部通过时写复用标记。PR另跑原生双架构构建。建议main规则不要求PR基于最新main（ruleset的strict关闭），
由合并后main push的基线兜底。本机只跑与改动相关的测试，全量交给CI，不在本机重复。
所有镜像发布使用同一串行并发组。失败要检查Actions和回执。
签名/SBOM尚未提供，校验和说明传输与内容一致性，不等同独立来源签名。

## 候选与失败恢复

workflow_dispatch保留：选择分支并填写当前完整40位SHA，默认publish=false，仅检查、不登录registry。
另有候选发布授权时，临时设置SEEKBELL_GHCR_ENABLED=true，在默认分支选择publish=true，
可添加短候选标签；候选禁止latest，完成后恢复变量原值。正式Release不依赖该候选开关。

中断可能留下SHA/架构标签或索引，不自动删远程镜像、不切换运行实例。
不能据部分结果宣告成功。重建同一源码可能因上游基础镜像变化产生不同digest；
已有版本不能靠重跑覆盖，须用已验证回执恢复同一digest或发布新版本。
CLI的promote默认只读计划，仅显式--execute写registry；compose只写本地部署附件：

```bash
uv run --frozen pytest -q tests/test_release_images.py
python3 scripts/release_images.py --help
python3 scripts/release_images.py --revision "$SEEKBELL_REVISION" --repository aspeternity/seekbell \
  promote --receipt release.json --version vX.Y.Z --report version-plan.json
python3 scripts/release_images.py --revision "$SEEKBELL_REVISION" --repository aspeternity/seekbell \
  compose --receipt version.json --version vX.Y.Z --templates deploy --output release-assets
```

pack/verify/release/alias保持兼容，两平台归档必须来自同一次运行。
包可见性失败即停止；个人CLI缺read:packages不代表包私有，不为核对扩张个人token权限。
发布使用短期GITHUB_TOKEN，公开包支持匿名拉取，无需docker login。

### 已发布镜像的附件恢复

若publish成功、最后附件上传失败，保留原索引digest及版本标签，从同次运行的原回执恢复。
先核对实际registry版本/两平台与原release.json，再以原标签的模板重建缺失的部署附件，
对照原publish日志中的文件SHA256。缺失version.json可按实际registry观测重建，但要明确记录来源；
不得冒充原artifact文件或重建同版本镜像。维护者在当次发布授权内补传附件后，实际匿名下载和拉取复核。
同时修复主分支的上传清单并通过PR检查；保留原失败运行与恢复证据，不能把失败历史描述为全绿。

## 安全升级与历史

0.3.0只改前端设置界面与发布工具，无数据库迁移（schema仍为0018），与0.2.0可直接互相切换镜像；升级前仍建议完整备份。

0.2.0新增0018_settings_maintenance迁移，用于工作空间修改版本与备份操作记录；
系统设置恢复顶部横向分类并加入维护能力。升级前完整备份，回退0.1.0必须匹配0017的原卷或备份，
不能用旧镜像读取已迁移到0018的卷。


0.1.0更新cryptography至50.0.2及certifi至2026.10.18，未新增数据库迁移。
用合成数据库实际验证cryptography 46.0.7与50.0.2双向恢复、原密钥、历史密文、队列和登录。
可在两个已安装项目依赖的独立Python环境中复现（不会读取真实实例）：

```bash
python3 scripts/check_crypto_compatibility.py --old-python /path/to/old-env/bin/python \
  --new-python /path/to/new-env/bin/python --report crypto-compatibility.json
```

升级前完整备份原卷与credentials.key；回退须使用匹配旧schema备份，见[维护流程](RELEASES.md)。
真实RSS、通知、部署和用户验收分别记录。版本号不代表来源限流/Cloudflare问题已消失。
历史hotlist-20261028的代码9c925ee及固定digest证据见[旧发布](history/2026-10-28-hotlist镜像发布.md)，
候选流程细节见[历史说明](history/2026-10-28-候选镜像流程.md)。

依据：[Release事件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#release)、
[GHCR](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)、
[cryptography变更](https://cryptography.io/en/latest/changelog/)。
