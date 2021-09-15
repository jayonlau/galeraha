#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import time
import traceback
import logging
import sys
import json
import galera_util
import socket
from logging.handlers import RotatingFileHandler

# 定义一些初始变量
galera_conf = "/etc/kolla/mariadb/galera.cnf"

# 初始化日志对象
logger = logging.getLogger("check-or-recover-galera")
log_file='/home/galeraha/check-or-recover-galera.log'
if not os.path.exists(log_file):
    os.system('mkdir -p /home/galeraha/')
    os.system('touch ' + log_file)

formatter = logging.Formatter('%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s')
file_handler = RotatingFileHandler(log_file, maxBytes=100 * 1024 * 1024, backupCount=3)
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.setLevel(logging.DEBUG)

PORT = 10000
BUFF_SIZE = 10240

def test_connect_ok(ip):
    client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_sock.settimeout(3)
#    logger.info('connect to service by %s:%s'%(ip,PORT))
    client_sock.connect((ip, PORT))
    client_sock.close()

# 这个方法要求在要远程的节点上需要有个进程在监听PORT端口等待处理命令
def send_request(ip, data, timeout=120):
    #test_connect_ok(ip)
    client_sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    client_sock.settimeout(timeout)
    client_sock.connect((ip, PORT))
    client_sock.send(data.encode())
    ret_data = client_sock.recv(BUFF_SIZE) #type of ret_data is bytes
    ret_data = ret_data.decode() #convert bytes to str
    #logger.info("type of ret_data is %s and content is %s"%(type(ret_data),ret_data))
    client_sock.close()
    return ret_data

def remote_send_request(ip, data, timeout=120):
    res_remote = send_request(ip, json.dumps(data), timeout=timeout)
    if res_remote is None or res_remote == '':
        raise Exception('res_remote is null')
    res_remote = json.loads(res_remote)
    return res_remote

# 获取当前galera的集群的各节点的ip
def get_cluster_ip():
    node_ips_info = os.popen("cat /etc/kolla/mariadb/galera.cnf |grep '^wsrep_cluster_address'").read()
    node_ips_str = node_ips_info.split('gcomm://')[1]
    node_ips_str = node_ips_str.strip()
    node_ips_arr = node_ips_str.split(',')
    node_ips = []
    for node_ip in node_ips_arr:
        node_ips.append(node_ip.split(':')[0])
    return node_ips

# 获取本机ip信息
def get_local_ip():
    cmd_out = os.popen('cat ' + galera_conf +' | grep wsrep_node_address | awk {\'print $3\'} 2>/dev/null').read()
    ip = cmd_out.split(":")[0]
    return ip

# 获取各节点的seqno值
def get_first_node_by_grastate(node_ips_arr):
    seqno_dict = {}
    data = {"req_type": "get_seqno"}
    for node_ip in node_ips_arr:
        try:
            res_remote = remote_send_request(node_ip, data)
            seqno_dict[node_ip] = res_remote["seqno"]
        except Exception as e:
            seqno_dict[node_ip] = -1
            logger.error(traceback.format_exc())
    #获取最大seqno的主机节点
    max_seqno = -1
    first_boot_node = None
    for node_ip in node_ips_arr:
        seqno = int(seqno_dict[node_ip])
        logger.info('node %s with seqno is %s'%(node_ip, seqno))
        if seqno > max_seqno:
            max_seqno = seqno
            first_boot_node = node_ip
    return first_boot_node

# 通过mysqld_safe --wsrep-recover来获取seqno，并比对集群内节点的seqno，以此确定谁是first boot node
def get_first_node_by_recover(node_ips_arr):
    seqno_dict = {}
    data = {"req_type": "get_seqno_by_wsrep_recover"}
    #获取所有节点的seqno
    for node_ip in node_ips_arr:
        try:
            res_remote = remote_send_request(node_ip, data)
            seqno_dict[node_ip] = res_remote["seqno"]
        except Exception as e:
            seqno_dict[node_ip] = -1
            logger.error(traceback.format_exc())
    #获取最大seqno的主机节点
    max_seqno = -1
    first_boot_node = None
    for node_ip in node_ips_arr:
        seqno = int(seqno_dict[node_ip])
        logger.info('node %s with seqno is %s'%(node_ip, seqno))
        if seqno > max_seqno:
            max_seqno = seqno
            first_boot_node = node_ip
    return first_boot_node

