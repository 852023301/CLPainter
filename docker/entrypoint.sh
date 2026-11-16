#!/bin/bash
set -e

"${PRJ_DIR}/web/backend/run.sh" &
app_pid=$!

/usr/sbin/sshd -f /etc/ssh/sshd_config -D &
sshd_pid=$!

trap 'kill "$app_pid" "$sshd_pid" 2>/dev/null || true' TERM INT
wait -n "$app_pid" "$sshd_pid"
status=$?
kill "$app_pid" "$sshd_pid" 2>/dev/null || true
wait "$app_pid" "$sshd_pid" 2>/dev/null || true
exit "$status"
