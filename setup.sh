#!/bin/bash
set -e

cd /root

echo "Updating package index..."
sudo apt update -y

echo "Installing prerequisites..."
sudo apt install -y \
    ca-certificates \
    curl \
    git \
    python3-venv \
    rsync

# --- Docker installation ---
if ! command -v docker >/dev/null 2>&1; then
    echo "Docker not found. Installing Docker..."
    # Use Ubuntu's docker.io package (no GPG key needed)
    sudo apt install -y docker.io docker-compose
    sudo systemctl enable --now docker
else
    echo "Docker is already installed. Skipping Docker installation."
fi

docker --version

mkdir -p /root/Zenith/
cd /root/Zenith/

# --- Python virtual environment ---
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv /root/Zenith/.venv
else
    echo "Python virtual environment already exists. Skipping..."
fi

# --- Project clone / update ---
TMP_DIR=$(mktemp -d)
REPO_URL="https://github.com/Scrapman238/zenith-contained.git"

if [ -d "zenith-contained" ]; then
    echo "Updating existing project..."
    git -C zenith-contained pull
else
    echo "Cloning project repository..."
    git clone "$REPO_URL" "$TMP_DIR"
    rsync -a --ignore-existing "$TMP_DIR/" /root/Zenith/
    rm -rf "$TMP_DIR"
fi

# --- Python dependencies ---
echo "Installing Python dependencies..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

.venv/bin/python3 main.py
