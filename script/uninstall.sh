#!/bin/bash
set -x
systemctl stop socket-server.service
systemctl stop mariadb-check.service
systemctl disable socket-server.service
systemctl disable mariadb-check.service
sleep 2
rm -rf /home/galeraha

#安装依赖包
PY_VERSION=`python -V 2>&1|awk '{print $2}'|awk -F '.' '{print $1}'`

if (( $PY_VERSION == 3 ))
then
    pip uninstall PyMySQL-1.0.2-py3-none-any.whl
elif (( $PY_VERSION == 2 ))
then
    rpm -e mariadb-devel-10.1.20-1.el7.x86_64
    pip uninstall MySQL-python-1.2.5.zip
fi
