#!/bin/bash
set -x

CURRENT_DIR=$(readlink -f "$(dirname $0)")
path=$(dirname $CURRENT_DIR)

cp $path/systemd/*.service /lib/systemd/system/

mkdir -p /home/galeraha/
mkdir -p /home/galeraha/script
cp $path/*.py /home/galeraha/
cp $path/script/start.sh /home/galeraha/script/
cp $path/script/stop.sh /home/galeraha/script/

#安装依赖包
PY_VERSION=`python -V 2>&1|awk '{print $2}'|awk -F '.' '{print $1}'`

if (( $PY_VERSION == 3 ))
then
    pip install $path/RPM/PyMySQL-1.0.2-py3-none-any.whl
elif (( $PY_VERSION == 2 ))
then
    rpm -ivh $path/RPM/mariadb-devel-10.1.20-1.el7.x86_64.rpm
    pip install $path/RPM/MySQL-python-1.2.5.zip
fi

systemctl daemon-reload
systemctl enable socket-server.service
systemctl start socket-server.service
systemctl enable mariadb-check.service
systemctl start mariadb-check.service
systemctl status socket-server.service
systemctl status mariadb-check.service
