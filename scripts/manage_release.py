"""Local Docker operator tool: prepare on a new volume, switch a pinned pair, explicit rollback.

No credentials, Docker socket, subprocesses or release controls are exposed to Web.
Use only with this repository's standard Compose service and one local operator.
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
FILES = ("compose.yaml", "compose.release.yaml", "compose.release-offline.yaml")
LABEL = "seekbell.release"


class ReleaseError(RuntimeError):
    pass


def docker(*arguments, timeout=60):
    result = subprocess.run(["docker", *arguments], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Docker diagnostics can include environment/configuration. Never print them.
        raise ReleaseError("Docker操作失败；未自动回退，请按状态检查实例。")
    return result.stdout.strip()


def inspect(kind, name):
    return json.loads(docker(kind, "inspect", name))[0]


def private_parent(path):
    parent = path.parent
    parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if parent.is_symlink() or parent.resolve() != parent.absolute():
        raise ReleaseError("状态目录不能含符号链接。")
    info = parent.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ReleaseError("状态目录必须归当前用户所有且权限0700。")


def save(path, state, *, new=False):
    if path.is_symlink() or (new and path.exists()):
        raise ReleaseError("状态文件已存在或不安全，拒绝覆盖。")
    descriptor, temp = tempfile.mkstemp(prefix=".release-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(state, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        if new:
            os.link(temp, path)
        else:
            os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temp).unlink(missing_ok=True)


def load(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
        raise ReleaseError("状态文件不可用。")
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ReleaseError("状态文件必须归当前用户所有且权限0600。")
    state = json.loads(path.read_text())
    if state.get("format") != 1:
        raise ReleaseError("不支持的维护状态版本。")
    return state


def daemon():
    host = os.environ.get("DOCKER_HOST")
    if not host:
        context = json.loads(docker("context", "inspect"))[0]
        host = context["Endpoints"]["docker"]["Host"]
    if not host.startswith("unix://"):
        raise ReleaseError("只支持Linux本机Unix socket Docker上下文。")
    return docker("info", "--format", "{{.ID}}")


@contextmanager
def project_lock(project, server):
    digest = hashlib.sha256((server + "/" + project).encode()).hexdigest()
    path = Path.home() / ".local/share/seekbell-release-locks" / (digest + ".lock")
    private_parent(path)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ReleaseError("同项目已有维护操作。") from None
        yield


def configuration():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES}


def current(project):
    ids = docker(
        "ps",
        "-aq",
        "--filter",
        "label=com.docker.compose.project=" + project,
        "--filter",
        "label=com.docker.compose.service=seekbell",
        "--filter",
        "label=com.docker.compose.oneoff=False",
    ).splitlines()
    if len(ids) != 1:
        raise ReleaseError("项目必须恰有一个已创建的标准seekbell服务容器。")
    info = inspect("container", ids[0])
    mounts = [item for item in info["Mounts"] if item["Destination"] == "/data"]
    if len(mounts) != 1 or mounts[0]["Type"] != "volume":
        raise ReleaseError("只支持/data使用命名卷的标准Compose实例。")
    persistent = [item for item in info["Mounts"] if item["Type"] in ("volume", "bind")]
    if len(persistent) != 1:
        raise ReleaseError("实例存在额外持久挂载，不能自动切换。")
    environment = dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
    data_dir = environment.get("SEEKBELL_DATA_DIR", "/data")
    path = PurePosixPath(data_dir)
    if not path.is_relative_to("/data") or ".." in path.parts:
        raise ReleaseError("数据目录必须在/data卷内。")
    if environment.get("SEEKBELL_STATIC_DIR", "/app/frontend/dist") != "/app/frontend/dist":
        raise ReleaseError("不支持自定义静态目录的实例自动切换。")
    if info["Config"]["User"] != "10001:10001" or not info["HostConfig"]["ReadonlyRootfs"]:
        raise ReleaseError("实例需使用标准非root/只读根配置。")
    allowed = {
        "SEEKBELL_DATA_DIR",
        "SEEKBELL_STATIC_DIR",
        "SEEKBELL_BUILD_REVISION",
        "SEEKBELL_TRUSTED_PROXY_IPS",
    }
    if any(key.startswith("SEEKBELL_") and key not in allowed for key in environment):
        raise ReleaseError("存在未支持的启动配置，需人工核对后维护。")
    offline = info["HostConfig"]["NetworkMode"] == "none"
    ports = info["HostConfig"].get("PortBindings") or {}
    if offline:
        if any(ports.values()):
            raise ReleaseError("离线实例不能有发布端口。")
        port = "8000"
    else:
        binding = ports.get("8000/tcp") or []
        if set(ports) != {"8000/tcp"} or len(binding) != 1 or binding[0]["HostIp"] != "127.0.0.1":
            raise ReleaseError("只支持一个127.0.0.1本机端口。")
        port = binding[0]["HostPort"]
    return {
        "trusted_proxy_ips": environment.get("SEEKBELL_TRUSTED_PROXY_IPS", ""),
        "container": info["Id"],
        "image": info["Image"],
        "volume": mounts[0]["Name"],
        "data_dir": data_dir,
        "running": info["State"]["Running"],
        "started_at": info["State"]["StartedAt"],
        "status": info["State"]["Status"],
        "restarts": info["RestartCount"],
        "offline": offline,
        "port": port,
    }


def same(actual, expected):
    return all(actual[key] == expected[key] for key in ("image", "volume", "data_dir")) and (
        actual.get("trusted_proxy_ips", "") == expected.get("trusted_proxy_ips", "")
    )


def unused(*volumes):
    for identifier in docker("ps", "-q").splitlines():
        info = inspect("container", identifier)
        if any(item.get("Name") in volumes for item in info["Mounts"]):
            raise ReleaseError("相关数据卷仍被运行中容器挂载，拒绝切换。")


def image(name):
    info = inspect("image", name)
    revision = info["Config"].get("Labels", {}).get("org.opencontainers.image.revision", "")
    if not re.fullmatch("[0-9a-f]{40}", revision) or info["Config"]["User"] != "10001:10001":
        raise ReleaseError("镜像须固定完整提交版本并使用UID/GID10001。")
    return info["Id"]


def run(image_id, mounts, *command, root=False):
    arguments = [
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
    ]
    if root:
        arguments += ["--user", "0", "--cap-add", "CHOWN"]
    for volume, target, readonly in mounts:
        arguments += [
            "--mount",
            "type=volume,src=" + volume + ",dst=" + target + (",readonly" if readonly else ""),
        ]
    return docker(*arguments, image_id, *command, timeout=240)


def source_path(state):
    relative = str(PurePosixPath(state["previous"]["data_dir"]).relative_to("/data"))
    source = "/source" + ("/" + relative if relative != "." else "")
    return source + ("/web-restore" if state["restored"] else "")


def prepare(path, project, target, *, restored=False):
    if path.exists():
        raise ReleaseError("状态文件已存在，请使用新的状态路径。")
    previous = current(project)
    if previous["running"]:
        raise ReleaseError("请先停止原服务，再准备新卷；此命令不代停日常服务。")
    unused(previous["volume"])
    target = image(target)
    image(previous["image"])
    identifier = uuid.uuid4().hex
    volume = "seekbell-release-" + identifier
    state = {
        "format": 1,
        "id": identifier,
        "project": project,
        "daemon": daemon(),
        "configuration": configuration(),
        "phase": "preparing",
        "previous": previous,
        "next": {**previous, "volume": volume, "image": target, "data_dir": "/data/release"},
        "restored": restored,
    }
    save(path, state, new=True)
    try:
        docker("volume", "create", "--label", LABEL + "=" + identifier, volume)
        run(
            target,
            [(volume, "/candidate", False)],
            "python",
            "-c",
            "import os; os.chmod('/candidate',0o700); os.chown('/candidate',10001,10001)",
            root=True,
        )
        source = source_path(state)
        # No actors/entrypoint/server, source volume mounted READ ONLY.
        run(
            target,
            [(previous["volume"], "/source", True), (volume, "/candidate", False)],
            "python",
            "-c",
            "from pathlib import Path; from seekbell.config import Settings; "
            "from seekbell.release import prepare; "
            "prepare(Settings(data_dir=Path(" + repr(source) + ")),Path('/candidate/release'))",
        )
        state["phase"] = "prepared"
    except Exception:
        state["phase"] = "prepare_failed"
        save(path, state)
        raise
    save(path, state)
    return state


def verify(state):
    if state["daemon"] != daemon() or state["configuration"] != configuration():
        raise ReleaseError("Docker上下文或Compose文件已改变，拒绝按旧状态执行。")


def compose(state, pair):
    environment = {
        **os.environ,
        "SEEKBELL_IMAGE": pair["image"],
        "SEEKBELL_RELEASE_VOLUME": pair["volume"],
        "SEEKBELL_RELEASE_DATA_DIR": pair["data_dir"],
        "SEEKBELL_PORT": pair["port"],
        "SEEKBELL_TRUSTED_PROXY_IPS": pair.get("trusted_proxy_ips", ""),
    }
    arguments = ["docker", "compose", "--project-directory", str(ROOT), "-p", state["project"]]
    for name in FILES[:2] + ((FILES[2],) if pair["offline"] else ()):
        arguments += ["-f", str(ROOT / name)]
    result = subprocess.run(
        [*arguments, "up", "-d", "--no-deps", "--force-recreate", "seekbell"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode:
        raise ReleaseError("切换启动失败；未自动回退，原卷与匹配镜像保留。")


def ready(state, pair):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        actual = current(state["project"])
        if not same(actual, pair):
            raise ReleaseError("实例与待验证镜像/卷不匹配。")
        if actual["status"] in ("exited", "dead") or actual["restarts"]:
            raise ReleaseError("新实例退出或重启，拒绝激活并停止新实例。")
        try:
            docker(
                "exec",
                actual["container"],
                "python",
                "-c",
                "import json,urllib.request; "
                "url='http://127.0.0.1:8000/health/ready'; "
                "r=json.load(urllib.request.urlopen(url,timeout=3)); "
                "assert r['status']=='ok'",
                timeout=5,
            )
            return
        except ReleaseError:
            time.sleep(0.5)
    raise ReleaseError("新实例未就绪；将停止该实例，原卷保留，不自动回退。")


def switch(path, state, *, rollback=False, accept_data_loss=False):
    verify(state)
    actual = current(state["project"])
    if not same(actual, state["previous"]) and not same(actual, state["next"]):
        raise ReleaseError("当前实例不是记录中的任一版本，拒绝操作。")
    if rollback:
        if not accept_data_loss:
            raise ReleaseError("回退会放弃切换后的数据；需明确传入--accept-data-loss。")
        pair = state["previous"]
    else:
        if state["phase"] != "prepared" or actual["running"] or not same(actual, state["previous"]):
            raise ReleaseError("仅允许原服务停服且候选已准备时激活。")
        if (
            actual["container"] != state["previous"]["container"]
            or actual["started_at"] != state["previous"]["started_at"]
        ):
            raise ReleaseError("原实例在准备后被启动或替换，请重新准备新卷。")
        pair = state["next"]
    image(pair["image"])
    inspect("volume", pair["volume"])
    if actual["running"]:
        docker("stop", "--time", "30", actual["container"])
    unused(state["previous"]["volume"], state["next"]["volume"])
    if not rollback:
        run(
            pair["image"],
            [(pair["volume"], "/data", False)],
            "python",
            "-c",
            "from pathlib import Path;from seekbell.config import Settings;"
            "from seekbell.release import check;"
            "check(Settings(data_dir=Path('/data/release')))",
        )
    if not rollback:
        run(
            pair["image"],
            [(state["previous"]["volume"], "/source", True), (pair["volume"], "/data", False)],
            "python",
            "-c",
            "from pathlib import Path;from seekbell.config import Settings;"
            "from seekbell.release import check_source;"
            "check_source(Settings(data_dir=Path("
            + repr(source_path(state))
            + ")),Path('/data/release'))",
        )
    state["phase"] = "rolling_back" if rollback else "activating"
    save(path, state)
    try:
        compose(state, pair)
        ready(state, pair)
    except Exception:
        actual = current(state["project"])
        if same(actual, pair):
            docker("stop", "--time", "30", actual["container"])
        state["phase"] = "rollback_failed" if rollback else "activation_failed"
        save(path, state)
        raise
    state["phase"] = "rolled_back" if rollback else "active"
    save(path, state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("prepare")
    create.add_argument("--project", required=True)
    create.add_argument("--image", required=True)
    create.add_argument("--restored", action="store_true", help="复制旧卷中的web-restore候选")
    actions.add_parser("status")
    actions.add_parser("activate")
    revert = actions.add_parser("rollback")
    revert.add_argument("--accept-data-loss", action="store_true")
    args = parser.parse_args()
    try:
        path = args.state.absolute()
        private_parent(path)
        state = None if args.action == "prepare" else load(path)
        project = args.project if state is None else state["project"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,80}", project):
            raise ReleaseError("项目名无效。")
        with project_lock(project, daemon()):
            if state is not None:
                state = load(path)
                if state["project"] != project:
                    raise ReleaseError("维护项目状态发生变化。")
            if args.action == "prepare":
                state = prepare(path, project, args.image, restored=args.restored)
            elif args.action in ("activate", "rollback"):
                state = switch(
                    path,
                    state,
                    rollback=args.action == "rollback",
                    accept_data_loss=getattr(args, "accept_data_loss", False),
                )
            else:
                verify(state)
            actual = current(project)
            print(
                json.dumps(
                    {
                        "phase": state["phase"],
                        "project": project,
                        "observed": "next"
                        if same(actual, state["next"])
                        else "previous"
                        if same(actual, state["previous"])
                        else "unknown",
                        "running": actual["running"],
                        "previous_retained": state["previous"]["volume"],
                        "candidate_retained": state["next"]["volume"],
                    }
                )
            )
    except ReleaseError as error:
        print("维护未完成：" + str(error), file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        print(
            "维护未完成：请检查停服、固定镜像、状态文件及维护说明。未自动删除任何数据卷或回退；原卷保留。",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
