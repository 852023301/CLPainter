#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
# 容器内全部步骤共用 echarts。显式 PYTHON_BIN 仍可覆盖，便于测试。
if [[ -z "${PYTHON_BIN:-}" && -x /root/mambaforge/envs/echarts/bin/python ]]; then
    PYTHON_BIN="/root/mambaforge/envs/echarts/bin/python"
else
    PYTHON_BIN="${PYTHON_BIN:-python3}"
fi
export CLPAINTER_PIPELINE_STARTED_AT="$(date -u +'%Y-%m-%dT%H:%M:%S+00:00')"

run_script() {
    local script_name="$1"
    shift

    echo "[start] ${script_name}"
    "${PYTHON_BIN}" "${SCRIPT_DIR}/${script_name}" "$@"
    echo "[done] ${script_name}"
}

run_parallel_scripts() {
    local script_names=("$@")
    local pids=()
    local script_name pid status index

    status=0
    for script_name in "${script_names[@]}"; do
        echo "[start] ${script_name}"
        "${PYTHON_BIN}" "${SCRIPT_DIR}/${script_name}" &
        pids+=("$!")
    done

    for index in "${!script_names[@]}"; do
        if wait "${pids[${index}]}"; then
            echo "[done] ${script_names[${index}]}"
        else
            status=1
            echo "[failed] ${script_names[${index}]}" >&2
        fi
    done

    return "${status}"
}

cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

run_script "data_ingestion/meta_info.py"
run_script "maintenance/cleanup_stale_data.py" --apply
run_script "data_ingestion/update_instrument_classification.py"
run_script "data_ingestion/data_from_tdata_1day.py"

if ! run_parallel_scripts \
    "aggregation/from_1day_to_1week.py" \
    "aggregation/from_1day_to_1month.py" \
    "aggregation/from_1day_to_1quarter.py" \
    "aggregation/from_1day_to_1year.py"; then
    echo "Parallel aggregation failed; skipping cache dump." >&2
    exit 1
fi

run_script "cache/dump_stock_caches.py"
run_script "state/update_cl_state.py" --archive-screener
