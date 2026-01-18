#!/bin/bash

set -e

docker build -t zenith-proxy .
docker save zenith-proxy:latest -o zenith-proxy.tar
