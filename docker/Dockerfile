FROM harbor.techfin.ai/library/ubuntu:20.04-ssh

USER root

# 剔除无用的源
RUN echo > /etc/apt/sources.list.d/docker.list
RUN echo > /etc/apt/sources.list.d/mariadb.list
RUN echo > /etc/apt/sources.list.d/mssql-release.list
RUN echo > /etc/apt/sources.list.d/pgdg.list

RUN  apt-get update \
&& apt-get install -y --allow-unauthenticated gnupg ca-certificates curl tar

# 密钥管理
RUN mkdir  -p /usr/share/keyrings
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
RUN curl -o  $INSTALL_EXE  $DUFS_URL/pkg/$INSTALL_EXE
RUN chmod 777 $INSTALL_EXE  && /bin/bash envinstall.sh


RUN  mkdir -p /run/sshd && chmod 0755 /run/sshd   && chown root:root /run/sshd \
&&sed -i 's/^#\s*PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/ssh_config  \
&&sed -i 's/^#\s*PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config \
&&sed -i 's/^#\s*PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config

RUN ln -snf $INSTALL_PATH/envs/$CONDA_ENV_NAME/lib/libstdc++.so.6 /usr/lib/x86_64-linux-gnu/libstdc++.so.6


ENV PYTHONPATH="${PYTHONPATH}:${ROOT_DIR}"
RUN mkdir -p $LOG_DIR

COPY ..  $PRJ_DIR
RUN pip_loc=$(pip show pip | grep Location | awk '{print $2}');echo $ROOT_DIR >>  $pip_loc/project_path.pth
RUN chmod +x $PRJ_DIR/web/backend/run.sh
#CMD ["/root/CLPainter/web/backend/run.sh"]
#CMD ["sh", "-c", "tail -f /dev/null"]