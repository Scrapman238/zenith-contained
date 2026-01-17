#!/bin/bash
set -e

cd /root

echo "Updating package index..."
sudo apt update -y

echo "Installing prerequisites..."
sudo apt install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    python3-venv

# Check if Docker is already installed
if ! command -v docker >/dev/null 2>&1; then
    echo "Docker not found. Installing Docker..."

    echo "Adding Docker GPG key..."
    sudo mkdir -p /etc/apt/keyrings
    if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
            sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    else
        echo "Docker GPG key already exists, skipping..."
    fi

    echo "Setting up Docker repository..."
    if [ ! -f /etc/apt/sources.list.d/docker.list ]; then
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    else
        echo "Docker repository already exists, skipping..."
    fi

    echo "Updating package index (Docker repo)..."
    sudo apt update -y

    echo "Installing Docker..."
    sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    sudo systemctl start docker
    sudo systemctl enable docker
else
    echo "Docker is already installed. Skipping Docker installation."
fi

docker --version

echo "Setting up Python virtual environment..."
python3 -m venv .venv

echo "Cloning project repository..."
TMP_DIR=$(mktemp -d)
git clone "https://github.com/Scrapman238/zenith-contained.git" "$TMP_DIR"

cp -r "$TMP_DIR"/. /root/
rm -rf "$TMP_DIR"

echo "Installing Python dependencies..."
.venv/bin/pip install -r requirements.txt

echo "Running the application..."
.venv/bin/python3 main.py