# 获取各节点的gvwstate.dat文件的my_uuid和view_id的比对值结果
def get_all_nodes_uv_is_equal(node_ips_arr):
    uv_equal_dict = {}
    data = {"req_type": "get_uv_equal_value"}
    for node_ip in node_ips_arr:
        try:
            res_remote = remote_send_request(node_ip, data)
            uv_equal_dict[node_ip] = res_remote["equal"]
        except Exception as e:
            uv_equal_dict[node_ip] = 0
            logger.error(traceback.format_exc())
    return uv_equal_dict


# 检查自身mariadb服务是否已经启动
def check_is_active_now():
    is_active = os.popen('ps -ef | grep \'/var/log/kolla/mariadb/mariadb.log\' | grep -v grep | awk {\'print $2\'} 2>/dev/null').read()
    is_active = is_active.strip()
    if is_active:
        logger.info('the mariadb is already up')
        return True
    return False

# 第一个启动的节点
def start_mariadb_with_wsrep():
    os.system("sed -i 's/--wsrep-new-cluster//' /etc/kolla/mariadb/config.json")
    os.system("sed -i 's/mysqld_safe/mysqld_safe --wsrep-new-cluster/' /etc/kolla/mariadb/config.json")
    os.system("sed -i 's/safe_to_bootstrap:.*/safe_to_bootstrap: 1/' /var/lib/docker/volumes/mariadb/_data/grastate.dat")
    #os.system("cat /etc/kolla/mariadb/config.json")
    logger.info("start mariadb with wsrep-new-cluster, wait about 60 seconds")
    os.system('systemctl daemon-reload')
    os.system('docker restart mariadb')
    time.sleep(60) #启动后，一定要等一会确保提供服务，可以连接后，再进行连接，时间太短会一直重启mariadb容器
    # 将配置文件恢复回去
    os.system("sed -i 's/ --wsrep-new-cluster//' /etc/kolla/mariadb/config.json")
    #os.system("cat /etc/kolla/mariadb/config.json")
    os.system('systemctl daemon-reload')
    if check_is_active_now() is True:
        return True
    else:
        logger.error('use option wsrep-new-cluster start mariadb failed')
    return False


