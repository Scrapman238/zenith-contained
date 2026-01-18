#!/bin/bash
set -e

FLAG="/root/.first_run_done"

echo "Container starting..."

chmod +x /root/launch

if [ ! -f "$FLAG" ]; then
    echo "First run: configuring Zenith (with TTY)"

    script -q -c "/root/launch" /dev/null <<EOF
1
y
2
3000
n
EOF

    touch "$FLAG"
    echo "First-run configuration complete"
fi

echo "Zenith launcher finished. Keeping container alive."
exec tail -f /dev/null
