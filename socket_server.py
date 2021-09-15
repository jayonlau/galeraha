#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import socket
import sys
import logging
import json
import galera_util

if(sys.version[:1] == "3"):
    import _thread as thread
else:
    import thread

# 初始化日志对象
logger = logging.getLogger("check-or-recover-galera")
log_file='/home/galeraha/check-or-recover-galera.log'
if not os.path.exists(log_file):
    os.system('mkdir -p /home/galeraha/')
    os.system('touch ' + log_file)

formatter = logging.Formatter('%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s')
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.setLevel(logging.DEBUG)

HOST = ''
PORT = 10000

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.bind((HOST, PORT))
except socket.error as msg:
    logger.info('Bind failed. Error Code : ' + str(msg[0]) + ' Message ' + msg[1])
    sys.exit()
s.listen(10)

# 检查自身mariadb服务是否已经启动
def check_is_active_now():
    is_active = os.popen('ps -ef | grep \'/var/log/kolla/mariadb/mariadb.log\' | grep -v grep | awk {\'print $2\'} 2>/dev/null').read()
    is_active = is_active.strip()
    if is_active:
        logger.info('the mariadb is already up')
        return True
    return False

# 通过启动mysqld_safe --wsrep-recovery方式获取各个mariadb实例的seqno
def get_local_seqno():
    os.system("sed -i 's/--wsrep-recover//' /etc/kolla/mariadb/config.json")
    os.system("sed -i 's/mysqld_safe/mysqld_safe --wsrep-recover/' /etc/kolla/mariadb/config.json")
    logger.info("start mariadb with wsrep-recover, then get seqno from log")
    os.system('systemctl daemon-reload')
    os.system('docker restart mariadb')
    # 将配置文件恢复回去
    os.system("sed -i 's/ --wsrep-recover//' /etc/kolla/mariadb/config.json")
    os.system('systemctl daemon-reload')
    logfile = "/var/lib/docker/volumes/kolla_logs/_data/mariadb/mariadb.log"
    seqno = None
    with open(logfile, 'r') as raw:
        for item in raw:
            #if "Setting initial position" in item:
            if "WSREP: Recovered position" in item:
                line = item.strip().split()
                #print(line)
                seqno = line[-1].split(':')[-1]
    if seqno is None:
        logger.info("seqno is none, wsrep position could not be found")
    logger.info("seqno is %s" %(seqno, ))
    return seqno


def clientthread(conn):
    #infinite loop so that function do not terminate and thread do not end.
    while True:

        #Receiving from client
        data = conn.recv(1024)
        req_type = None;
        if data != '':
            data = data.decode()
            data = json.loads(data)
            req_type = data["req_type"]
        if req_type and req_type == 'get_seqno':
            res = {}
            grastate = os.popen("cat /var/lib/docker/volumes/mariadb/_data/grastate.dat | grep seqno").read()
            if grastate and grastate != '':
                seqno_arr = grastate.split(':')
                res[seqno_arr[0]] = seqno_arr[1].strip().replace('\n', '')
                res["ret_state"] = "success"
            else:
                res["ret_state"] = "failed"
            res = json.dumps(res)
            conn.sendall(res.encode())
        if req_type and req_type == 'get_uv_equal_value':
            res = {}
            gvw_file = "/var/lib/docker/volumes/mariadb/_data/gvwstate.dat"
            #当关闭docker容器时，这个文件会消失，所以当文件不存在时，直接返回，关闭连接
            if not os.path.exists(gvw_file):
                res["equal"] = 0
                res["ret_state"] = "success"
                res = json.dumps(res)
                conn.sendall(res.encode())
                conn.close()
                return
            gvwstate = os.popen("cat /var/lib/docker/volumes/mariadb/_data/gvwstate.dat | grep -v ^#").readlines()
            gvw_dict = {}
            if gvwstate and gvwstate != '':
                for line in gvwstate:
                    content = line.split(':')
                    key = content[0]
                    value = content[1]
                    if key == 'view_id':
                        value = value.split(' ')[2]
                    gvw_dict[key] = value

                my_uuid = gvw_dict["my_uuid"].strip()
                view_id = gvw_dict["view_id"].strip()
                print('my_uuid===%s'%my_uuid)
                print('view_id===%s'%view_id)
                if my_uuid == view_id:
                    res["equal"] = 1
                else:
                    res["equal"] = 0
                res["ret_state"] = "success"
            else:
                res["ret_state"] = "failed"
            res = json.dumps(res)
            conn.sendall(res.encode())
        if req_type and req_type == 'check_mariadb_service':
            res = {}
            if check_is_active_now() is True:
                if galera_util.test_galera_connection():
                    res["state"] = "active"
                    res["ret_state"] = "success"
                else:
                    res["state"] = "inactive"
                    res["ret_state"] = "failed"
            else:
                res["state"] = "inactive"
                res["ret_state"] = "failed"
            res = json.dumps(res)
            conn.sendall(res.encode())
        if req_type and req_type == 'get_seqno_by_wsrep_recover':
            res = {}
            seqno = get_local_seqno()
            res["seqno"] = seqno
            res = json.dumps(res)
            conn.sendall(res.encode())

    conn.close()

while 1:
    conn, addr = s.accept()
    logger.info('Connected with ' + addr[0] + ':' + str(addr[1]))
    thread.start_new_thread(clientthread ,(conn,))

s.close()
