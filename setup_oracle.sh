#!/bin/bash
# ══════════════════════════════════════════════════════════════
# MAX∞ Oracle Cloud Setup Script
# Run this after SSH-ing into your Oracle VPS
# ══════════════════════════════════════════════════════════════

set -e
echo "══════════════════════════════════════════════"
echo "  MAX∞ Server Setup — Oracle Cloud"
echo "══════════════════════════════════════════════"

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
sudo apt install -y python3.11 python3.11-venv python3-pip

# Install Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install PM2 globally
sudo npm install -g pm2

# Install nginx
sudo apt install -y nginx

# Install certbot for free SSL
sudo apt install -y certbot python3-certbot-nginx

# Clone the repo
cd ~
git clone https://github.com/DANIFYCEO/Max-Infinity.git max-infinity
cd max-infinity

# Setup Python environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Setup Baileys
cd baileys
npm install
cd ..

# Create .env from example (user fills in values)
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  Edit .env with your actual API keys:"
    echo "    nano .env"
fi

# Create image cache directory
mkdir -p image_cache

echo ""
echo "══════════════════════════════════════════════"
echo "  Setup complete! Next steps:"
echo "══════════════════════════════════════════════"
echo ""
echo "  1. Edit .env:        nano .env"
echo "  2. Scan QR code:     cd baileys && node index.js"
echo "     (scan with WhatsApp on +2347042650401, then Ctrl+C)"
echo "  3. Start services:   cd .. && pm2 start ecosystem.config.js"
echo "  4. Save PM2:         pm2 save && pm2 startup"
echo "  5. Setup nginx:      See DEPLOY_ORACLE.md"
echo ""
