"""Deployment mount contracts; Docker merge/runtime checks are run separately."""

from pathlib import Path

import pytest
import yaml


PROJECT_DIR = Path(__file__).resolve().parents[3]
DATA_ROOTS = {
    "prod": "/mnt/DataDepartmentTest/home/wjl/data_set",
    "test": "/mnt/DataDepartmentTest/home/wjl/data_set_dev",
}
SOURCE_DATA = "/DataDepartment/SourceData"


def service(filename):
    content = yaml.safe_load((PROJECT_DIR / filename).read_text(encoding="utf-8"))
    return content["services"]["clpainter"]


@pytest.mark.parametrize("filename", (
    "docker-compose.yml", "docker-compose.prod.yml", "docker-compose.test.yml",
))
def test_mounts_use_explicit_colon_short_syntax(filename):
    mounts = service(filename).get("volumes", [])
    assert mounts, filename
    for mount in mounts:
        assert isinstance(mount, str), mount
        parts = mount.split(":")
        assert len(parts) == 3 and parts[2] in {"ro", "rw"}, mount
        assert parts[0].startswith("/") and parts[1].startswith("/"), mount


def test_shared_service_only_mounts_read_only_source_data():
    shared = service("docker-compose.yml")
    assert shared["volumes"] == [f"{SOURCE_DATA}:{SOURCE_DATA}:ro"]
    # Privileged mode is explicitly retained; this contract only narrows bind mounts.
    assert shared["privileged"] is True


@pytest.mark.parametrize("environment", DATA_ROOTS)
def test_each_environment_only_mounts_its_own_writable_data(environment):
    root = DATA_ROOTS[environment]
    override = service(f"docker-compose.{environment}.yml")
    assert override["volumes"] == [f"{root}:{root}:rw"]
    assert override.get("privileged", True) is True
    mounts = service("docker-compose.yml")["volumes"] + override["volumes"]
    targets = [mount.split(":")[1] for mount in mounts]
    assert len(targets) == len(set(targets))


@pytest.mark.parametrize("environment", DATA_ROOTS)
def test_environment_paths_stay_under_the_mounted_data_root(environment):
    root = Path(DATA_ROOTS[environment])
    text = (PROJECT_DIR / "deploy" / "env" / f"{environment}.env").read_text(encoding="utf-8")
    values = dict(line.split("=", 1) for line in text.splitlines() if line and not line.startswith("#"))
    for name in ("DATA_DIR", "OLD_DATA_DIR", "CACHE_DUMP_DIR", "DB_PATH"):
        assert root in Path(values[name]).parents, (name, values[name])
