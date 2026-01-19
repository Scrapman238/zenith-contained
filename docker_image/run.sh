#!/bin/bash
set -e

echo "Container starting..."
exec /root/.venv/bin/python3 -u /root/launch_controller.py
