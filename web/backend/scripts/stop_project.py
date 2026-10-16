#!/usr/bin/env python3
"""Stop CLPainter processes started from this project."""

import argparse
import os
import signal
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
WAIT_SECONDS = 5


def read_command_line(pid: int) -> list[str]:
    try:
        raw_command_line = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return []
    return [part.decode(errors="replace") for part in raw_command_line.split(b"\0") if part]


def read_process_path(pid: int, name: str) -> Path | None:
    try:
        return (Path(f"/proc/{pid}") / name).resolve(strict=True)
    except (FileNotFoundError, PermissionError, ProcessLookupError, RuntimeError):
        return None


def is_python_process(command_line: list[str]) -> bool:
    if not command_line:
        return False
    executable = Path(command_line[0]).name
    return executable in {"python", "python3", "python3.10", "python3.11", "python3.12"}


def is_project_process(pid: int, current_pid: int) -> bool:
    if pid == current_pid or pid == 1:
        return False

    command_line = read_command_line(pid)
    if not command_line:
        return False

    command_text = " ".join(command_line)
    working_directory = read_process_path(pid, "cwd")
    executable = read_process_path(pid, "exe")
    script_paths = [argument for argument in command_line if argument.endswith((".py", ".sh"))]

    belongs_to_project = any(
        path is not None and (path == PROJECT_ROOT or PROJECT_ROOT in path.parents)
        for path in (working_directory, executable, *(Path(item) for item in script_paths if Path(item).is_absolute()))
    )
    if not belongs_to_project:
        return False

    is_backend = "app.main:app" in command_text or "gunicorn" in command_text
    is_script = any(
        path is not None and PROJECT_ROOT in path.parents
        for path in (Path(item) for item in script_paths if Path(item).is_absolute())
    )
    return (is_backend and is_python_process(command_line)) or is_script


def find_project_processes() -> list[int]:
    current_pid = os.getpid()
    pids = []
    for proc_entry in Path("/proc").iterdir():
        if not proc_entry.name.isdigit():
            continue
        pid = int(proc_entry.name)
        if is_project_process(pid, current_pid):
            pids.append(pid)
    return sorted(pids)


def signal_processes(pids: list[int], signal_number: int) -> list[int]:
    survivors = []
    for pid in pids:
        try:
            os.kill(pid, signal_number)
        except ProcessLookupError:
            continue
        except PermissionError as error:
            print(f"[warn] 无权限停止进程 {pid}: {error}", flush=True)
            survivors.append(pid)
        else:
            print(f"[signal] pid={pid} signal={signal.Signals(signal_number).name}", flush=True)
            survivors.append(pid)
    return survivors


def wait_for_exit(pids: list[int]) -> list[int]:
    deadline = time.monotonic() + WAIT_SECONDS
    survivors = set(pids)
    while survivors and time.monotonic() < deadline:
        survivors = {pid for pid in survivors if Path(f"/proc/{pid}").exists()}
        if survivors:
            time.sleep(0.2)
    return sorted(survivors)


def main() -> int:
    parser = argparse.ArgumentParser(description="停止 CLPainter 后端和数据更新进程")
    parser.add_argument("--list-only", action="store_true", help="仅列出将被停止的进程")
    args = parser.parse_args()

    pids = find_project_processes()
    if not pids:
        print("没有找到 CLPainter 相关进程")
        return 0

    print("匹配到的进程:", ", ".join(map(str, pids)), flush=True)
    if args.list_only:
        return 0

    survivors = wait_for_exit(signal_processes(pids, signal.SIGTERM))
    if survivors:
        print(f"优雅停止超时，强制结束: {', '.join(map(str, survivors))}", flush=True)
        survivors = wait_for_exit(signal_processes(survivors, signal.SIGKILL))

    if survivors:
        print(f"仍未能停止的进程: {', '.join(map(str, survivors))}", flush=True)
        return 1

    print("CLPainter 相关进程已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
