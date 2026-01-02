#!/bin/bash
# Setup script for automatic website deployment

echo "🚀 Setting up auto-deployment for Divine Davis Portfolio..."

# 1. Clone repository
echo "📦 Cloning repository..."
cd /root
if [ -d "/root/Personal-Website" ]; then
    rm -rf /root/Personal-Website
fi
git clone https://github.com/divinedavis/Personal-Website.git

# 2. Create auto-deploy script
echo "📝 Creating auto-deploy script..."
cat > /root/auto_deploy_website.sh << 'ENDOFSCRIPT'
#!/bin/bash
REPO_DIR="/root/Personal-Website"
WEB_DIR="/var/www/divinedavis"
LOG_FILE="/var/log/website-deploy.log"

echo "[$(date)] Starting auto-deploy..." >> "$LOG_FILE"
cd "$REPO_DIR" || exit 1
git fetch origin main >> "$LOG_FILE" 2>&1
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "[$(date)] New changes detected, deploying..." >> "$LOG_FILE"
    git pull origin main >> "$LOG_FILE" 2>&1
    cp -r "$REPO_DIR"/* "$WEB_DIR/" >> "$LOG_FILE" 2>&1
    chown -R www-data:www-data "$WEB_DIR"
    chmod -R 755 "$WEB_DIR"
    echo "[$(date)] ✅ Deployment successful!" >> "$LOG_FILE"
else
    echo "[$(date)] No changes detected" >> "$LOG_FILE"
fi
ENDOFSCRIPT

chmod +x /root/auto_deploy_website.sh

# 3. Initial deployment
echo "🚀 Running initial deployment..."
mkdir -p /var/www/divinedavis
cp -r /root/Personal-Website/* /var/www/divinedavis/
chown -R www-data:www-data /var/www/divinedavis
chmod -R 755 /var/www/divinedavis

# 4. Setup cron job (every 5 minutes)
echo "⏰ Setting up cron job (every 5 minutes)..."
(crontab -l 2>/dev/null | grep -v auto_deploy_website; echo "*/5 * * * * /root/auto_deploy_website.sh") | crontab -

# 5. Test the script
echo "🧪 Testing deployment script..."
/root/auto_deploy_website.sh

echo ""
echo "✅ Auto-deployment setup complete!"
echo "📍 Your website: http://167.7.170.219"
echo "📝 Logs: tail -f /var/log/website-deploy.log"
echo "🔄 Updates every 5 minutes automatically"
echo ""
echo "📂 Repository: /root/Personal-Website"
echo "🌐 Web directory: /var/www/divinedavis"
echo ""
echo "To manually trigger deployment: /root/auto_deploy_website.sh"
