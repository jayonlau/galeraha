#!/bin/bash
set -x
systemctl stop socket-server.service
systemctl stop mariadb-check.service
systemctl disable socket-server.service
systemctl disable mariadb-check.service
rm -rf /home/galera
