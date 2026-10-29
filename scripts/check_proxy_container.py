"""Real TLS/auth/streaming rehearsal; synthetic credentials, internal Docker network only."""

import argparse
import http.cookiejar
import json
import urllib.error
import urllib.request

from check_container import docker
from check_deployment import check_container, check_endpoint
from proxy_fixture import ProxyFixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    with ProxyFixture(args.image, args.revision) as fixture:
        report = check_container(fixture.name, args.revision)
        report.update(check_endpoint(fixture.url, revision=args.revision, ca_file=fixture.ca_file))
        # The ephemeral certificate is trusted ONLY through this explicit local CA.
        try:
            check_endpoint(fixture.url, revision=args.revision)
        except urllib.error.URLError:
            pass
        else:
            raise AssertionError("Unknown test CA must be rejected")
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=fixture.context),
            urllib.request.HTTPCookieProcessor(jar),
        )
        csrf = ""

        def request(path, values=None, headers=None):
            supplied = {"X-CSRF-Token": csrf, "Origin": fixture.url, **(headers or {})}
            if values is not None:
                supplied["Content-Type"] = "application/json"
            return opener.open(
                urllib.request.Request(
                    fixture.url + "/api/" + path,
                    data=json.dumps(values).encode() if values is not None else None,
                    headers=supplied,
                ),
                timeout=30,
            )

        with request(
            "auth/status", headers={"X-Forwarded-Proto": "http", "X-Forwarded-For": "198.51.100.80"}
        ) as response:
            csrf = json.load(response)["csrf"]
            assert "; Secure" in response.headers["Set-Cookie"]
        credentials = {"username": "proxy_admin", "password": "Synthetic-Proxy-2026"}
        with request("auth/setup", credentials) as response:
            csrf = json.load(response)["csrf"]
            assert "; Secure" in response.headers["Set-Cookie"]
        with request("manage/workspace") as response:
            before = json.load(response)
        try:
            request("auth/logout", {}, {"Origin": "https://other.example.test"})
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("Cross-origin logout must be rejected")
        with request(
            "manage/backups/download",
            {"current_password": credentials["password"], "password": "Synthetic-TLS-Backup-2026"},
        ) as response:
            archive = response.read()
            assert (
                archive.startswith(b"SEEKBELL-BACKUP")
                and response.headers["Cache-Control"] == "no-store"
            )
        metadata = {
            "current_password": credentials["password"],
            "password": "Synthetic-TLS-Backup-2026",
        }
        body = json.dumps(metadata).encode() + b"\n" + archive
        with opener.open(
            urllib.request.Request(
                fixture.url + "/api/manage/backups/restore",
                data=body,
                headers={
                    "Content-Type": "application/octet-stream",
                    "X-CSRF-Token": csrf,
                    "Origin": fixture.url,
                },
            ),
            timeout=30,
        ) as response:
            assert json.load(response) == {"candidate_available": True, "activated": False}
        with request("manage/workspace") as response:
            assert json.load(response) == before
        with request("auth/logout", {}) as response:
            assert json.load(response)["ok"]
        direct = (
            "import urllib.request; "
            "r=urllib.request.urlopen(urllib.request.Request('http://"
            + fixture.app_ip
            + ":8000/api/auth/status',"
            "headers={'X-Forwarded-Proto':'https','X-Forwarded-For':'198.51.100.80'}));"
            "assert '; Secure' not in r.headers['Set-Cookie']"
        )
        docker("run", "--rm", "--network", fixture.network, args.image, "python", "-c", direct)
        logs = ""
        for container in (fixture.app, fixture.proxy):
            captured = docker("logs", container)
            logs += captured.stdout + captured.stderr
        for secret in (credentials["password"], "Synthetic-TLS-Backup-2026", csrf):
            assert secret not in logs
        report.update(
            {
                "tls_ca_verified": True,
                "real_nginx": True,
                "secure_login_logout": True,
                "csrf_origin_rejected": True,
                "proxy_overwrites_spoofed_headers": True,
                "untrusted_direct_spoof_ignored": True,
                "backup_stream_round_trip": True,
                "sample_secrets_absent_from_logs": True,
                "network": "internal",
                "proxy_image": fixture.proxy_image,
            }
        )
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
