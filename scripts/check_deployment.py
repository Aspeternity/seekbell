"""Read-only deployment preflight. Never enables a source, logs in, sends or migrates."""

import argparse
import ipaddress
import json
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookies import SimpleCookie
from pathlib import Path

MAX_RESPONSE = 256 * 1024


class CheckError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        raise CheckError("检查地址发生跳转；请直接使用正确的站点根地址。")


def endpoint_url(value, allow_http=False):
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme not in ({"https", "http"} if allow_http else {"https"})
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise CheckError("请填写无账号/参数/子路径的HTTPS站点根地址。")
    if parsed.scheme == "http":
        try:
            local = (
                parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
            )
        except ValueError:
            local = False
        if not local:
            raise CheckError("直接HTTP检查仅限本机回环地址。")
    return value.rstrip("/")


def check_endpoint(url, *, revision, ca_file=None, allow_http=False):
    url = endpoint_url(url, allow_http)
    context = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context), NoRedirect()
    )

    def get(path):
        with opener.open(url + path, timeout=10) as response:
            body = response.read(MAX_RESPONSE + 1)
            if len(body) > MAX_RESPONSE or response.status != 200:
                raise CheckError("部署端点响应状态或大小无效。")
            data = json.loads(body)
            if not isinstance(data, dict):
                raise CheckError("部署端点JSON格式无效。")
            return data, response.headers

    for path in ("/health/live", "/health/ready"):
        info, _ = get(path)
        if info.get("status") != "ok":
            raise CheckError("实例未存活或未就绪。")
    info, _ = get("/api/version")
    if info.get("name") != "SeekBell" or info.get("build_revision") != revision:
        raise CheckError("站点代码版本与指定提交不匹配。")
    info, headers = get("/api/auth/status")
    if info.get("authenticated") is not False or not isinstance(info.get("initialized"), bool):
        raise CheckError("匿名认证状态响应无效。")
    cookie = SimpleCookie()
    for value in headers.get_all("Set-Cookie", []):
        cookie.load(value)
    record = cookie.get("seekbell_preauth")
    https = urllib.parse.urlsplit(url).scheme == "https"
    if (
        record is None
        or not record["httponly"]
        or record["samesite"].lower() != "strict"
        or bool(record["secure"]) != https
        or headers.get("Cache-Control") != "no-store"
    ):
        raise CheckError("Cookie/缓存配置不符合访问协议；请检查可信代理IP及转发头。")
    return {
        "endpoint": "passed",
        "transport": "https" if https else "http",
        "revision": revision,
        "tls_verified": https,
        "preauth_cookie": "passed",
        "initialized": info["initialized"],
    }


def docker(*args):
    result = subprocess.run(["docker", *args], text=True, capture_output=True, timeout=20)
    if result.returncode:
        raise CheckError("Docker只读检查失败。")
    return result.stdout


def container_report(info, revision):
    config, host = info["Config"], info["HostConfig"]
    environment = dict(item.split("=", 1) for item in config["Env"] if "=" in item)
    if environment.get("SEEKBELL_BUILD_REVISION") != revision:
        raise CheckError("容器构建版本不匹配。")
    if (
        config.get("User") != "10001:10001"
        or not host.get("ReadonlyRootfs")
        or "ALL" not in (host.get("CapDrop") or [])
        or not any(
            item in ("no-new-privileges", "no-new-privileges:true")
            for item in (host.get("SecurityOpt") or [])
        )
    ):
        raise CheckError("容器权限与标准只读非root配置不匹配。")
    mounts = [item for item in info["Mounts"] if item["Destination"] == "/data"]
    if (
        len(mounts) != 1
        or mounts[0]["Type"] != "volume"
        or len([item for item in info["Mounts"] if item["Type"] in ("bind", "volume")]) != 1
    ):
        raise CheckError("/data必须是明确的持久命名卷。")
    ports = host.get("PortBindings") or {}
    bindings = ports.get("8000/tcp") or []
    if set(ports) != {"8000/tcp"} or len(bindings) != 1 or bindings[0]["HostIp"] != "127.0.0.1":
        raise CheckError("应用端口必须仅发布到127.0.0.1。")
    if not info["State"]["Running"] or info.get("RestartCount", 0):
        raise CheckError("实例未运行或已有重启，需要先核对。")
    command = config.get("Cmd") or []
    if (
        "--no-proxy-headers" not in command
        or "--no-access-log" not in command
        or "--proxy-headers" in command
        or "--forwarded-allow-ips" in command
        or config.get("Entrypoint")
    ):
        raise CheckError("请使用标准单入口及关闭访问日志的固定镜像命令。")
    trusted = environment.get("SEEKBELL_TRUSTED_PROXY_IPS", "")
    for item in trusted.split(",") if trusted else []:
        address = ipaddress.ip_address(item.strip())
        if address.is_unspecified or address.is_multicast or "%" in item:
            raise CheckError("可信代理须为明确IP，不能通配。")
    return {
        "container": "passed",
        "revision": revision,
        "local_port_only": True,
        "persistent_volume": True,
        "proxy_headers": "explicit" if trusted else "disabled",
    }


def check_container(project, revision):
    ids = docker(
        "ps",
        "-aq",
        "--filter",
        "label=com.docker.compose.project=" + project,
        "--filter",
        "label=com.docker.compose.service=seekbell",
        "--filter",
        "label=com.docker.compose.oneoff=False",
    ).split()
    if len(ids) != 1:
        raise CheckError("项目须恰有一个seekbell服务容器。")
    return container_report(json.loads(docker("container", "inspect", ids[0]))[0], revision)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project")
    parser.add_argument("--url")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--allow-http", action="store_true", help="仅检查直接本机HTTP模式")
    args = parser.parse_args()
    try:
        if (not args.project and not args.url) or not re.fullmatch("[0-9a-f]{40}", args.revision):
            raise CheckError("须指定项目或站点，以及完整40位提交版本。")
        result = {}
        if args.project:
            result.update(check_container(args.project, args.revision))
        if args.url:
            result.update(
                check_endpoint(
                    args.url,
                    revision=args.revision,
                    ca_file=args.ca_file,
                    allow_http=args.allow_http,
                )
            )
        print(json.dumps(result))
    except CheckError as error:
        print("检查未通过：" + str(error), file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError, KeyError, urllib.error.URLError, subprocess.TimeoutExpired):
        print(
            "检查未通过：请检查证书、站点/版本、就绪状态或Docker配置。检查未修改业务配置。",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
