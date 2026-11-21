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
    "", "data_ingestion/meta_info.py", "data_ingestion/update_instrument_classification.py",
    "data_ingestion/data_from_tdata_1day.py",
    "aggregation/from_1day_to_1quarter.py", "cache/dump_stock_caches.py", "state/update_cl_state.py",
))
@pytest.mark.parametrize("classification_override", (False, True))
def test_pipeline_order_and_failure_short_circuit(tmp_path, failure, classification_override):
    log = tmp_path / "calls.jsonl"
    interpreter = tmp_path / "fake-python"
    interpreter.write_text(
        "#!" + sys.executable + "\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "script = Path(sys.argv[1])\n"
        "assert script.is_file(), script\n"
        "relative = str(script.relative_to(Path(os.environ['TEST_SCRIPTS_DIR'])))\n"
        "record = {'interpreter': sys.argv[0], 'script': relative, 'cwd': os.getcwd(), 'pythonpath': os.environ.get('PYTHONPATH', '')}\n"
        "with Path(os.environ['TEST_CALL_LOG']).open('a') as output:\n"
        "    output.write(json.dumps(record) + '\\n')\n"
        "sys.exit(7 if relative == os.environ.get('TEST_FAIL_SCRIPT') else 0)\n",
        encoding="utf-8",
    )
    interpreter.chmod(0o755)
    env = os.environ.copy()
    env.update(PYTHON_BIN=str(interpreter), PYTHONPATH="/preserved-search-path",
               TEST_SCRIPTS_DIR=str(SCRIPTS_DIR), TEST_CALL_LOG=str(log), TEST_FAIL_SCRIPT=failure)
    alternate = tmp_path / "classification-python"
    alternate.write_text(interpreter.read_text(encoding="utf-8"), encoding="utf-8")
    alternate.chmod(0o755)
    env.pop("CLPAINTER_CLASSIFICATION_PYTHON", None)
    if classification_override:
        env["CLPAINTER_CLASSIFICATION_PYTHON"] = str(alternate)
    result = subprocess.run(
        ["bash", str(SCRIPTS_DIR / "pipelines/run_update_pipeline.sh")], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert log.exists(), result.stderr
    records = [json.loads(line) for line in log.read_text().splitlines()]
    calls = [record["script"] for record in records]
    assert calls[0] == "data_ingestion/meta_info.py"
    for record in records:
        is_classification = record["script"] == "data_ingestion/update_instrument_classification.py"
        expected_interpreter = alternate if classification_override and is_classification else interpreter
        assert record["interpreter"] == str(expected_interpreter)
        assert record["cwd"] == str(PROJECT_DIR.parent)
        assert record["pythonpath"].split(os.pathsep)[0] == str(PROJECT_DIR.parent)
        assert "/preserved-search-path" in record["pythonpath"].split(os.pathsep)
    if failure == "data_ingestion/meta_info.py":
        assert calls == [failure]
    elif failure == "data_ingestion/update_instrument_classification.py":
        assert calls == ["data_ingestion/meta_info.py", failure]
    elif failure == "data_ingestion/data_from_tdata_1day.py":
        assert calls == ["data_ingestion/meta_info.py", "data_ingestion/update_instrument_classification.py", failure]
    else:
        assert calls[1] == "data_ingestion/update_instrument_classification.py"
        assert calls[2] == "data_ingestion/data_from_tdata_1day.py"
        assert set(calls[3:7]) == AGGREGATION_PATHS
        if failure.startswith("aggregation/"):
            assert len(calls) == 7
        elif failure == "cache/dump_stock_caches.py":
            assert calls[7:] == [failure]
        else:
            assert calls[7:] == ["cache/dump_stock_caches.py", "state/update_cl_state.py"]
    assert (result.returncode == 0) == (not failure), result.stderr
