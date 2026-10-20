import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from seekbell.config import Settings
from seekbell.main import create_app


@pytest.mark.parametrize(
    "value",
    ["*", "0.0.0.0", "::", "192.0.2.0/24", "localhost", "192.0.2.5,", "ff02::1", "fe80::1%eth0"],
)
def test_unsafe_proxy_settings_are_rejected(value):
    with pytest.raises(ValidationError):
        Settings(trusted_proxy_ips=value)


def test_proxy_ips_are_canonical_and_default_disabled():
    assert Settings().trusted_proxy_ips == ""
    assert (
        Settings(trusted_proxy_ips="192.0.2.10, ::1,192.0.2.10").trusted_proxy_ips
        == "192.0.2.10,::1"
    )


@pytest.mark.parametrize(
    "trusted,peer,secure",
    [
        ("", "192.0.2.10", False),
        ("192.0.2.10", "192.0.2.11", False),
        ("192.0.2.10", "192.0.2.10", True),
    ],
)
def test_only_the_exact_trusted_peer_can_change_scheme_and_https_origin(
    tmp_path, trusted, peer, secure
):
    app = create_app(Settings(data_dir=tmp_path, trusted_proxy_ips=trusted))
    headers = {
        "host": "seekbell.example.test:8443",
        "x-forwarded-proto": "https",
        "x-forwarded-for": "198.51.100.25",
    }
    with TestClient(
        app, base_url="http://seekbell.example.test:8443", client=(peer, 1234), headers=headers
    ) as client:
        response = client.get("/api/auth/status")
        assert ("; Secure" in response.headers["set-cookie"]) == secure
        assert response.headers["cache-control"] == "no-store"
        nonce = response.cookies.get("seekbell_preauth")
        client.cookies.clear()
        client.cookies.set("seekbell_preauth", nonce)
        client.headers.update(
            {
                "x-csrf-token": response.json()["csrf"],
                "origin": "https://seekbell.example.test:8443",
            }
        )
        result = client.post(
            "/api/auth/setup", json={"username": "proxy_admin", "password": "Synthetic-Proxy-2026"}
        )
        assert result.status_code == (200 if secure else 403)
        if secure:
            assert "; Secure" in result.headers["set-cookie"]
            session = result.cookies.get("seekbell_session")
            client.cookies.clear()
            client.cookies.set("seekbell_session", session)
            client.headers["x-csrf-token"] = result.json()["csrf"]
            assert client.get("/api/manage/workspace").status_code == 200
            client.headers["origin"] = "https://other.example.test:8443"
            assert client.post("/api/auth/logout").status_code == 403
            client.headers["origin"] = "https://seekbell.example.test:8443"
            assert client.post("/api/auth/logout").status_code == 200


def test_direct_http_still_works_with_an_explicit_proxy_config(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, trusted_proxy_ips="192.0.2.10"))
    with TestClient(app) as client:
        response = client.get("/api/auth/status")
        assert "; Secure" not in response.headers["set-cookie"]
        client.headers["x-csrf-token"] = response.json()["csrf"]
        assert (
            client.post(
                "/api/auth/setup",
                json={"username": "local_admin", "password": "Synthetic-HTTP-2026"},
            ).status_code
            == 200
        )


def checker():
    spec = importlib.util.spec_from_file_location(
        "check_deployment", Path(__file__).resolve().parents[1] / "scripts/check_deployment.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test",
        "https://admin:password@example.test",
        "https://example.test/?secret=value",
        "https://example.test/path",
        "https://example.test/#secret",
    ],
)
def test_preflight_rejects_unsafe_or_redirectable_base_urls_without_network(url):
    tool = checker()
    with pytest.raises(tool.CheckError):
        tool.endpoint_url(url)


def test_release_pair_identity_includes_proxy_setting():
    from tests.test_release import operator

    tool = operator()
    original = {"image": "old", "volume": "data", "data_dir": "/data"}
    assert tool.same(original, {**original, "trusted_proxy_ips": ""})
    assert not tool.same(original, {**original, "trusted_proxy_ips": "192.0.2.10"})


def test_preflight_container_guards_detect_exposed_ports_and_unsafe_runtime():
    import copy

    tool = checker()
    info = {
        "Config": {
            "Env": ["SEEKBELL_BUILD_REVISION=" + "a" * 40],
            "User": "10001:10001",
            "Cmd": ["uvicorn", "--no-proxy-headers", "--no-access-log"],
        },
        "HostConfig": {
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "PortBindings": {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8000"}]},
        },
        "Mounts": [{"Destination": "/data", "Type": "volume"}],
        "State": {"Running": True},
        "RestartCount": 0,
    }
    assert tool.container_report(info, "a" * 40)["proxy_headers"] == "disabled"
    mutations = [
        lambda item: item["HostConfig"]["PortBindings"]["8000/tcp"][0].update(HostIp="0.0.0.0"),
        lambda item: item["HostConfig"].update(ReadonlyRootfs=False),
        lambda item: item["HostConfig"].update(SecurityOpt=["no-new-privileges:false"]),
        lambda item: item["Config"].update(User="0"),
        lambda item: item["Config"].update(
            Cmd=["uvicorn", "--proxy-headers", "--forwarded-allow-ips", "*"]
        ),
        lambda item: item["Config"]["Env"].append("SEEKBELL_TRUSTED_PROXY_IPS=*"),
        lambda item: item["Mounts"][0].update(Type="bind"),
    ]
    for mutate in mutations:
        unsafe = copy.deepcopy(info)
        mutate(unsafe)
        with pytest.raises((tool.CheckError, ValueError)):
            tool.container_report(unsafe, "a" * 40)
