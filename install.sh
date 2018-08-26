#!/bin/bash
set -e
# prepare system
apt-get update
apt-get install -y sudo curl openssh-server locales
# install 0-access software
cd
wget https://github.com/0-complexity/0-access/archive/${ZEROACCESSBRANCH}.zip
unzip ${ZEROACCESSBRANCH}.zip
mkdir -p /opt/0-access
cp -r 0-access-${ZEROACCESSBRANCH}/* /opt/0-access
cp 0-access-${ZEROACCESSBRANCH}/lash /bin
chmod 755 /bin/lash
rm ${ZEROACCESSBRANCH}.zip
wget https://github.com/xmonader/Flask_Itsyouonline/archive/master.zip
unzip master.zip
cp Flask_Itsyouonline-master/flask_itsyouonline.py /opt/0-access
cd /opt/0-access
pip3 install -r requirements.txt
mkdir -p /var/recordings/index
chmod -R 777 /var/recordings
mkdir -p /var/run/sshd

# add correct locals
locale-gen en_US.UTF-8
