#!/bin/bash
# Auto-deploy personal website from GitHub
# Runs every 5 minutes via cron

REPO_DIR="/root/Personal-Website"
WEB_DIR="/var/www/divinedavis"
LOG_FILE="/var/log/website-deploy.log"

echo "[$(date)] Starting auto-deploy..." >> "$LOG_FILE"

# Navigate to repo
cd "$REPO_DIR" || exit 1

# Pull latest changes
git fetch origin main >> "$LOG_FILE" 2>&1

# Check if there are updates
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "[$(date)] New changes detected, deploying..." >> "$LOG_FILE"
    
    # Pull changes
    git pull origin main >> "$LOG_FILE" 2>&1
    
    # Copy website files to web directory
    cp -r "$REPO_DIR"/* "$WEB_DIR/" >> "$LOG_FILE" 2>&1
    
    # Set correct permissions
    chown -R www-data:www-data "$WEB_DIR"
    chmod -R 755 "$WEB_DIR"
    
    echo "[$(date)] ✅ Deployment successful!" >> "$LOG_FILE"
else
    echo "[$(date)] No changes detected" >> "$LOG_FILE"
fi
