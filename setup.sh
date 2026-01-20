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
    rsync \
    wget

# --- Install Git LFS ---
if ! command -v git-lfs >/dev/null 2>&1; then
    echo "Installing Git LFS..."
    curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.deb.sh | sudo bash
    sudo apt install -y git-lfs
    git lfs install
else
    echo "Git LFS already installed. Skipping..."
fi

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
    cd zenith-contained
    git lfs pull  # <- pull the actual large files
    cd ..
else
    echo "Cloning project repository..."
    git clone "$REPO_URL" "$TMP_DIR"
    cd "$TMP_DIR"
    git lfs pull  # <- pull LFS files
    rsync -a --ignore-existing "$TMP_DIR/" /root/Zenith/
    cd /root/Zenith/
    rm -rf "$TMP_DIR"
fi

cp /root/Zenith/run.sh /root/launch
chmod +x /root/launch

ZENITH_TAR="/root/Zenith/docker_image/zenith-proxy.tar"

if [ -f "$ZENITH_TAR" ]; then
    echo "Loading Zenith Docker image..."
    docker load -i "$ZENITH_TAR"
else
    echo "ERROR: Docker image not found at $ZENITH_TAR"
    exit 1
fi

# --- Python dependencies ---
echo "Installing Python dependencies..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

.venv/bin/python3 main.py
