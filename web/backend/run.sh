#!/bin/sh
set -e
. "$INSTALL_PATH"/etc/profile.d/conda.sh
conda activate "$CONDA_ENV_NAME"


export APP_MODULE=${APP_MODULE-app.main:app}
# HOST有重名,不能用这个变量了
#export HOST=${HOST:-0.0.0.0}
#export PORT=${PORT:-8001}



cd $bkdDir
#echo $(pwd)
# run gunicorn
exec gunicorn -w 1 --bind 0.0.0.0:8001 "$APP_MODULE"  --log-level debug --access-logfile - --error-logfile /app/logs/error.log  -k uvicorn.workers.UvicornWorker