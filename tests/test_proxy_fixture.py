"""Exercise explicit Docker IPAM reservation without creating real host networks."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def fixture_tool(monkeypatch):
    scripts = Path(__file__).parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "proxy_fixture_test", scripts / "proxy_fixture.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("overlaps", [0, 1, 3])
def test_declared_subnet_is_reserved_before_static_ips(fixture_tool, monkeypatch, overlaps):
    calls, occupied, reservations = [], False, 0

    def docker(*args, check=True):
        nonlocal occupied, reservations
        calls.append(args)
        if args[:2] == ("network", "inspect"):
            assert occupied
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps(
                    [{"IPAM": {"Config": [{"Subnet": "fd00::/64"}, {"Subnet": "172.30.0.0/24"}]}}]
                ),
                "",
            )
        if args[:2] == ("network", "rm"):
            occupied = False
        if args[:2] == ("network", "create"):
            assert not occupied
            if "--subnet" in args:
                reservations += 1
                if reservations <= overlaps:
                    return subprocess.CompletedProcess(args, 1, "", "Pool overlaps with other one")
                assert args[-2] == "172.30.0.0/24"
            occupied = True
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(fixture_tool, "docker", docker)
    if overlaps == 3:
        with pytest.raises(RuntimeError):
            fixture_tool.create_internal_network("only-this-fixture")
        assert not occupied
    else:
        subnet = fixture_tool.create_internal_network("only-this-fixture")
        assert str(subnet[10]) == "172.30.0.10"
        assert occupied
    assert reservations == min(overlaps + 1, 3)
    assert all(args[-1] == "only-this-fixture" for args in calls)
    assert all("--internal" in args for args in calls if args[1] == "create")


@pytest.mark.parametrize("subnets", [["fd00::/64"], ["172.30.0.0/28"]])
def test_unusable_auto_subnet_is_removed(fixture_tool, monkeypatch, subnets):
    calls = []

    def docker(*args, check=True):
        calls.append(args)
        return subprocess.CompletedProcess(
            args,
            0,
            json.dumps([{"IPAM": {"Config": [{"Subnet": subnet} for subnet in subnets]}}]),
            "",
        )

    monkeypatch.setattr(fixture_tool, "docker", docker)
    with pytest.raises(ValueError):
        fixture_tool.create_internal_network("only-this-fixture")
    assert calls[-1] == ("network", "rm", "only-this-fixture")


def test_non_overlap_engine_error_is_not_retried(fixture_tool, monkeypatch):
    calls = []

    def docker(*args, check=True):
        calls.append(args)
        if "--subnet" in args:
            return subprocess.CompletedProcess(args, 1, "", "synthetic daemon rejection")
        return subprocess.CompletedProcess(
            args, 0, json.dumps([{"IPAM": {"Config": [{"Subnet": "172.30.0.0/24"}]}}]), ""
        )

    monkeypatch.setattr(fixture_tool, "docker", docker)
    with pytest.raises(subprocess.CalledProcessError):
        fixture_tool.create_internal_network("only-this-fixture")
    assert sum("--subnet" in args for args in calls) == 1
