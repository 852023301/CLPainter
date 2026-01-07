#!/bin/bash -i
set -e
# 下载mambaforge https://github.com/conda-forge/miniforge/releases/download/23.1.0-3/Mambaforge-23.1.0-3-Linux-x86_64.sh
# 安装环境相关的命令都写在这个文件中
#环境相关都用conda命令,安装才用mamba

/bin/bash "$INSTALL_EXE" -b -p "$INSTALL_PATH"
source "$INSTALL_PATH"/etc/profile.d/conda.sh  && conda init
conda config --set remote_connect_timeout_secs 600
conda config --set remote_read_timeout_secs 600
conda activate base && mamba create -n "$CONDA_ENV_NAME" python="$UPDATE_ENV_PYTHON_VERSION" conda gcc_linux-64  gxx_linux-64 libstdcxx-ng  gcc==11.2.0 gxx==11.2.0 --file /root/requirements_conda.txt  -c conda-forge -c numba -y
echo "conda activate $CONDA_ENV_NAME"  >> /root/.bashrc
conda activate "$CONDA_ENV_NAME" && pip install --no-cache-dir -i https://nexus.techfin.ai/repository/techfin-pypi/simple --extra-index-url=https://pypi.tuna.tsinghua.edu.cn/simple -r /root/requirements_pip.txt