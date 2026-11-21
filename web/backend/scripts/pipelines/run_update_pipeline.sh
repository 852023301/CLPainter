#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
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

METADATA_CONTEXT_DIR=""
if [[ -z "${CLPAINTER_METADATA_REPORT:-}" ]]; then
    METADATA_CONTEXT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/clpainter-metadata.XXXXXXXX")"
    export CLPAINTER_METADATA_REPORT="${METADATA_CONTEXT_DIR}/metadata.json"
fi
cleanup_metadata_context() {
    local exit_status=$?
    if [[ -n "${METADATA_CONTEXT_DIR}" ]]; then
        rm -f -- "${METADATA_CONTEXT_DIR}/metadata.json" || true
        rmdir -- "${METADATA_CONTEXT_DIR}" 2>/dev/null || true
    fi
    return "${exit_status}"
}
trap cleanup_metadata_context EXIT

run_script "data_ingestion/meta_info.py"
run_script "maintenance/cleanup_stale_data.py" --apply
CLASSIFICATION_PYTHON="${CLPAINTER_CLASSIFICATION_PYTHON:-${PYTHON_BIN}}"
if [[ -z "${CLPAINTER_CLASSIFICATION_PYTHON:-}" && -x "${PROJECT_ROOT}/CLPainter/.venv-classification/bin/python" ]]; then
    CLASSIFICATION_PYTHON="${PROJECT_ROOT}/CLPainter/.venv-classification/bin/python"
fi
PYTHON_BIN="${CLASSIFICATION_PYTHON}" run_script "data_ingestion/update_instrument_classification.py"
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
