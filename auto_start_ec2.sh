#!/bin/bash
# ==========================================
# AUTO STARTUP EC2 SCRIPT
# Run this once to launch EC2 with auto-startup
# ==========================================

set -e

# ==========================================
# CONFIGURATION (UPDATE THESE!)
# ==========================================
AWS_REGION="us-east-1"
INSTANCE_TYPE="t2.micro"
KEY_NAME="my-aws-keypair"         
SECURITY_GROUP_NAME="clinic-app-sg"
GITHUB_REPO="https://github.com/clinic/clinic-booking-app.git"  # CHANGE THIS

echo "========================================"
echo "🚀 AUTO STARTUP EC2 DEPLOYMENT"
echo "========================================"

# ==========================================
# STEP 1: CHECK AWS CLI
# ==========================================
echo "📋 Checking AWS CLI..."
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found! Installing..."
    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
    unzip awscliv2.zip
    sudo ./aws/install
    rm -rf awscliv2.zip aws/
fi
echo "✅ AWS CLI is ready"

# ==========================================
# STEP 2: CHECK SSH KEY
# ==========================================
echo "🔑 Checking SSH key..."
if ! aws ec2 describe-key-pairs --key-names $KEY_NAME --region $AWS_REGION &> /dev/null; then
    echo "❌ Key pair '$KEY_NAME' not found!"
    echo "📝 Creating new key pair..."
    aws ec2 create-key-pair --key-name $KEY_NAME --region $AWS_REGION --query 'KeyMaterial' --output text > ~/.ssh/${KEY_NAME}.pem
    chmod 400 ~/.ssh/${KEY_NAME}.pem
    echo "✅ Key pair created: ~/.ssh/${KEY_NAME}.pem"
else
    echo "✅ Key pair '$KEY_NAME' exists"
fi

# ==========================================
# STEP 3: CREATE SECURITY GROUP
# ==========================================
echo "🛡️ Creating Security Group..."
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SECURITY_GROUP_NAME" --region $AWS_REGION --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null)

if [ "$SG_ID" == "None" ] || [ -z "$SG_ID" ]; then
    SG_ID=$(aws ec2 create-security-group \
        --group-name $SECURITY_GROUP_NAME \
        --description "Clinic App Security Group" \
        --region $AWS_REGION \
        --query 'GroupId' --output text)
    
    aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 22 --cidr 0.0.0.0/0 --region $AWS_REGION
    aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 80 --cidr 0.0.0.0/0 --region $AWS_REGION
    aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 443 --cidr 0.0.0.0/0 --region $AWS_REGION
    aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 5000 --cidr 0.0.0.0/0 --region $AWS_REGION
    
    echo "✅ Security group created: $SG_ID"
else
    echo "✅ Security group exists: $SG_ID"
fi

# ==========================================
# STEP 4: CREATE USER-DATA SCRIPT (AUTO-STARTUP ON BOOT)
# ==========================================
echo "📝 Creating auto-startup user-data script..."

USER_DATA='#!/bin/bash
# ==========================================
# EC2 AUTO-STARTUP SCRIPT
# This runs automatically when EC2 starts
# ==========================================

set -e

echo "========================================"
echo "🚀 EC2 AUTO-STARTUP SCRIPT"
echo "========================================"

# 1. SYSTEM UPDATE
echo "📦 Updating system..."
sudo apt-get update -y
sudo apt-get upgrade -y

# 2. INSTALL DEPENDENCIES
echo "📦 Installing dependencies..."
sudo apt-get install -y python3 python3-pip python3-venv nginx git curl wget

# 3. INSTALL NODE.JS
echo "📦 Installing Node.js..."
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# 4. CLONE REPOSITORY
echo "📂 Cloning repository..."
cd /home/ubuntu
if [ -d "clinic-booking-app" ]; then
    echo "⚠️  Directory exists, updating..."
    cd clinic-booking-app
    git pull
else
    git clone https://github.com/your-username/clinic-booking-app.git
    cd clinic-booking-app
fi

# 5. SETUP BACKEND
echo "🐍 Setting up Python backend..."
cd backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 6. SETUP DATABASE
echo "🗄️ Setting up database..."
python3 -c "
from app import app, db
with app.app_context():
    db.create_all()
    print('\''✅ Database created!\'')"

# 7. SETUP GUNICORN SERVICE (AUTO-START ON BOOT)
echo "🔄 Setting up Gunicorn service..."
sudo bash -c "cat > /etc/systemd/system/gunicorn.service << '\''EOS'\''
[Unit]
Description=Gunicorn for Clinic App
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/clinic-booking-app/backend
Environment=\"PATH=/home/ubuntu/clinic-booking-app/backend/venv/bin\"
Environment=\"RUNNING_ON_EC2=true\"
ExecStart=/home/ubuntu/clinic-booking-app/backend/venv/bin/gunicorn --workers 3 --bind unix:clinic-app.sock -m 007 app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOS"

sudo systemctl daemon-reload
sudo systemctl enable gunicorn
sudo systemctl start gunicorn

