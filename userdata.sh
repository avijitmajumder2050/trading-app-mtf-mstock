#!/bin/bash
set -e

LOGSCANNER=/var/log/trading-bot-scanner-eod.log
LOG=/var/log/trading-bot-scanner-bootstrap.log
exec > >(tee -a $LOG) 2>&1

echo "🚀 Bootstrapping Trading Bot scanner EC2"

REGION="ap-south-1"
SSM_REPO_PARAM="/trading-bot-scanner/github_repo"
APP_USER="ec2-user"
APP_HOME="/home/ec2-user"

S3_BUCKET="s3://dhan-trading-data"
S3_PREFIX="trading-bot"

# -----------------------------
# System update & deps
# -----------------------------
sudo yum update -y
sudo timedatectl set-timezone Asia/Kolkata
sudo yum install -y git python3.11 python3.11-pip python3.11-devel awscli
echo "✅ Installed Python 3.11"
/usr/bin/python3.11 --version
python3 --version  # should remain system 3.9

# -----------------------------
# Safe python aliases (user only)
# -----------------------------
BASHRC="$APP_HOME/.bashrc"
grep -q "alias python=python3.11" "$BASHRC" || echo "alias python=python3.11" >> "$BASHRC"
grep -q "alias pip=pip3.11" "$BASHRC" || echo "alias pip=pip3.11" >> "$BASHRC"

# -----------------------------
# Get repo URL from SSM
# -----------------------------
REPO_URL=$(aws ssm get-parameter \
  --name "$SSM_REPO_PARAM" \
  --region "$REGION" \
  --query "Parameter.Value" \
  --output text)

cd "$APP_HOME"

# -----------------------------
# Clone repo (idempotent)
# -----------------------------
REPO_NAME=$(basename "$REPO_URL" .git)
if [ ! -d "$REPO_NAME" ]; then
  git clone "$REPO_URL"
fi

cd "$REPO_NAME"

# -----------------------------
# Python venv using 3.11
# -----------------------------
if [ ! -d "venv" ]; then
  /usr/bin/python3.11 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
[ -f requirements.txt ] && pip install -r requirements.txt

# -----------------------------
# Runtime dirs
# -----------------------------
mkdir -p logs outputs
chmod -R 755 logs outputs
chown -R $APP_USER:$APP_USER logs outputs

# -----------------------------
# Ensure /var/log exists & writable
# -----------------------------
sudo touch $LOGSCANNER
sudo chown $APP_USER:$APP_USER $LOGSCANNER
sudo chmod 664 $LOGSCANNER
# PYTHONPATH
# -----------------------------
export PYTHONPATH=$PWD
grep -q "export PYTHONPATH=" /home/$APP_USER/.bashrc || \
  echo "export PYTHONPATH=$PWD" >> /home/$APP_USER/.bashrc

# -----------------------------
# Upload ONLY /var/log/trading-bot-scanner-eod.log to S3
# -----------------------------
sudo tee /usr/local/bin/upload-trading-bot-scanner-log.sh > /dev/null <<EOF
#!/bin/bash
aws s3 cp $LOGSCANNER \
  $S3_BUCKET/$S3_PREFIX/logs/trading-bot-scanner-eod.log \
  --region $REGION || true
EOF
sudo chmod +x /usr/local/bin/upload-trading-bot-scanner-log.sh

# -----------------------------
# systemd uploader service
# -----------------------------
sudo tee /etc/systemd/system/trading-bot-scanner-log-upload.service > /dev/null <<EOF
[Unit]
Description=Upload trading-bot-scanner.log to S3

[Service]
Type=oneshot
ExecStart=/usr/local/bin/upload-trading-bot-scanner-log.sh 
EOF

# -----------------------------
# systemd uploader timer (5 min)
# -----------------------------
sudo tee /etc/systemd/system/trading-bot-scanner-log-upload.timer > /dev/null <<EOF
[Unit]
Description=Upload trading-bot-scanner.log to S3 every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
EOF

# -----------------------------
# Trading bot scanner service
# -----------------------------
sudo tee /etc/systemd/system/trading-bot-scanner.service > /dev/null <<EOF
[Unit]
Description=Trading Bot scanner Service
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_HOME/$REPO_NAME
Environment=PYTHONPATH=$APP_HOME/$REPO_NAME
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_HOME/$REPO_NAME/venv/bin/python app/main.py
Restart=always
RestartSec=10
StandardOutput=append:$LOGSCANNER
StandardError=append:$LOGSCANNER
ExecStopPost= /usr/local/bin/upload-trading-bot-scanner-log.sh

[Install]
WantedBy=multi-user.target
EOF

# -----------------------------
# Enable & start
# -----------------------------
sudo systemctl daemon-reload
sudo systemctl enable trading-bot-scanner
sudo systemctl enable --now trading-bot-scanner-log-upload.timer
sudo systemctl restart trading-bot-scanner

echo "✅ Trading Bot scanner started; /var/log/trading-bot-scanner-eod.log uploads to S3 only"
