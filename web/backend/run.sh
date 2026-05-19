#!/bin/sh
set -e
. "$INSTALL_PATH"/etc/profile.d/conda.sh
conda activate "$CONDA_ENV_NAME"

# 导出环境变量，供 python-dotenv 或 os.environ 使用
export APP_MODULE=${APP_MODULE-app.main:app}
#export LHOST=${LHOST:-0.0.0.0}
#export PORT=${PORT:-8001}
#export WORKERS=${WORKERS:-1}
#export LOG_DIR=${LOG_DIR:-debug}
#export LOG_LEVEL=${LOG_LEVEL:-debug}

# 确保日志目录存在
mkdir -p $LOG_DIR

cd $BKD_DIR
# run gunicorn
exec gunicorn -w $WORKERS --bind $LHOST:$PORT "$APP_MODULE" \
  --log-level $LOG_LEVEL \
  --access-logfile - \
  --error-logfile $LOG_ERROR_FILE \
  -k uvicorn.workers.UvicornWorker