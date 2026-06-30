#!/bin/bash

# Deployment script for MVM VPN Backend
# This script is intended to be run from the local machine (CI/CD environment)

set -e

REMOTE_HOST="185.230.143.98"
REMOTE_USER="root"
REMOTE_DIR="/root/mvm-vpn"
SSH_PASSWORD="${SSH_PASSWORD:-zgtejT3R7v0u}"

# SSH and Rsync wrapper functions to support password-based authentication via sshpass
run_ssh() {
    if [ -n "$SSH_PASSWORD" ]; then
        if ! command -v sshpass &> /dev/null; then
            echo "Error: sshpass is required for password authentication but is not installed." >&2
            exit 1
        fi
        sshpass -p "$SSH_PASSWORD" ssh -o StrictHostKeyChecking=no "$@"
    else
        ssh "$@"
    fi
}

run_rsync() {
    if [ -n "$SSH_PASSWORD" ]; then
        if ! command -v sshpass &> /dev/null; then
            echo "Error: sshpass is required for password authentication but is not installed." >&2
            exit 1
        fi
        rsync -avz -e "sshpass -p '$SSH_PASSWORD' ssh -o StrictHostKeyChecking=no" "$@"
    else
        rsync -avz "$@"
    fi
}

echo "--- Starting Deployment to $REMOTE_HOST ---"

# 1. Prepare remote directory
echo "Preparing remote directory..."
run_ssh $REMOTE_USER@$REMOTE_HOST "mkdir -p $REMOTE_DIR/backend && apt-get update && apt-get install -y rsync"

# 2. Upload code
echo "Uploading backend code..."
run_rsync --exclude '__pycache__' --exclude '.venv' --exclude '.git' ./backend/ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/backend/

# 3. Server-side setup and cleanup
echo "Running server-side setup..."
run_ssh $REMOTE_USER@$REMOTE_HOST << 'EOF'
    set -e
    
    # 3.1 Stop and delete old services (Scratch)
    echo "Cleaning up old services..."
    systemctl stop hiddify-bot.service hiddify-vkbot.service server-manager.service mvm-admin-bot.service || true
    systemctl disable hiddify-bot.service hiddify-vkbot.service server-manager.service mvm-admin-bot.service || true
    rm -f /etc/systemd/system/hiddify-bot.service
    rm -f /etc/systemd/system/hiddify-vkbot.service
    rm -f /etc/systemd/system/server-manager.service
    rm -f /etc/systemd/system/mvm-admin-bot.service
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
    if [ -f "bot_admin/requirements.txt" ]; then
        pip install -r bot_admin/requirements.txt
    fi
    if [ -f "remnawave_webhook_server/requirements.txt" ]; then
        pip install -r remnawave_webhook_server/requirements.txt
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
WorkingDirectory=/root/mvm-vpn/backend
ExecStart=/root/mvm-vpn/backend/.venv/bin/python3 -m uvicorn server_manager.app:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOFF

    cat > /etc/systemd/system/mvm-admin-bot.service << EOFF
[Unit]
Description=MVM Admin Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/mvm-vpn/backend
ExecStart=/root/mvm-vpn/backend/.venv/bin/python3 -m bot_admin
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOFF

    cat > /etc/systemd/system/mvm-remnawave-webhook.service << EOFF
[Unit]
Description=MVM Remnawave Webhook Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/mvm-vpn/backend
ExecStart=/root/mvm-vpn/backend/.venv/bin/python3 -m remnawave_webhook_server
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOFF

    # 3.6 Enable and start services
    echo "Enabling and starting services..."
    systemctl daemon-reload
    systemctl enable mvm-tg-bot.service mvm-vk-bot.service mvm-server-manager.service mvm-admin-bot.service mvm-remnawave-webhook.service
    systemctl restart mvm-tg-bot.service mvm-vk-bot.service mvm-server-manager.service mvm-admin-bot.service mvm-remnawave-webhook.service

    echo "--- Server-side setup complete ---"
EOF

echo "--- Deployment Successful ---"
