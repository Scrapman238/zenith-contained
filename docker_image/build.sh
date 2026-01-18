#!/bin/bash

set -e

docker build -t zenith-proxy .
docker save zenith-proxy:latest | gzip >zenith-proxy.tar.gz
