# 📈 Trading App – MTF MStock Automated Bot

Automated intraday trading system running on AWS EC2 with:

- ⏰ Time-controlled execution (9:31–11:00 IST)
- 🌆 4 PM post-market monitor
- 🔁 Random EC2 auto-termination (2–5 minutes delay)
- 📲 Telegram alerts
- ☁ AWS S3 integration
- 📊 Nifty trend filter
- 🛡 One trade per day protection

---

# 🏗 System Architecture

## 🌅 Morning Session

1. EventBridge starts EC2 at **9:30 AM IST**
2. Script runs from **9:31 AM to 11:00 AM IST**
3. Every 60 seconds:
   - Run Entry Engine
   - Run Trade Monitor
4. At 11:00:
   - Telegram alert sent
   - EC2 terminates after random 2–5 minutes

---

## 🌆 Evening Session

1. EventBridge starts EC2 at **4:00 PM IST**
2. Runs Monitor once
3. Sends Telegram alert
4. Terminates EC2 after 2–5 minutes

---

# ⚙️ Tech Stack

- Python 3.11
- AsyncIO
- boto3 (AWS SDK)
- AWS EC2
- AWS EventBridge
- AWS S3
- Telegram Bot API
- MStock Trading API

---

# 📂 Project Structure

```
trading-app-mtf-mstock/
│
├── app/
│   ├── main.py
│   ├── services/
│   ├── config/
│   ├── strategy/
│   ├── execution/
│
├── requirements.txt
└── README.md
```

---

# 🚀 EC2 Deployment Guide

## 1️⃣ Launch EC2

Recommended:
- Instance type: t3.micro
- OS: Amazon Linux 2
- Enable Instance Metadata
- Attach IAM role (see below)

---

## 2️⃣ Install Dependencies

```bash
sudo yum update -y
sudo yum install git python3 -y

cd /home/ec2-user
git clone <your-repo-url>
cd trading-app-mtf-mstock

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

---

## 3️⃣ Fix Logging Permission (IMPORTANT)

The `tradingapi_a` library writes `mconnect.log`.

```bash
sudo chown -R ec2-user:ec2-user /home/ec2-user/trading-app-mtf-mstock
touch /home/ec2-user/trading-app-mtf-mstock/mconnect.log
chmod 666 /home/ec2-user/trading-app-mtf-mstock/mconnect.log
```

Without this fix, the app will crash with:

```
PermissionError: mconnect.log
```

---

# 🔐 Required IAM Role

Attach this policy to EC2:

```json
{
  "Effect": "Allow",
  "Action": "ec2:TerminateInstances",
  "Resource": "*"
}
```

This allows EC2 to terminate itself.

---

# ⏰ EventBridge Scheduling

## Morning Rule (Start EC2 at 9:30 IST)

```
cron(0 4 ? * MON-FRI *)
```

(9:30 IST = 04:00 UTC)

Target → Start EC2 Instance

---

## Evening Rule (Start EC2 at 4:00 PM IST)

```
cron(30 10 ? * MON-FRI *)
```

(16:00 IST = 10:30 UTC)

Target → Start EC2 Instance

---

# 🔁 EC2 Auto Termination

Function used:

```python
async def terminate_after_delay(max_delay_minutes=5):
```

Behavior:
- Random shutdown between 2–5 minutes
- Telegram alert before shutdown
- Uses EC2 metadata to identify itself
- Calls ec2:TerminateInstances

---

# 📲 Telegram Notifications

Alerts sent for:

- Trade execution
- Trade failure
- Nifty filter skip
- EC2 shutdown scheduling
- Errors

---

# 📊 Trading Logic

## Strategy Flow

1. Read breakout signals from S3
2. Rank stocks
3. Apply Nifty filter
4. Execute best valid stock
5. Allow only one trade per day

---

# 🐞 Troubleshooting

## Permission Error: mconnect.log

Fix:

```bash
chmod 666 mconnect.log
```

---

## EC2 Not Terminating

Check:

- IAM role attached
- Correct AWS region
- Instance metadata enabled

---

## Service Keeps Restarting

Check:

```bash
sudo systemctl status trading-app-mtf-mstock
```

If using:

```
Restart=always
```

It will restart on crash.

---

# 💰 Cost Optimization

- No Elastic IP
- Runs ~1–2 hours daily
- Use Spot instance (optional)
- Auto-termination prevents idle billing

---

# 🔄 Execution Flow

```
EventBridge → Start EC2
        ↓
main.py runs
        ↓
9:31–11:00 loop
        ↓
Schedule random termination
        ↓
EC2 terminates itself

4 PM → Start EC2 again
        ↓
Run monitor once
        ↓
Terminate after delay
```

---

# 🛡 Production Notes

- Do not hardcode credentials
- Use IAM role for AWS
- Store API keys in environment variables
- Monitor logs in /var/log
- Backup logs to S3

---

# 👨‍💻 Maintainer

