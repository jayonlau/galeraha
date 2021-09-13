this program was needed by package as fllows, so you must install them
yum remove -y mariadb-libs mariadb-common mariadb-config
yum install -y mariadb-devel
#yum install -y mariadb-common
yum install -y mariadb-libs
yum install -y crypto-utils
yum install -y openssl-devel

pip install MySQL-python

there still have to implement some feathur like this
1. there need a conf file to make program flexble
2. it make the log file to be override
3. it need people to make it more better
