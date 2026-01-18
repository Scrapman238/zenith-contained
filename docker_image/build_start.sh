#!/bin/bash

set -e

docker build -t zenith-proxy .
docker save zenith-proxy:latest | gzip >zenith-proxy.tar.gz

docker rm -f zenith
docker run -d \
  --name zenith \
  -p 8080:8080 \
  zenith-proxy

docker ps
sleep 1
docker ps -a
