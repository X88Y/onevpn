#!/bin/bash

# Deployment script for MVM VPN Backend
# This script is intended to be run from the local machine (CI/CD environment)

set -e

REMOTE_HOST="92.118.232.155"
REMOTE_USER="root"
REMOTE_DIR="/root/mvm-vpn"

echo "--- Starting Deployment to $REMOTE_HOST ---"

# 1. Prepare remote directory
echo "Preparing remote directory..."
ssh $REMOTE_USER@$REMOTE_HOST "mkdir -p $REMOTE_DIR/backend && apt-get update && apt-get install -y rsync"

# 2. Upload code
echo "Uploading backend code..."
rsync -avz --exclude '__pycache__' --exclude '.venv' --exclude '.git' ./backend/ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/backend/

# 3. Server-side setup and cleanup
echo "Running server-side setup..."
ssh $REMOTE_USER@$REMOTE_HOST << 'EOF'
    set -e
    
    # 3.1 Stop and delete old services (Scratch)
    echo "Cleaning up old services..."
    systemctl stop hiddify-bot.service hiddify-vkbot.service server-manager.service || true
    systemctl disable hiddify-bot.service hiddify-vkbot.service server-manager.service || true
    rm -f /etc/systemd/system/hiddify-bot.service
    rm -f /etc/systemd/system/hiddify-vkbot.service
    rm -f /etc/systemd/system/server-manager.service
    systemctl daemon-reload

    # 3.2 Install system dependencies
    echo "Installing system dependencies..."
    apt-get update
    apt-get install -y python3-pip python3-venv rsync

    # 3.3 Set up virtual environment
    echo "Setting up virtual environment..."
    cd /root/mvm-vpn/backend
    python3 -m venv .venv
    source .venv/bin/activate
    
    # 3.4 Install requirements
    echo "Installing requirements..."
    pip install --upgrade pip
    if [ -f "bot/requirements.txt" ]; then
        pip install -r bot/requirements.txt
    fi
    if [ -f "server_manager/requirements.txt" ]; then
        pip install -r server_manager/requirements.txt
    fi

    # 3.5 Create new service files
    echo "Creating new service files..."
    
    cat > /etc/systemd/system/mvm-tg-bot.service << EOFF
[Unit]
Description=MVM Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/mvm-vpn/backend/bot
ExecStart=/root/mvm-vpn/backend/.venv/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOFF

    cat > /etc/systemd/system/mvm-vk-bot.service << EOFF
[Unit]
Description=MVM VK Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/mvm-vpn/backend/bot
ExecStart=/root/mvm-vpn/backend/.venv/bin/python3 vk_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOFF

    cat > /etc/systemd/system/mvm-server-manager.service << EOFF
[Unit]
Description=MVM Server Manager
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/mvm-vpn/backend/server_manager
ExecStart=/root/mvm-vpn/backend/.venv/bin/python3 -m uvicorn app:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOFF

    # 3.6 Enable and start services
    echo "Enabling and starting services..."
    systemctl daemon-reload
    systemctl enable mvm-tg-bot.service mvm-vk-bot.service mvm-server-manager.service
    systemctl restart mvm-tg-bot.service mvm-vk-bot.service mvm-server-manager.service

    echo "--- Server-side setup complete ---"
EOF

echo "--- Deployment Successful ---"
