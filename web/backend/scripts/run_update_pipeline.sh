#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

run_script() {
    local script_name="$1"

    echo "[start] ${script_name}"
    "${PYTHON_BIN}" "${SCRIPT_DIR}/${script_name}"
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

run_script "data_from_tdata_1day.py"

if ! run_parallel_scripts \
    "from_1day_to_1week.py" \
    "from_1day_to_1month.py" \
    "from_1day_to_1quarter.py" \
    "from_1day_to_1year.py"; then
    echo "Parallel aggregation failed; skipping cache dump." >&2
    exit 1
fi

run_script "dump_stock_caches.py"