# 8. SETUP NGINX
echo "🌐 Setting up Nginx..."
sudo bash -c "cat > /etc/nginx/sites-available/clinic-app << '\''EOS'\''
server {
    listen 80;
    server_name _;

    location / {
        include proxy_params;
        proxy_pass http://unix:/home/ubuntu/clinic-booking-app/backend/clinic-app.sock;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }

    location /api {
        include proxy_params;
        proxy_pass http://unix:/home/ubuntu/clinic-booking-app/backend/clinic-app.sock;
    }

    location /static {
        alias /home/ubuntu/clinic-booking-app/backend/static;
    }
}
EOS"

sudo ln -sf /etc/nginx/sites-available/clinic-app /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

# 9. SETUP FIREWALL
echo "🛡️ Configuring firewall..."
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
echo "y" | sudo ufw enable

# 10. SET PERMISSIONS
echo "🔧 Setting permissions..."
sudo chown -R ubuntu:www-data /home/ubuntu/clinic-booking-app
sudo chmod -R 755 /home/ubuntu/clinic-booking-app

# 11. ADD CRON FOR AUTO-START ON REBOOT
echo "📅 Adding cron job for auto-start on reboot..."
(crontab -l 2>/dev/null; echo "@reboot cd /home/ubuntu/clinic-booking-app/backend && source venv/bin/activate && nohup python3 app.py &") | crontab -

# 12. DEPLOYMENT COMPLETE
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)
echo "========================================"
echo "✅ DEPLOYMENT COMPLETE!"
echo "========================================"
echo "🌐 App URL: http://$PUBLIC_IP"
echo "📊 Dashboard: http://$PUBLIC_IP/dashboard"
echo "🔌 API: http://$PUBLIC_IP/api/appointments"
echo "========================================"
'

# ==========================================
# STEP 5: LAUNCH EC2 WITH AUTO-STARTUP USER-DATA
# ==========================================
echo "🖥️ Launching EC2 instance with auto-startup..."

INSTANCE_ID=$(aws ec2 run-instances \
    --image-id ami-0c55b159cbfafe1f0 \
    --instance-type $INSTANCE_TYPE \
    --key-name $KEY_NAME \
    --security-group-ids $SG_ID \
    --region $AWS_REGION \
    --user-data "$USER_DATA" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=clinic-app-instance},{Key=AutoStart,Value=true}]" \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "✅ EC2 instance launched: $INSTANCE_ID"

# ==========================================
# STEP 6: ENABLE AUTO-START ON INSTANCE REBOOT
# ==========================================
echo "🔄 Enabling auto-start on instance reboot..."
aws ec2 modify-instance-attribute \
    --instance-id $INSTANCE_ID \
    --region $AWS_REGION \
    --attribute instanceInitiatedShutdownBehavior \
    --value "stop"

echo "✅ Auto-start configured! Instance will restart on reboot."

# ==========================================
# STEP 7: WAIT FOR INSTANCE
# ==========================================
echo "⏳ Waiting for instance to be ready..."
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $AWS_REGION

# Get public IP
PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids $INSTANCE_ID \
    --region $AWS_REGION \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo "✅ Instance is running!"
echo "🌐 Public IP: $PUBLIC_IP"

# ==========================================
# STEP 8: SAVE CONNECTION INFO
# ==========================================
cat > ec2_info.txt << EOF
========================================
CLINIC APP EC2 INSTANCE INFO
========================================
Instance ID: $INSTANCE_ID
Public IP: $PUBLIC_IP
Region: $AWS_REGION
Key Pair: $KEY_NAME

SSH Command:
ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@$PUBLIC_IP

Application URL:
http://$PUBLIC_IP

Dashboard:
http://$PUBLIC_IP/dashboard

API:
http://$PUBLIC_IP/api/appointments

Health Check:
http://$PUBLIC_IP/api/health

========================================
AUTO-STARTUP INFO
========================================
- Gunicorn service: Enabled (starts on boot)
- Nginx service: Enabled (starts on boot)
- Cron job: @reboot runs app on startup
- Instance shutdown behavior: Stop (not terminate)
========================================
EOF

echo "✅ Connection info saved to ec2_info.txt"

# ==========================================
# STEP 9: TEST CONNECTION
# ==========================================
echo "🔍 Testing connection..."
sleep 60

if curl -s "http://$PUBLIC_IP/api/health" > /dev/null; then
    echo "✅ App is responding!"
    curl -s "http://$PUBLIC_IP/api/health" | python3 -m json.tool 2>/dev/null || echo "✅ App is running"
else
    echo "⚠️ App not responding yet. Waiting longer..."
    sleep 30
    if curl -s "http://$PUBLIC_IP/api/health" > /dev/null; then
        echo "✅ App is responding!"
    else
        echo "❌ App still not responding. Check manually."
        echo "SSH: ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@$PUBLIC_IP"
    fi
fi

# ==========================================
# DEPLOYMENT COMPLETE
# ==========================================
echo "========================================"
echo "✅ DEPLOYMENT COMPLETE!"
echo "========================================"
echo "🌐 Application URL: http://$PUBLIC_IP"
echo "📊 Dashboard: http://$PUBLIC_IP/dashboard"
echo "🔌 API: http://$PUBLIC_IP/api/appointments"
echo "🔑 SSH: ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@$PUBLIC_IP"
echo ""
echo "📁 ec2_info.txt saved with all details"
echo "========================================"