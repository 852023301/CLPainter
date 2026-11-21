"""Script entry-point layout and side-effect-free pipeline regressions."""

import ast
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest


PROJECT_DIR = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_DIR / "web" / "backend"
SCRIPTS_DIR = BACKEND_DIR / "scripts"
SCRIPT_PATHS = (
    "data_ingestion/meta_info.py",
    "data_ingestion/update_instrument_classification.py",
    "data_ingestion/data_from_tdata_1day.py",
    "data_ingestion/data_from_tushare_old.py",
    "aggregation/from_1day_to_1week.py",
    "aggregation/from_1day_to_1month.py",
    "aggregation/from_1day_to_1quarter.py",
    "aggregation/from_1day_to_1year.py",
    "cache/dump_stock_caches.py",
    "state/update_cl_state.py",
    "validation/check_xianduan_invariants.py",
    "validation/snapshot_structures.py",
    "validation/compare_structures.py",
    "maintenance/cleanup_stale_data.py",
    "maintenance/_mkdir.py",
    "maintenance/stop_project.py",
    "pipelines/run_update_pipeline.sh",
)
AGGREGATION_PATHS = {name for name in SCRIPT_PATHS if name.startswith("aggregation/")}


@pytest.mark.parametrize("relative", SCRIPT_PATHS)
def test_script_has_one_categorized_entry_point(relative):
    assert (SCRIPTS_DIR / relative).is_file()
    assert not (SCRIPTS_DIR / Path(relative).name).exists()


@pytest.mark.parametrize("relative", (
    "data_ingestion/meta_info.py",
    "cache/dump_stock_caches.py",
    "state/update_cl_state.py",
    "validation/check_xianduan_invariants.py",
    "validation/snapshot_structures.py",
))
def test_backend_directory_is_preserved_after_move(relative):
    script = SCRIPTS_DIR / relative
    tree = ast.parse(script.read_text(encoding="utf-8"))
    assignment = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "BACKEND_DIR" for target in node.targets)
    )
    resolved = eval(compile(ast.Expression(assignment.value), str(script), "eval"), {
        "Path": Path, "__file__": str(script),
    })
    assert resolved == BACKEND_DIR


def test_stop_script_still_targets_this_project():
    module = runpy.run_path(str(SCRIPTS_DIR / "maintenance/stop_project.py"))
    assert module["PROJECT_ROOT"] == PROJECT_DIR


@pytest.mark.parametrize("relative", (
    "data_ingestion/data_from_tushare_old.py",
    "data_ingestion/update_instrument_classification.py",
    "cache/dump_stock_caches.py",
    "state/update_cl_state.py",
    "validation/check_xianduan_invariants.py",
    "validation/snapshot_structures.py",
    "validation/compare_structures.py",
    "maintenance/cleanup_stale_data.py",
    "maintenance/stop_project.py",
))
def test_safe_cli_help_from_another_working_directory(relative, tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_DIR.parent)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["LOG_FILE"] = str(tmp_path / "app.log")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / relative), "--help"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()