def main():
    first_boot_node = None
    while True:
        try:
            # 获取当前galera的集群的各节点的ip
            node_ips_arr = get_cluster_ip()
            # 确定网络连接情况
            rep = 0
            for node_ip in node_ips_arr:
                rep = os.system('ping ' + node_ip + ' -c 5 2>/dev/null')
                if rep != 0:
                    logger.info('mariadb node %s network is not ready, wait a moment'%node_ip)
                    break
            if rep != 0:
                continue
            logger.info('all cluster node network is ready')

            # 先检测自己的mariadb是否已经自己启动
            if check_is_active_now():
                if galera_util.test_galera_connection():
                    time.sleep(10) #正常情况下，不要太快输出日志
                    logger.info('this mariadb node is running')
                    collect_data = galera_util.get_important_value()
                    logger.info('the important value of this mariadb node is %s at this moment'%collect_data)
                    continue
                else:
                    logger.info('this mariadb node is running process, but cannot be connected, there is some problem at this moment')
            else:
                logger.info('this mariadb is not running process')

            # 检测其它节点是否已经有在运行着的
            data = {"req_type": "check_mariadb_service"}
            has_mariadb_service_on = False
            for node_ip in node_ips_arr:
                try:
                    logger.info('start to check if mariadb node %s can be connected '%node_ip)
                    res_remote = remote_send_request(node_ip, data)
                    state = res_remote["state"]
                    logger.info('the result of mariadb node %s state is %s'%(node_ip, state))
                    if state == 'active':
                        has_mariadb_service_on = True
                        # 找到在运行着的可以连接的节点
                        logger.info('find the running mariadb service node:' + node_ip)
                        # 直接启动自己服务
                        os.system('docker restart mariadb')
                        time.sleep(10)
                        if check_is_active_now() is True:
                            if galera_util.test_galera_connection():
                                time.sleep(5)
                                logger.info('this mariadb node is running')
                                collect_data = galera_util.get_important_value()
                                logger.info('the important value of this mariadb node is %s at this moment'%collect_data)
                            else:
                                logger.info('through there is a mariadb process, it cannot be connected this moment, maybe need manual check')
                        else:
                            logger.info('the mariadb service process is not running, maybe need manual check')
                        break
                except Exception as e:
                    logger.error(traceback.format_exc())
                    logger.error('check_mariadb_service for ' + node_ip + ' failed, error:' + str(e))
            if has_mariadb_service_on is True:
                continue

            # 如果所有节点的mariadb都没在运行，则需要寻找一个节点进行启动
            # 根据seqno值判断哪个节点为启动节点
            first_boot_node = get_first_node_by_grastate(node_ips_arr)
            if first_boot_node is not None:
                logger.info('find the first_boot_node by max seqno, first_boot_node:' + first_boot_node)
                # 判断这个启动节点是不是自己，如果是就启动，否则等待其它节点启动起来
                if first_boot_node == get_local_ip():
                    if start_mariadb_with_wsrep() is True: #服务进程启动成功
                        if not galera_util.test_galera_connection(): #检查是否可以连接3306端口，如果不能，人工介入
                            logger.info("cannot start first boot node with wsrep-new-cluster, need manual check")
                else:
                    logger.info('wait node ' + first_boot_node + ' start mariadb service')
                    time.sleep(10)
                continue
            else:
                logger.info("all node's seqno is -1, we need view gvwstate.dat to confirm the first boot node")

            # 如果所有节点的seqno都是-1则说明可能是全部主机非正常停止的，比如断电等
            # 这时则通过比对gvwstate.dat文件的my_uuid和view_id是否相等来决定从这个节点启动
            # 当集群时干净状态停止的时候该文件是被删除的
            uv_equal_dict = get_all_nodes_uv_is_equal(node_ips_arr)
            # 根据返回的值判断哪个是启动节点，1表示是，0表示否
            for key in uv_equal_dict:
                if uv_equal_dict[key] == 1:
                    first_boot_node = key
                    logger.info('find the first_boot_node by uv_equal_dict, first_boot_node:' + first_boot_node)
                    break
            if first_boot_node is not None:
                # 判断这个启动节点是不是自己，如果是就启动，否则等待其它节点启动起来
                if first_boot_node == get_local_ip():
                    if start_mariadb_with_wsrep() is True:
                        if not galera_util.test_galera_connection(): #检查是否可以连接3306端口，如果不能，人工介入
                            logger.info("cannot start first boot node with wsrep-new-cluster, need manual check")
                    else:
                        logger.info('wait node ' + first_boot_node + ' start mariadb service')
                        time.sleep(10)
                continue
            else:
                logger.info("can not find first_boot_node by gvwstate.dat file, need manual check")

            # 通过wsrep-recover方式查找定位first boot node
            first_boot_node = get_first_node_by_recover(node_ips_arr)
            if first_boot_node is not None:
                logger.info('find the first_boot_node by wsrep recover seqno, first_boot_node:' + first_boot_node)
                # 判断这个启动节点是不是自己，如果是就启动，否则等待其它节点启动起来
                if first_boot_node == get_local_ip():
                    if start_mariadb_with_wsrep() is True:
                        if not galera_util.test_galera_connection(): #检查是否可以连接3306端口，如果不能，人工介入
                            logger.info("cannot start first boot node with wsrep-new-cluster, need manual check")
                    else:
                        logger.info('wait node ' + first_boot_node + ' start mariadb service')
                        time.sleep(10)
                continue
            else:
                logger.info("can not find first_boot_node by gvwstate.dat file, need manual check")

            # 如果经过上述步骤依然找不到启动节点，需要人工进行干预了，或者可以随机挑选个节点进行启动
            logger.error('can not find first_boot_node, maybe you should ask admin to manual deal with this problem')
            time.sleep(5)
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error('error:' + str(e))

if __name__ == "__main__":
    sys.exit(main())
