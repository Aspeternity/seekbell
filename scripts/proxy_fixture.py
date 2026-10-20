"""Disposable real Nginx/TLS fixture on a private internal Docker network."""

import ipaddress
import json
import os
import socket
import socketserver
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
from contextlib import suppress
from pathlib import Path

from check_container import docker

ROOT = Path(__file__).resolve().parents[1]
PROXY_IMAGE = "nginx@sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5"
CERTIFICATE = r"""
from contextlib import suppress
from pathlib import Path
from datetime import datetime,timedelta,timezone
import os,ipaddress
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
root=Path('/fixture')
ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
now=datetime.now(timezone.utc)
name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'SeekBell ephemeral test CA')])
ca=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
    .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5))
    .not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=0),True)
    .sign(ca_key,hashes.SHA256()))
server=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')]))
        .issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),False)
        .sign(ca_key,hashes.SHA256()))
(root/'ca.crt').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
(root/'server.crt').write_bytes(server.public_bytes(serialization.Encoding.PEM))
(root/'server.key').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
(root/'server.key').chmod(0o600)
os.chown(root/'server.key',101,101)
"""


class TLSRelay:
    """Opaque TCP bytes through exec; Docker internal networks do not publish ports.

    TLS still terminates in Nginx. No external route or host CA installation.
    """

    def __init__(self, container, port):
        self.active, self.lock = set(), threading.Lock()
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                connection = self.request
                connection.settimeout(30)
                process = subprocess.Popen(
                    ["docker", "exec", "-i", container, "nc", "127.0.0.1", "8443"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                )
                with owner.lock:
                    owner.active.add((process, connection))

                def receive():
                    try:
                        while block := os.read(process.stdout.fileno(), 65536):
                            connection.sendall(block)
                    except OSError:
                        pass
                    finally:
                        with suppress(OSError):
                            connection.shutdown(socket.SHUT_RDWR)

                threading.Thread(target=receive, daemon=True).start()
                try:
                    while block := connection.recv(4096):
                        process.stdin.write(block)
                except OSError:
                    pass
                finally:
                    process.stdin.close()
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    process.stdout.close()
                    with owner.lock:
                        owner.active.discard((process, connection))

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = False

        self.server = Server(("127.0.0.1", port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        with self.lock:
            for process, connection in self.active:
                with suppress(OSError):
                    connection.shutdown(socket.SHUT_RDWR)
                if process.poll() is None:
                    process.terminate()


def create_internal_network(name):
    # Ask Docker for a free, host-compatible subnet, then declare it explicitly.
    # Older Engines reject --ip on networks with only implicit IPAM configuration.
    for _ in range(3):
        docker("network", "create", "--internal", name)
        try:
            details = json.loads(docker("network", "inspect", name).stdout)[0]
            subnets = [ipaddress.ip_network(item["Subnet"]) for item in details["IPAM"]["Config"]]
            subnet = next((item for item in subnets if item.version == 4), None)
            if subnet is None or subnet.num_addresses < 32:
                raise ValueError("TLS fixture needs an IPv4 subnet with at least 32 addresses")
        finally:
            docker("network", "rm", name)
        result = docker(
            "network", "create", "--internal", "--subnet", str(subnet), name, check=False
        )
        if result.returncode == 0:
            return subnet
        # Another concurrent creator may reserve the released pool first.
        if "pool overlaps" not in result.stderr.lower():
            result.check_returncode()
    raise RuntimeError("Could not reserve the isolated TLS fixture subnet")


class ProxyFixture:
    def __init__(self, image, revision, *, port=0, proxy_image=PROXY_IMAGE):
        details = json.loads(docker("image", "inspect", image).stdout)[0]
        if details["Config"].get("Labels", {}).get("org.opencontainers.image.revision") != revision:
            raise ValueError("Fixture image revision mismatch")
        self.image, self.revision, self.port, self.proxy_image = (
            details["Id"],
            revision,
            port,
            proxy_image,
        )
        self.name = "seekbell-proxy-check-" + uuid.uuid4().hex[:12]
        self.app = self.name + "-app"
        self.proxy = self.name + "-proxy"
        self.data, self.files = self.name + "-data", self.name + "-files"
        self.network = self.name + "-network"
        self.temporary = None
        self.relay = None

    def __enter__(self):
        try:
            self.temporary = tempfile.TemporaryDirectory(prefix=self.name)
            subnet = create_internal_network(self.network)
            self.proxy_ip, self.app_ip = str(subnet[10]), str(subnet[20])
            for volume in (self.data, self.files):
                docker("volume", "create", volume)
            template = (ROOT / "deploy/nginx.conf.example").read_text()
            start = template.index("server {", template.index("server {") + 1)
            server = (
                template[start:]
                .replace("listen 443 ssl;", "listen 8443 ssl;")
                .replace("seekbell.example.test", "localhost")
                .replace("/etc/nginx/tls/seekbell.crt", "/fixture/server.crt")
                .replace("/etc/nginx/tls/seekbell.key", "/fixture/server.key")
                .replace("http://127.0.0.1:8000", "http://" + self.app_ip + ":8000")
            )
            config = (
                "worker_processes 1;pid /tmp/nginx.pid;error_log stderr crit;"
                "events {worker_connections 128;}http {access_log off;"
                "client_body_temp_path /tmp/client;proxy_temp_path /tmp/proxy;"
                "fastcgi_temp_path /tmp/fastcgi;uwsgi_temp_path /tmp/uwsgi;"
                "scgi_temp_path /tmp/scgi;" + server + "}"
            )
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "0",
                "--cap-add",
                "CHOWN",
                "-v",
                self.files + ":/fixture",
                self.image,
                "python",
                "-c",
                CERTIFICATE + "\n(root/'nginx.conf').write_text(" + repr(config) + ")",
            )
            self.ca_file = Path(self.temporary.name) / "ca.crt"
            self.ca_file.write_text(
                docker(
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "-v",
                    self.files + ":/fixture:ro",
                    self.image,
                    "cat",
                    "/fixture/ca.crt",
                ).stdout
            )
            self.context = ssl.create_default_context(cafile=str(self.ca_file))
            docker(
                "run",
                "-d",
                "--name",
                self.app,
                "--network",
                self.network,
                "--ip",
                self.app_ip,
                "--label",
                "com.docker.compose.project=" + self.name,
                "--label",
                "com.docker.compose.service=seekbell",
                "--label",
                "com.docker.compose.oneoff=False",
                "--read-only",
                "--tmpfs",
                "/tmp",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "-p",
                "127.0.0.1::8000",
                "-e",
                "SEEKBELL_TRUSTED_PROXY_IPS=" + self.proxy_ip,
                "-v",
                self.data + ":/data",
                self.image,
            )
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "101:101",
                "--read-only",
                "--tmpfs",
                "/tmp",
                "-v",
                self.files + ":/fixture:ro",
                "--entrypoint",
                "nginx",
                self.proxy_image,
                "-t",
                "-c",
                "/fixture/nginx.conf",
            )
            docker(
                "run",
                "-d",
                "--name",
                self.proxy,
                "--network",
                self.network,
                "--ip",
                self.proxy_ip,
                "--read-only",
                "--tmpfs",
                "/tmp",
                "--cap-drop",
                "ALL",
                "--user",
                "101:101",
                "--security-opt",
                "no-new-privileges:true",
                "-v",
                self.files + ":/fixture:ro",
                "--entrypoint",
                "nginx",
                self.proxy_image,
                "-c",
                "/fixture/nginx.conf",
                "-g",
                "daemon off;",
            )
            self.relay = TLSRelay(self.proxy, self.port)
            self.port = self.relay.port
            self.url = "https://127.0.0.1:" + str(self.port)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(
                        self.url + "/health/ready", context=self.context, timeout=2
                    ) as response:
                        if json.load(response)["status"] == "ok":
                            return self
                except (OSError, ValueError):
                    time.sleep(0.25)
            raise RuntimeError("Disposable TLS proxy did not become ready")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        if self.relay:
            self.relay.close()
        docker("rm", "--force", self.proxy, self.app, check=False)
        docker("volume", "rm", self.files, self.data, check=False)
        docker("network", "rm", self.network, check=False)
        if self.temporary:
            self.temporary.cleanup()