@pytest.mark.parametrize("failure", (
    "", "data_ingestion/meta_info.py", "maintenance/cleanup_stale_data.py", "data_ingestion/update_instrument_classification.py",
    "data_ingestion/data_from_tdata_1day.py",
    "aggregation/from_1day_to_1quarter.py", "cache/dump_stock_caches.py", "state/update_cl_state.py",
))
@pytest.mark.parametrize("classification_override", (False, True))
def test_pipeline_order_and_failure_short_circuit(tmp_path, failure, classification_override):
    log = tmp_path / "calls.jsonl"
    workspace = tmp_path / "isolated-workspace"
    fixture_scripts = workspace / "CLPainter/web/backend/scripts"
    for relative in SCRIPT_PATHS:
        target = fixture_scripts / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# isolated pipeline fixture\n", encoding="utf-8")
    fixture_pipeline = fixture_scripts / "pipelines/run_update_pipeline.sh"
    fixture_pipeline.write_text((SCRIPTS_DIR / "pipelines/run_update_pipeline.sh").read_text(encoding="utf-8"), encoding="utf-8")
    interpreter = tmp_path / "fake-python"
    interpreter.write_text(
        "#!" + sys.executable + "\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "script = Path(sys.argv[1])\n"
        "assert script.is_file(), script\n"
        "relative = str(script.relative_to(Path(os.environ['TEST_SCRIPTS_DIR'])))\n"
        "record = {'interpreter': sys.argv[0], 'script': relative, 'cwd': os.getcwd(), 'pythonpath': os.environ.get('PYTHONPATH', ''), 'args': sys.argv[2:], 'pipeline_start': os.environ.get('CLPAINTER_PIPELINE_STARTED_AT'), 'metadata_report': os.environ.get('CLPAINTER_METADATA_REPORT') }\n"
        "with Path(os.environ['TEST_CALL_LOG']).open('a') as output:\n"
        "    output.write(json.dumps(record) + '\\n')\n"
        "sys.exit(7 if relative == os.environ.get('TEST_FAIL_SCRIPT') else 0)\n",
        encoding="utf-8",
    )
    interpreter.chmod(0o755)
    env = os.environ.copy()
    env.update(PYTHON_BIN=str(interpreter), PYTHONPATH="/preserved-search-path",
               TEST_SCRIPTS_DIR=str(fixture_scripts), TEST_CALL_LOG=str(log), TEST_FAIL_SCRIPT=failure)
    alternate = tmp_path / "classification-python"
    alternate.write_text(interpreter.read_text(encoding="utf-8"), encoding="utf-8")
    alternate.chmod(0o755)
    env.pop("CLPAINTER_METADATA_REPORT", None)
    env["TMPDIR"] = str(tmp_path)
    env.pop("CLPAINTER_CLASSIFICATION_PYTHON", None)
    if classification_override:
        env["CLPAINTER_CLASSIFICATION_PYTHON"] = str(alternate)
    result = subprocess.run(
        ["bash", str(fixture_pipeline)], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert log.exists(), result.stderr
    records = [json.loads(line) for line in log.read_text().splitlines()]
    calls = [record["script"] for record in records]
    assert calls[0] == "data_ingestion/meta_info.py"
    from datetime import datetime
    assert datetime.fromisoformat(records[0]["pipeline_start"]).tzinfo is not None
    assert all(record["pipeline_start"] == records[0]["pipeline_start"] for record in records)
    for record in records:
        is_classification = record["script"] == "data_ingestion/update_instrument_classification.py"
        expected_interpreter = alternate if classification_override and is_classification else interpreter
        assert record["interpreter"] == str(expected_interpreter)
        assert record["cwd"] == str(workspace)
        assert record["pythonpath"].split(os.pathsep)[0] == str(workspace)
        assert "/preserved-search-path" in record["pythonpath"].split(os.pathsep)
    prefix = ["data_ingestion/meta_info.py", "maintenance/cleanup_stale_data.py",
              "data_ingestion/update_instrument_classification.py", "data_ingestion/data_from_tdata_1day.py"]
    if failure in prefix:
        assert calls == prefix[:prefix.index(failure) + 1]
    else:
        assert calls[:4] == prefix
        assert set(calls[4:8]) == AGGREGATION_PATHS
        if failure.startswith("aggregation/"):
            assert len(calls) == 8
        elif failure == "cache/dump_stock_caches.py":
            assert calls[8:] == [failure]
        else:
            assert calls[8:] == ["cache/dump_stock_caches.py", "state/update_cl_state.py"]
    assert all(record["metadata_report"] for record in records)
    assert len({record["metadata_report"] for record in records}) == 1
    assert not Path(records[0]["metadata_report"]).parent.exists()
    for record in records:
        if record["script"] == "maintenance/cleanup_stale_data.py":
            assert record["args"] == ["--apply"]
    if calls[-1] == "state/update_cl_state.py":
        assert records[-1]["args"] == ["--archive-screener"]
    assert (result.returncode == 0) == (not failure), result.stderr
