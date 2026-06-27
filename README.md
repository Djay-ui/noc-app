# Teleglobal NOC Automation Platform

A robust, enterprise-grade Network Operations Center (NOC) automation application engineered using **FastAPI**, **PostgreSQL**, and vanilla **JavaScript / HTML5**. Designed to streamline the tracking of customer network circuits, automate operations ticketing tracking, handle escalation notifications via secure SMTP, and provide instant query compilation across network layers.

---

## 🛠️ Infrastructure Requirements & Dependencies

Before beginning deployment, make sure the hosting environment satisfies the following baseline software stack requirements:
*   **Operating System**: Ubuntu 22.04 LTS / 24.04 LTS or equivalent Linux distribution
*   **Database Engine**: PostgreSQL 14 or higher
*   **Runtime Environment**: Python 3.10 or higher
*   **Process Supervisor**: Systemd Daemon Manager

---

## 🚀 Step-by-Step Deployment Guide

### Step 1: Establish Workspace Directory Structure
Initialize the physical path variables and layout environments on the operational host under `/opt`:

```bash
# Create application root workspace directory
sudo mkdir -p /opt/noc-app
sudo chown -R $USER:$USER /opt/noc-app
cd /opt/noc-app

# Construct core application scaffolding layout
mkdir -p templates

# Initialize clean isolated virtual environment
python3 -m venv venv

# Activate target environment scope
source venv/activate

# Upgrade pipeline package collection systems
pip install --upgrade pip

# Install the production dependencies via pip:

pip install -r requirements.txt

# Gain immediate administrative terminal access to database cluster
sudo -u postgres psql

# Execute the database provisioning schema within the interactive prompt:

-- 1. Generate Isolated Application Cluster Target
CREATE DATABASE noc_ticketing;

-- 2. Construct Specialized Automation Administrator Role 
CREATE USER noc_admin WITH ENCRYPTED PASSWORD 'SecureNocPassword2026!';

-- 3. Delegate Administrative Ownership Privileges
GRANT ALL PRIVILEGES ON DATABASE noc_ticketing TO noc_admin;

-- 4. Connect to Target Database Environment Scope
\c noc_ticketing;

-- 5. Construct Core Access Control Scheme (Users)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'operator',
    password_hash VARCHAR(255) NOT NULL
);

-- 6. Construct Core Infrastructure Topology Matrix (Customers & Circuits)
CREATE TABLE customers (
    circuit_id VARCHAR(100) PRIMARY KEY,
    customer_name VARCHAR(150) NOT NULL,
    company_name VARCHAR(200),
    customer_email VARCHAR(150) NOT NULL,
    phone_number VARCHAR(50),
    address TEXT
);

-- 7. Construct Operations Action Database Ledger (Tickets)
CREATE TABLE tickets (
    ticket_id SERIAL PRIMARY KEY,
    circuit_id VARCHAR(100) NOT NULL,
    issue_category VARCHAR(150) NOT NULL,
    root_cause_segment VARCHAR(150),
    status VARCHAR(50) NOT NULL DEFAULT 'Open',
    assigned_team VARCHAR(100) NOT NULL,
    open_by_name VARCHAR(150) NOT NULL,
    closed_by_name VARCHAR(150) DEFAULT '--',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP WITH TIME ZONE,
    resolution_minutes INTEGER DEFAULT 0,
    CONSTRAINT fk_circuit FOREIGN KEY (circuit_id) REFERENCES customers(circuit_id) ON UPDATE CASCADE
);

-- 8. Apply Permissions to System Users
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO noc_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO noc_admin;

-- Exit the cluster prompt
\q


# Create a target service tracking configuration:

sudo nano /etc/systemd/system/nocapp.service

# Paste the unified execution specification profile:

[Unit]
Description=Teleglobal NOC Automation Platform Service Engine
After=network.target postgresql.service

[Service]
User=root
WorkingDirectory=/opt/noc-app
ExecStart=/opt/noc-app/venv/bin/uvicorn main:app --host 0.0.0.0 --port 80
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target

# Reload the service controls matrix, activate the boot listener, and spawn the application instance cleanly:

# Force engine to register new daemon configs
sudo systemctl daemon-reload

# Enable boot sequence persistence
sudo systemctl enable nocapp.service

# Launch application platform instance
sudo systemctl start nocapp.service

# 🧹 Maintenance & Troubleshooting Commands

# Navigate to active application path workspace
cd /opt/noc-app

# Wipe all cached python runtime objects and stale binary bytecodes
sudo find . -type d -name "__pycache__" -exec rm -rf {} +
sudo find . -type f -name "*.pyc" -delete

# Restart your backend service manager process to fetch the newest modifications cleanly
sudo systemctl restart nocapp.service

# Stream active process logs to debug routing actions in real time
sudo journalctl -u nocapp.service -f -n 100

##################################################################################


📂 Step 1: Align Your Workspace Layout
Your main.py backend expects HTML files to reside inside a dedicated templates/ folder. Run these commands to organize your existing files and prepare them for tracking:


cd /opt/noc-app

# Create the templates folder if it doesn't exist yet
mkdir -p templates

# Move your root HTML dashboards into the templates directory
mv dashboard.html templates/ 2>/dev/null
mv tickets.html templates/ 2>/dev/null

# Create your updated circuits.html file inside the templates folder
nano templates/circuits.html





