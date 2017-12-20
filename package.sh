#!/bin/bash
set -e
ZUTILSBRANCH=master
JS9BRANCH=master
if [ -z ${1+x} ]
then 
    ZEROACCESSBRANCH=master
else
    ZEROACCESSBRANCH=$1
fi
if [ ${ZEROACCESSBRANCH} = "master" ]
then
    TAG="latest"
else
    TAG=${ZEROACCESSBRANCH}
fi

name=c$RANDOM
dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

docker rmi -f openvcloud/0-access:${TAG}
docker run --name ${name} -v ${dir}:/tmp/install ubuntu:16.04 bash /tmp/install/install.sh ${ZUTILSBRANCH} ${JS9BRANCH} ${ZEROACCESSBRANCH}
docker commit ${name} openvcloud/0-access:${TAG}
docker rm ${name}