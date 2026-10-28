# 公开镜像与版本发布

仓库与GHCR包均公开。当前已发布的是历史候选 hotlist-20261028：
`ghcr.io/aspeternity/seekbell@sha256:abb0a56e6c2b648b49348cb697207d8afd7a53b4517020b14c0a6cddfad8aeb5`。
代码9c925ee，linux/amd64及linux/arm64，见[发布证据](history/2026-10-28-hotlist镜像发布.md)。
当前尚未发布标准版本或latest；本次流程改动不重命名历史版本、不部署实例。
[8000](../deploy/compose.portainer.yaml)与[8001](../deploy/compose.portainer.compare.yaml)模板继续固定上述digest。

## 版本约定

Git标签与GitHub Release使用 `vX.Y.Z`，镜像使用 `X.Y.Z`。
例如首次版本可选v0.1.0，对应ghcr.io/aspeternity/seekbell:0.1.0。
被GitHub标为最新的正式Release在检查全部通过后同时更新latest。
预发布支持vX.Y.Z-alpha.N、-beta.N、-rc.N（N从1开始），仅生成自身镜像版本标签。
旧正式Release补发且未被选为GitHub最新版本时，也只生成自身版本标签。

latest方便试用，会随正式发布移动；生产推荐Release回执中的固定digest。
同版本如果对应不同digest会拒绝覆盖，同版本同digest允许从已验证回执恢复。
v*标签禁止更新/删除。SHA、运行编号和架构标签仍保留用于追溯，
GHCR会展示这些标签和双架构manifest；日常部署使用版本号、latest或digest即可。

## 正式发布

1. 在开发分支修改版本和发布说明，通过PR合并main。pyproject.toml与Release版本必须一致，
   并更新uv.lock：正式0.1.0对应v0.1.0；0.1.0rc1对应v0.1.0-rc.1。
   当前仍为0.1.0.dev0，不能直接创建v0.1.0冒充对应版本。
2. 经本次发布授权后，为main上选定提交创建v*标签并发布GitHub Release；
   预发布须勾选pre-release，正式发布按需要设为latest。发布Release就是镜像发布入口。
   草稿不会发布镜像，普通push/PR也不写GHCR。
3. Versioned images and manual candidates核对标签、版本、主分支祖先关系和源码/包public，
   执行完整baseline，再在ubuntu-24.04和ubuntu-24.04-arm原生构建及离线演练。
4. 发布复用两份测试归档中的配置和层，不重新构建；推送各平台并组合验证双架构索引。
   按digest拉取并完成发布后禁外网容器检查后，才给同一个索引添加版本号及可选latest。
5. Actions保存release.json、package.json、version.json；
   独立的contents:write job将三份回执上传到Release。构建/发布job只持所需的contents:read/packages:write。
   整个运行成功后才能宣告镜像发布完成。

GitHub的Release条目先出现，镜像须等待工作流完成；失败时不可将Release当成可部署镜像。
正式发布不依赖候选的临时开关。所有镜像发布共用串行并发组。

## 候选与失败恢复

workflow_dispatch保留：选择分支并填写当前完整40位SHA，默认publish=false，只检查、不登录registry。
本次另有候选发布授权时，临时设置SEEKBELL_GHCR_ENABLED=true，
在默认分支选择publish=true，可添加hotlist-20261028等短候选标签；候选仍禁止latest。
完成后恢复开关原值，当前开关缺失。

中断可能留下SHA/架构标签或索引，不自动删除远程镜像、不切换运行实例。
标签更新失败以实际registry digest和回执为准，不据部分结果宣告成功。
上游基础镜像变化可能使同源码重建digest不同，已有版本不能靠重跑覆盖：
有已验证回执时使用promote恢复同一digest，否则使用新版本。
CLI默认只读计划，只有显式--execute写registry：

```bash
uv run --frozen pytest -q tests/test_release_images.py
python3 scripts/release_images.py --help
python3 scripts/release_images.py --revision "$SEEKBELL_REVISION" --repository aspeternity/seekbell \
  promote --receipt release.json --version v0.1.0 --report version-plan.json
```

pack/verify/release/alias保持兼容；两种原生平台归档须来自同一次运行。
包可见性核对失败即停止，不能将个人CLI缺read:packages误报成包私有。
发布使用短期GITHUB_TOKEN，不向仓库写入个人token或Docker凭据。
现阶段无镜像签名、SBOM或独立供应链证明，校验和不等同来源签名。

## 部署与依据

公开包匿名拉取，无需docker login。正式Compose继续固定digest用于复现与回退。
升级前完整备份原卷及credentials.key；回退须匹配旧schema备份，见[维护流程](RELEASES.md)。
真实RSS、通知和实机验收仍分别授权并记录。

治理见[公开仓库](PUBLIC_REPOSITORY.md)，候选实现细节见[历史流程](history/2026-10-28-候选镜像流程.md)。
依据：[Release事件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#release)、
[GHCR权限与匿名访问](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)。
