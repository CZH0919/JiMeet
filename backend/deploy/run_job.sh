#!/bin/sh
# 供单台调度主机调用。同类任务互斥，失败写入系统告警并返回原退出码。
set -eu
umask 077
job=${1:?需要指定任务}
case "$job" in
    run_sync_recruitments|run_purge_applications|run_purge_chat_messages|check_registration_mail|backup) ;;
    *) echo "未知任务" >&2; exit 2 ;;
esac
. "${JIMEET_OPS_ENV:-/etc/jimeet/ops.env}"
exec 9>"${JIMEET_LOCK_DIR:?}/$job.lock"
if flock -n -E 75 9; then
    :
else
    code=$?
    [ "$code" -eq 75 ] && exit 0
    exit "$code"
fi

run_job() {
    if [ "$job" = backup ]; then
        export PGHOST PGPORT PGUSER PGDATABASE PGPASSFILE
        python3 "$(dirname "$0")/db_backup.py" backup --directory "${JIMEET_BACKUP_DIR:?}"
    else
        docker exec "${JIMEET_CONTAINER:-jimeet-api}" python manage.py "$job"
    fi
}
if run_job; then
    exit 0
else
    code=$?
fi
logger -p daemon.err -t jimeet-ops -- "job=$job exit=$code" || :
if [ -n "${JIMEET_ALERT_CURL_CONFIG:-}" ]; then
    curl --disable --config "$JIMEET_ALERT_CURL_CONFIG" --proto '=https' --max-time 10 --silent --fail \
        --header 'Content-Type: application/json' --data "{\"service\":\"jimeet\",\"job\":\"$job\",\"exit\":$code}" \
        --output /dev/null || logger -p daemon.err -t jimeet-ops -- "alert_delivery_failed job=$job"
fi
exit "$code"
