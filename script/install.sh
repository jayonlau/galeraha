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

systemctl daemon-reload
systemctl enable socket-server.service
systemctl start socket-server.service
systemctl enable mariadb-check.service
systemctl start mariadb-check.service
systemctl status socket-server.service
systemctl status mariadb-check.service
