# MAX∞ Oracle Cloud Deployment Guide

## Step 1 — Create Oracle Cloud Account

1. Go to [cloud.oracle.com](https://cloud.oracle.com)
2. Click **Sign Up**
3. Home Region: **UK South (London)** (closest to Nigeria)
   - Backup if capacity issues: **Germany Central (Frankfurt)**
4. Enter your details + card for verification (you will NOT be charged)
5. When asked about account type, choose **Pay As You Go** if available (still free within limits, prevents idle reclamation)

## Step 2 — Create a VM Instance

1. In Oracle Cloud Console → **Compute → Instances → Create Instance**
2. Settings:
   - **Name**: `max-infinity`
   - **Image**: Ubuntu 22.04 (or 24.04)
   - **Shape**: Click **Change Shape** →
     - Shape series: **Ampere** (ARM)
     - OCPU count: **1**
     - Memory: **6 GB**
   - **Networking**: Create new VCN + subnet (defaults are fine)
   - **SSH Keys**: Click **Generate a key pair** → **Download both keys**
     - Save the private key somewhere safe (you need it to SSH in)
3. Click **Create**
4. Wait for the instance to show **RUNNING** (takes ~2 min)
5. Copy the **Public IP Address**

## Step 3 — Open Firewall Ports

1. Go to your instance → **Subnet** link → **Security Lists** → Default
2. Add **Ingress Rules**:
   - Port 80 (HTTP): Source CIDR `0.0.0.0/0`, TCP, Destination Port `80`
   - Port 443 (HTTPS): Source CIDR `0.0.0.0/0`, TCP, Destination Port `443`
3. Also open them in the OS firewall (do this after SSH):
   ```bash
   sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```

## Step 4 — SSH Into Your Server

From your terminal (PowerShell on Windows):
```powershell
ssh -i C:\path\to\your\private-key.key ubuntu@YOUR_PUBLIC_IP
```

If you get a permissions error on Windows:
```powershell
icacls C:\path\to\your\private-key.key /inheritance:r
icacls C:\path\to\your\private-key.key /grant:r "%USERNAME%:(R)"
ssh -i C:\path\to\your\private-key.key ubuntu@YOUR_PUBLIC_IP
```

## Step 5 — Run Setup Script

```bash
# Download and run the setup script
curl -fsSL https://raw.githubusercontent.com/DANIFYCEO/Max-Infinity/main/setup_oracle.sh | bash
```

Or manually:
```bash
cd ~
git clone https://github.com/DANIFYCEO/Max-Infinity.git max-infinity
cd max-infinity
chmod +x setup_oracle.sh
./setup_oracle.sh
```

## Step 6 — Configure Environment

```bash
cd ~/max-infinity
nano .env
```

Fill in ALL your API keys. Save with Ctrl+O, Exit with Ctrl+X.

## Step 7 — Connect WhatsApp (First Time Only)

```bash
cd ~/max-infinity/baileys
node index.js
```

A QR code appears in terminal. Open WhatsApp on the phone with **+2347042650401** → **Linked Devices** → **Link a Device** → Scan the QR code.

Wait for `[BAILEYS] ✅ MAX∞ is live on WhatsApp!`

Then press **Ctrl+C** to stop (we'll use PM2 to manage it properly).

## Step 8 — Start Everything with PM2

```bash
cd ~/max-infinity
source venv/bin/activate
pm2 start ecosystem.config.js
pm2 save
pm2 startup
```

Copy the command PM2 gives you and run it (it sets up auto-start on boot).

Check both services are running:
```bash
pm2 status
```

You should see:
```
┌─────────────┬────┬─────┬──────┬────────┐
│ Name        │ id │ mode│ cpu  │ status │
├─────────────┼────┼─────┼──────┼────────┤
│ max-flask   │ 0  │ fork│ 0%   │ online │
│ max-baileys │ 1  │ fork│ 0%   │ online │
└─────────────┴────┴─────┴──────┴────────┘
```

## Step 9 — Setup Nginx (Reverse Proxy + SSL)

Create nginx config:
```bash
sudo nano /etc/nginx/sites-available/max-infinity
```

Paste this:
```nginx
server {
    listen 80;
    server_name YOUR_PUBLIC_IP;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

Enable it:
```bash
sudo ln -s /etc/nginx/sites-available/max-infinity /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

Test: Visit `http://YOUR_PUBLIC_IP/health` in a browser. You should see:
```json
{"status": "ok", "service": "MAX∞"}
```

## Step 10 — (Optional) Add a Domain + Free SSL

If you have a domain:
1. Point an A record to your Oracle IP
2. Update the nginx config with your domain name
3. Run: `sudo certbot --nginx -d yourdomain.com`

If you don't have a domain, the plain IP works fine for MAX∞. WhatsApp doesn't need HTTPS for Baileys.

## Step 11 — Test MAX∞

Text **"Hello"** from any WhatsApp number to **+2347042650401**.

You should get MAX∞'s onboarding message within seconds.

Then test:
- ✅ Text message
- ✅ Voice note
- ✅ Send an image
- ✅ Type "generate a sunset over Lagos"
- ✅ Send a PDF document
- ✅ Type "HELP"
- ✅ Type "what's the dollar rate today?"

## Step 12 — Admin Dashboard

Visit: `http://YOUR_PUBLIC_IP/admin?key=faber2024`

## Monitoring & Maintenance

```bash
# Check service status
pm2 status

# View Flask logs
pm2 logs max-flask

# View Baileys logs
pm2 logs max-baileys

# Restart everything
pm2 restart all

# If WhatsApp disconnects, re-scan QR:
pm2 stop max-baileys
cd ~/max-infinity/baileys
rm -rf auth_info
node index.js
# Scan QR, then Ctrl+C
pm2 start max-baileys
```

## UptimeRobot Monitoring (Optional but Recommended)

1. Go to [uptimerobot.com](https://uptimerobot.com) → free signup
2. Add monitor: `http://YOUR_PUBLIC_IP/health` every 5 minutes
3. Get email/SMS alerts if server goes down
