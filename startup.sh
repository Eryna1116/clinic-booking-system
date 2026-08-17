#!/bin/bash
echo "========================================="
echo "  Starting EC2 instance setup"
echo "========================================="


echo "Step 1: Updating system..."
sudo yum update -y


echo "Step 2: Installing Python3 and Git..."
sudo yum install -y python3 python3-pip git


echo "Step 3: Installing PostgreSQL client..."
sudo yum install -y postgresql15


echo "Step 4: Going to home directory..."
cd /home/ec2-user


echo "Step 5: Cloning your code..."
git clone https://github.com/Eryna1116/clinic-booking-system
cd clinic-app


echo "Step 6: Installing Python packages..."
pip3 install -r requirements.txt


echo "Step 7: Setting environment variables..."
export DB_HOST="clinic-db.c4yauadckpyb.us-east-1.rds.amazonaws.com"
export DB_PORT="5432"
export DB_NAME="clinicdb"
export DB_USER="postgres"
export DB_PASSWORD="ClinicApp2026!"


echo "Step 8: Creating database tables..."
python3 -c "from app import app, db; app.app_context().push(); db.create_all()"


echo "Step 9: Starting the app..."
echo "========================================="
echo "  App running on port 5000"
echo "  Health check: /health"
echo "========================================="
python3 app.py
