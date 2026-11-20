"""Exercise dataset failure policy through actual pytest subprocesses."""

import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET



PROJECT_DIR = Path(__file__).resolve().parents[3]


def isolated_env(tmp_path: Path) -> dict:
    root = tmp_path / "test_data"
    env = os.environ.copy()
    env.update(APP_ENV="development", DATA_DIR=str(root / "pv_data"),
               OLD_DATA_DIR=str(root / "old_pv_data"), CACHE_DUMP_DIR=str(root / "dump" / "curated"),
               DB_PATH=str(root / "instrument.db"), LOG_FILE=str(tmp_path / "app.log"),
               PYTHONPATH=str(PROJECT_DIR.parent), PYTHONDONTWRITEBYTECODE="1")
    return env


def run_pytest(tmp_path: Path, env: dict, target: str):
    xml_path = tmp_path / "result.xml"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", target, "--junitxml=" + str(xml_path)],
        cwd=PROJECT_DIR, env=env, capture_output=True, text=True, timeout=45,
    )
    assert xml_path.is_file(), result.stdout + result.stderr
    cases = ET.parse(xml_path).findall(".//testcase")
    assert cases and not any(case.find("skipped") is not None for case in cases)
    return result, cases


def test_missing_curated_data_fails_instead_of_skipping(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)
    result, cases = run_pytest(
        tmp_path, env, "web/backend/tests/test_confirmed_splits.py::test_confirmed_split_is_applied[688611SH]",
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Required curated test data directory is missing" in result.stdout
    assert env["CACHE_DUMP_DIR"] in result.stdout
    assert len(cases) == 1 and cases[0].find("error") is not None


def test_missing_raw_data_fails_instead_of_skipping(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)
    Path(env["CACHE_DUMP_DIR"]).mkdir(parents=True)
    result, cases = run_pytest(
        tmp_path, env, "web/backend/tests/test_xianduan_pipeline.py::test_raw_rebuild_uses_explicit_reference[S1]",
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Required raw test data directory is missing" in result.stdout
    assert env["DATA_DIR"] in result.stdout
    assert len(cases) == 1 and cases[0].find("error") is not None


def test_pure_postprocess_tests_do_not_require_dataset(tmp_path: Path) -> None:
    result, cases = run_pytest(
        tmp_path, isolated_env(tmp_path),
        "web/backend/tests/test_xianduan_pipeline.py::test_postprocess_order_and_dataflow",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(cases) == 2
    assert all(case.find("error") is None and case.find("failure") is None for case in cases)
