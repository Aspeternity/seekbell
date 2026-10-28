# 公开镜像与版本发布

源码与GHCR包均公开。正式版本、固定digest部署文件和回执以
[GitHub Releases](https://github.com/Aspeternity/seekbell/releases)为准。
下载前确认对应版本的镜像发布Actions完整成功；Release条目会先于镜像构建完成。

## 版本与部署引用

Git标签/Release使用vX.Y.Z，镜像使用X.Y.Z；0.1.0正式版对应
`ghcr.io/aspeternity/seekbell:0.1.0`。
GitHub最新正式Release在检查全部通过后同时更新latest；
预发布vX.Y.Z-alpha.N、-beta.N、-rc.N（N从1开始）只生成自身标签。
补发旧正式Release且未被设为GitHub最新版本时，也只生成自身标签。

源码中的[8000](../deploy/compose.portainer.yaml)和[8001](../deploy/compose.portainer.compare.yaml)
模板固定明确版本；Release附件在相同版本上追加已验证的索引digest，例如
`ghcr.io/aspeternity/seekbell:0.1.0@sha256:…`。
正式升级优先下载Release附件的同名Compose，核对deployment.json；不会随latest漂移。
更新现有Portainer Stack，保留Stack名、端口和实际数据卷；使用自定义配置时仅替换image更稳妥。

同版本不同digest拒绝覆盖；同版本同digest可从已验证回执恢复。v*标签禁止更新/删除。
SHA、运行编号和架构标签保留供追溯，日常部署使用版本号或Release的固定digest引用。
镜像的真实身份以digest为准，不能假定有写权限的管理员永远不会手动改标签。

## 正式发布

1. 在分支中更新pyproject.toml、uv.lock、frontend/package.json、两份Portainer模板的版本和CHANGELOG，
   通过PR合并main。正式0.1.0对应v0.1.0；Python的0.1.0rc1对应v0.1.0-rc.1。
   前端/Compose的预发布标签使用SemVer形式；应用版本使用PEP 440形式。
2. 在本次明确发布授权下，为main上选定完整提交创建v*标签、发布GitHub Release。
   预发布勾选pre-release，正式发布按需要设为latest；草稿和普通push/PR不写GHCR。
3. Versioned images and manual candidates核对标签、版本、main祖先关系和源码/包public，
   执行完整baseline，再由ubuntu-24.04和ubuntu-24.04-arm原生构建并离线演练。
4. 发布复用同次测试归档中的配置和层，不重新构建；分别推送平台后组合、核对双架构索引。
   按digest拉取并完成禁外网容器检查后，才添加版本标签及受控latest。
5. 由已发布version.json生成固定digest的两份Compose，保留各自端口、卷名和安全选项，
   验证Compose配置；生成记录SHA256的deployment.json。
6. 独立contents:write job把release.json、package.json、version.json、deployment.json及两份Compose
   上传到Release。构建/发布job仅持contents:read/packages:write。整个运行成功后才宣告镜像发布完成。

所有镜像发布使用同一串行并发组。Release条目出现不表示镜像已完成；失败要检查Actions和回执。
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
  promote --receipt release.json --version v0.1.0 --report version-plan.json
python3 scripts/release_images.py --revision "$SEEKBELL_REVISION" --repository aspeternity/seekbell \
  compose --receipt version.json --version v0.1.0 --templates deploy --output release-assets
```

pack/verify/release/alias保持兼容，两平台归档必须来自同一次运行。
包可见性失败即停止；个人CLI缺read:packages不代表包私有，不为核对扩张个人token权限。
发布使用短期GITHUB_TOKEN，公开包支持匿名拉取，无需docker login。

## 安全升级与历史

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
