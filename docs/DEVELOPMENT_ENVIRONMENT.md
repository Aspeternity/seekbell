# 本机开发环境

用户于2026-10-18确认新建独立WSL，安装位置`D:\WSL\SeekBell-Dev`。本文件描述实际本机配置，不改变产品技术栈或PVE部署目标。M0源码保留待审，尚未开展M1。

## 位置与进入方式

|项目|配置|
|---|---|
|发行版|`SeekBell-Dev`，WSL2，Ubuntu 24.04.5 LTS，amd64|
|虚拟磁盘|`D:\WSL\SeekBell-Dev\ext4.vhdx`|
|默认用户|`dev`，UID/GID 1000，普通用户|
|正式开发目录|`/home/dev/projects/seekbell`，新发行版内部ext4|
|Windows访问目录|`\\wsl.localhost\SeekBell-Dev\home\dev\projects\seekbell`|
|原目录|`D:\Projects\SeekBell`，保留交接副本；不要两边同时开发|
|开发数据库|`/home/dev/.local/share/seekbell-dev/seekbell.sqlite3`，仅M0安装标记|

Windows PowerShell/终端：

```powershell
wsl.exe -d SeekBell-Dev --cd /home/dev/projects/seekbell
```

进入后先确认`echo "$WSL_DISTRO_NAME"`为`SeekBell-Dev`、`pwd`为上述正式目录。当前聊天仍可能从原Ubuntu执行工具；此时所有开发/构建/测试均显式通过`wsl.exe -d SeekBell-Dev`派发，不能误用原Ubuntu或D盘源码。Windows编辑器打开上述UNC目录或连接指定发行版，不需改变Windows默认WSL。

## 工具链

Python 3.12.3、uv 0.13.1、Node 24.22.0、pnpm 10.34.7。项目依赖分别位于`.venv`和`frontend/node_modules`，按已有锁文件安装，不复制原目录的依赖、数据库或环境文件。完整Git提交历史由本地bundle复制。此后用户提供私有GitHub仓库`Aspeternity/seekbell`，正式目录配置origin；D盘目录仅保留交接历史。Git认证使用本机Windows GitHub CLI的凭据库helper，不复制token，helper配置仅在.git/config，不入Git。

uv及命令链接位于`/home/dev/.local/bin`；Node/pnpm本体位于`/home/dev/.local/share/seekbell-tools`，Node通过官方SHASUMS256校验。`.profile`和`.bashrc`加载`~/.config/seekbell/environment.sh`，只在这个新发行版设置用户PATH和`DOCKER_CONTEXT=rootless`。`/etc/wsl.conf`开启systemd、默认用户dev、`appendWindowsPath=false`，避免混用Windows Node。

dev没有设置密码或免密sudo。需要维护新发行版系统配置时，Windows用户显式进入`wsl.exe -d SeekBell-Dev -u root`；没有创建应用管理员。

## 独立Docker

Docker Engine 29.9.1（官方Ubuntu仓库）、Buildx 0.38.0、Compose 5.6.0。使用普通用户dev的Rootless模式：

- 上下文：`rootless`；socket：`unix:///run/seekbell-docker/docker.sock`。
- 镜像/卷数据：`/home/dev/.local/share/docker`，属于新发行版。
- 服务：新发行版的`/etc/systemd/system/seekbell-docker.service`，启用自启动，`User=dev`，执行`dockerd-rootless.sh`。
- 新发行版的系统级`docker.service`、`docker.socket`、`containerd.service`已mask，防止意外启动第二套rootful服务。
- WSLg会覆盖`/run/user/1000`，使首次常规Rootless用户服务看不到D-Bus。实际采用systemd系统单元以dev身份运行，由systemd `RuntimeDirectory`管理`/run/seekbell-docker`作为`XDG_RUNTIME_DIR`，避免WSLg覆盖和冷启动残留PID；不修改全局WSLg/WSL配置。旧的用户服务自动安装路线未继续使用。
- 当前Rootless cgroup driver为none，容器级CPU/内存限额不可用；不是宿主机资源隔离方案。未来需要限额时单独评估，不能擅改全局WSL参数。

新发行版内核对：

```bash
docker context show
docker context inspect rootless --format '{{json .Endpoints.docker.Host}}'
docker info --format '{{.ServerVersion}} {{.DockerRootDir}} {{json .SecurityOptions}}'
systemctl status seekbell-docker.service --no-pager
```

只重启此Docker服务时，从Windows执行：

```powershell
wsl.exe -d SeekBell-Dev -u root -- systemctl restart seekbell-docker.service
```

本机原Ubuntu的Docker仍在原位置，未迁移/清空/停止；原发行版安装的SeekBell工具和缓存保留，未经用户授权不清理。不得用`wsl --shutdown`或全局Docker prune作为本项目维护步骤。

## 验证与边界

新环境使用M0实现代码`1ddea580bbfc314a9e9df97bd2e95e375a2d0202`，仅额外更新文档。11项pytest、Ruff、锁校验、wheel、前端类型/格式/构建、数据库维护检查已通过；独立Docker在新发行版重启后已恢复，镜像构建和容器复核结果见PROJECT_STATE及[迁移记录](history/2026-10-18-开发环境迁移.md)。日常检查命令继续使用README。

未更改默认发行版、全局`.wslconfig`或原Ubuntu系统配置；多个WSL仍共享宿主机CPU/内存及部分网络环境，不承诺完全不影响其他项目。临时容器使用`--network none`；不访问真实论坛或通知服务。PVE/arm64/远程CI/页面体验及用户验收未完成。已实现、自动验证与用户验收分别记录。
