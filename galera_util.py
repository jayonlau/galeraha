#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import time
import logging
import sys

if(sys.version[:1] == "3"):
    import pymysql
else:
    import MySQLdb

# 定义一些初始变量
mysql_user = "haproxy"
mysql_pw = ""
galera_conf = "/etc/kolla/mariadb/galera.cnf"

# 初始化日志对象
logger = logging.getLogger("galera-util")
log_file='/home/galeraha/galera-util.log'
if not os.path.exists(log_file):
    os.system('mkdir -p /home/galeraha/')
    os.system('touch ' + log_file)

formatter = logging.Formatter('%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s')
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.setLevel(logging.DEBUG)

def get_local_ip():
    cmd_out = os.popen('cat ' + galera_conf +' | grep wsrep_node_address | awk {\'print $3\'} 2>/dev/null').read()
    ip = cmd_out.split(":")[0]
    return ip


host = get_local_ip()

def test_galera_connection():
    logger.info("check galera connetcion on host %s"%host)
    retry = 0
    while retry < 10:
        try:
            if(sys.version[:1] == "3"):
                conn = pymysql.connect(host=host, port=3306, user=mysql_user, passwd=mysql_pw, db='information_schema')
            else:
                conn = MySQLdb.connect(host=host, port=3306, user=mysql_user, passwd=mysql_pw, db='information_schema')
            print('already connect to mariadb server')
            return True
        except Exception as e:
            print('can not connect to mariadb server')
            time.sleep(5)
            retry = retry + 1
    return False

def get_important_value():

    # Open database connection
    if(sys.version[:1] == "3"):
        conn = pymysql.connect(host=host, port=3306, user=mysql_user, passwd=mysql_pw, db='information_schema')
    else:
        conn = MySQLdb.connect(host=host, port=3306, user=mysql_user, passwd=mysql_pw, db='information_schema')

    # prepare a cursor object using cursor() method
    cursor = conn.cursor()

    # execute SQL query using execute() method.
    # cursor.execute("SELECT VERSION()")
    cursor.execute("show status like '%wsrep%';")

    # Fetch a single row using fetchone() method.
    data = cursor.fetchall()
    # print "Database version : %s " % data
    collect_keys = ['wsrep_cluster_size','wsrep_cluster_status','wsrep_local_state_comment','wsrep_incoming_addresses']
    collect_data = {}
    for i in range(0, cursor.rowcount, 1):
        row_data = data[i]
        key = row_data[0]
        if key in collect_keys:
            collect_data[key] = row_data[1]

    # disconnect from server
    conn.close()
    return collect_data
