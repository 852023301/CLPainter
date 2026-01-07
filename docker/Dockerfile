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
RUN  apt-get update \
&& apt-get install -y --allow-unauthenticated gnupg ca-certificates curl tar  \
&& apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 0E98404D386FA1D9 \
&& apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 6ED0E7B82643E131 \
&& echo deb https://mirrors.aliyun.com/debian/ bookworm main non-free non-free-firmware contrib >> /etc/apt/sources.list \
&& echo deb https://mirrors.aliyun.com/debian-security/ bookworm-security main >> /etc/apt/sources.list \
&& echo deb https://mirrors.aliyun.com/debian/ bookworm-updates main non-free non-free-firmware contrib >> /etc/apt/sources.list \
&& echo deb https://mirrors.aliyun.com/debian/ bookworm-backports main non-free non-free-firmware contrib >> /etc/apt/sources.list \
&& apt-get install -y --allow-unauthenticated iputils-ping vim

RUN  /bin/cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && echo 'Asia/Shanghai' >/etc/timezone \
&& echo root:airflow | chpasswd


WORKDIR /root
COPY docker/envinstall.sh   requirements_conda.txt requirements_pip.txt   /root/
COPY ..  /root/CLPainter
RUN curl -o  $INSTALL_EXE  172.17.1.5:5000/pkg/$INSTALL_EXE
RUN chmod 777 $INSTALL_EXE  && /bin/bash envinstall.sh


RUN ln -snf $INSTALL_PATH/envs/$CONDA_ENV_NAME/lib/libstdc++.so.6 /usr/lib/x86_64-linux-gnu/libstdc++.so.6



ENV prjDir=/root/CLPainter
ENV bkdDir=$prjDir/web/backend
ENV appDir=$prjDir/web/backend/app
# 环境变量配置
ENV FLASK_APP=$prjDir/web/backend/app/main.py
ENV FLASK_ENV=$CONDA_ENV_NAME

ENV PYTHONPATH=$prjDir
RUN mkdir -p /app/logs
ENV LOG_FILE=/app/logs/app.log

RUN chmod +x $prjDir/web/backend/run.sh
RUN apt-get update && apt-get install -y iputils-ping

#CMD ["/root/CLPainter/web/backend/run.sh"]
CMD ["sh", "-c", "tail -f /dev/null"]