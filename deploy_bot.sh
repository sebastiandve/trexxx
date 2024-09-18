#!/bin/bash

# Exit on error
set -e

# Update the system
apt-get update
apt-get upgrade -y

# Install required packages
apt-get install -y python3-full python3-venv

# Create a directory for the bot
mkdir -p /opt/trading-bot

# Copy the bot files to the directory
cp -R ./* /opt/trading-bot/
cp .env /opt/trading-bot/

# Change to the bot directory
cd /opt/trading-bot
chown -R nobody:nogroup /opt/trading-bot
chmod 644 my_telegram.session

# Create a virtual environment within the directory
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Now you can safely install pipenv or any other package within the venv
pip install pipenv
pipenv install

# Create a systemd service file
cat << EOF > /etc/systemd/system/trading-bot.service
[Unit]
Description=Trading Bot Service
After=network.target

[Service]
ExecStart=/opt/trading-bot/venv/bin/python /opt/trading-bot/main.py
WorkingDirectory=/opt/trading-bot
Restart=always
User=nobody
Group=nogroup

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd to apply changes
systemctl daemon-reload

# Enable auto-startup and start the service
systemctl enable trading-bot
systemctl start trading-bot

echo "Deployment completed successfully!"