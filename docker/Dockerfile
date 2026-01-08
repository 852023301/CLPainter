FROM harbor.techfin.ai/library/python:3.10

USER root


ENV INSTALL_EXE="Miniforge3-25.3.1-0-Linux-x86_64.sh"
ENV INSTALL_PATH="/root/mambaforge"
ENV CONDA_ENV_NAME="echarts"
ENV UPDATE_ENV_PYTHON_VERSION="3.12"




# 剔除无用的源
RUN echo > /etc/apt/sources.list.d/docker.list
RUN echo > /etc/apt/sources.list.d/mariadb.list
RUN echo > /etc/apt/sources.list.d/mssql-release.list
RUN echo > /etc/apt/sources.list.d/pgdg.list

# 使用阿里云源
# 设置时区
RUN ln -fs /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    apt-get install -y tzdata && \
    dpkg-reconfigure tzdata

# 密钥管理
RUN mkdir -m 0755 -p /usr/share/keyrings
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | \
    gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# 配置源
RUN apt-get update &&  apt-get install -y lsb-release
RUN echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
    https://download.docker.com/linux/debian $(lsb_release -cs) stable" \
    | tee /etc/apt/sources.list.d/docker.list \
&& apt-get install -y --allow-unauthenticated ceph-common openssh-server rsync git gcc g++  openssl libssl-dev iputils-ping vim

RUN  /bin/cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && echo 'Asia/Shanghai' >/etc/timezone \
&& echo root:airflow | chpasswd


WORKDIR /root
COPY docker/envinstall.sh   requirements_conda.txt requirements_pip.txt   /root/
RUN curl -o  $INSTALL_EXE  172.17.1.5:5000/pkg/$INSTALL_EXE
RUN chmod 777 $INSTALL_EXE  && /bin/bash envinstall.sh


RUN  mkdir -p /run/sshd && chmod 0755 /run/sshd   && chown root:root /run/sshd \
&& sed -i 's/^#\s*PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/ssh_config &&sed -i 's/^#\s*PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config && /usr/sbin/sshd -f /etc/ssh/sshd_config

RUN ln -snf $INSTALL_PATH/envs/$CONDA_ENV_NAME/lib/libstdc++.so.6 /usr/lib/x86_64-linux-gnu/libstdc++.so.6



ENV prjDir=/root/CLPainter
ENV bkdDir=$prjDir/web/backend
ENV appDir=$prjDir/web/backend/app
# 环境变量配置
ENV FLASK_APP=$prjDir/web/backend/app/main.py
ENV FLASK_ENV=$CONDA_ENV_NAME

ENV PYTHONPATH=$PYTHONPATH:$prjDir
RUN mkdir -p /app/logs
ENV LOG_FILE=/app/logs/app.log

COPY ..  /root/CLPainter
RUN chmod +x $prjDir/web/backend/run.sh
#CMD ["/root/CLPainter/web/backend/run.sh"]
#CMD ["sh", "-c", "tail -f /dev/null"]