"""Disposable real Nginx/TLS fixture on a private internal Docker network."""

import ipaddress
import json
import ssl
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

from check_container import docker

ROOT = Path(__file__).resolve().parents[1]
PROXY_IMAGE = "nginx@sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5"
CERTIFICATE = r"""
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

    def __enter__(self):
        try:
            self.temporary = tempfile.TemporaryDirectory(prefix=self.name)
            docker("network", "create", "--internal", self.network)
            network = json.loads(docker("network", "inspect", self.network).stdout)[0]
            subnet = ipaddress.ip_network(network["IPAM"]["Config"][0]["Subnet"])
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
                "client_body_temp_path /tmp/client;proxy_temp_path /tmp/proxy;" + server + "}"
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
                "-p",
                "127.0.0.1:" + (str(self.port) if self.port else "") + ":8443",
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
            proxy = json.loads(docker("container", "inspect", self.proxy).stdout)[0]
            self.port = int(proxy["NetworkSettings"]["Ports"]["8443/tcp"][0]["HostPort"])
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
        docker("rm", "--force", self.proxy, self.app, check=False)
        docker("volume", "rm", self.files, self.data, check=False)
        docker("network", "rm", self.network, check=False)
        if self.temporary:
            self.temporary.cleanup()
