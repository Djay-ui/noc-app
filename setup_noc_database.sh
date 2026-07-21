#!/bin/bash
# ==============================================================================
# END-TO-END POSTGRESQL DATABASE SETUP & SCHEMA RECREATION
# Application: Teleglobal NOC Ticketing & Mail Access System
# Target OS: Ubuntu 24.04 / 26.04 LTS
# Target DB: PostgreSQL 18+
# ==============================================================================

# ------------------------------------------------------------------------------
# STEP 1: INSTALL POSTGRESQL & REQUIRED PACKAGES ON UBUNTU
# ------------------------------------------------------------------------------
echo "==> Step 1: Updating System & Installing PostgreSQL..."
sudo apt update -y
sudo apt install -y postgresql postgresql-contrib python3-psycopg2

# Enable and start PostgreSQL service
sudo systemctl enable postgresql
sudo systemctl start postgresql

# ------------------------------------------------------------------------------
# STEP 2: CREATE DATABASE & USER WITH SECURE CREDENTIALS
# ------------------------------------------------------------------------------
echo "==> Step 2: Provisioning Database 'noc_ticketing' & User 'noc_admin'..."

sudo -u postgres psql << 'EOF'
-- Create Database User if not exists
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'noc_admin') THEN
      CREATE USER noc_admin WITH PASSWORD 'SecureNocPassword2026!';
   END IF;
END
$$;

-- Create Database
DROP DATABASE IF EXISTS noc_ticketing;
CREATE DATABASE noc_ticketing OWNER noc_admin;

-- Grant Privileges
GRANT ALL PRIVILEGES ON DATABASE noc_ticketing TO noc_admin;
EOF

# ------------------------------------------------------------------------------
# STEP 3: CREATE EXACT TABLE SCHEMAS, CONSTRAINTS & INDEXES
# ------------------------------------------------------------------------------
echo "==> Step 3: Executing DDL Scripts to Build Database Schema..."

PGPASSWORD='SecureNocPassword2026!' psql -U noc_admin -d noc_ticketing -h localhost << 'EOF'

-- Grant schema rights
GRANT ALL ON SCHEMA public TO noc_admin;

-- ==============================================================================
-- 1. TABLE: customers
-- Stores circuit metadata, client corporate profiles, and location info
-- ==============================================================================
CREATE TABLE customers (
    circuit_id VARCHAR(100) PRIMARY KEY,
    customer_name VARCHAR(255) NOT NULL,
    company_name VARCHAR(255),
    customer_email VARCHAR(255) NOT NULL,
    phone_number VARCHAR(50),
    address TEXT
);

-- ==============================================================================
-- 2. TABLE: users
-- Core operator authentication table
-- ==============================================================================
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'operator',
    email_id VARCHAR(255) UNIQUE,
    employee_id VARCHAR(50)
);

-- ==============================================================================
-- 3. TABLE: noc_users
-- NOC operational agents, shift leads, and signature metadata
-- ==============================================================================
CREATE TABLE noc_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    signature TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

-- ==============================================================================
-- 4. TABLE: tickets
-- Ticketing operations engine, SLA tracking, and resolution metrics
-- ==============================================================================
CREATE TABLE tickets (
    ticket_id SERIAL PRIMARY KEY,
    circuit_id VARCHAR(100) NOT NULL,
    issue_category VARCHAR(100) NOT NULL,
    root_cause_segment VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    assigned_team VARCHAR(100) NOT NULL,
    open_by_name VARCHAR(255) NOT NULL,
    closed_by_name VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP WITHOUT TIME ZONE,
    resolution_minutes INT DEFAULT 0,
    priority VARCHAR(20) NOT NULL DEFAULT 'P3',
    sla_deadline TIMESTAMP WITH TIME ZONE,
    is_sla_breached BOOLEAN NOT NULL DEFAULT FALSE
);

-- Indexes for performance on lookup queries
CREATE INDEX idx_tickets_circuit_id ON tickets(circuit_id);
CREATE INDEX idx_tickets_search_lookup ON tickets(circuit_id, open_by_name);
CREATE INDEX idx_tickets_created_at_desc ON tickets(created_at DESC);
CREATE INDEX idx_tickets_status ON tickets(status);
CREATE INDEX idx_tickets_assigned_team ON tickets(assigned_team);

-- ==============================================================================
-- 5. TABLE: bandwidth_upgrade_logs
-- Logs bandwidth change activities
-- ==============================================================================
CREATE TABLE bandwidth_upgrade_logs (
    id SERIAL PRIMARY KEY,
    circuit_id VARCHAR(100),
    old_bandwidth VARCHAR(50),
    new_bandwidth VARCHAR(50),
    upgraded_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_bandwidth_upgrade_logs_date ON bandwidth_upgrade_logs(upgraded_at);

-- ==============================================================================
-- 6. TABLE: link_termination_logs
-- Logs decommissioned/terminated circuit links
-- ==============================================================================
CREATE TABLE link_termination_logs (
    id SERIAL PRIMARY KEY,
    circuit_id VARCHAR(100),
    reason TEXT,
    terminated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_link_termination_logs_date ON link_termination_logs(terminated_at);

-- ==============================================================================
-- 7. TABLE: welcome_mail_logs
-- Audit table for dispatched customer welcome communications
-- ==============================================================================
CREATE TABLE welcome_mail_logs (
    id SERIAL PRIMARY KEY,
    circuit_id VARCHAR(100),
    dispatched_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_welcome_mail_logs_dispatched_at ON welcome_mail_logs(dispatched_at);
CREATE INDEX idx_welcome_mail_logs_date ON welcome_mail_logs(dispatched_at);

-- ==============================================================================
-- 8. TABLE: event_welcome_logs
-- Event logs for site provisioning and mail notifications
-- ==============================================================================
CREATE TABLE event_welcome_logs (
    id SERIAL PRIMARY KEY,
    circuit_id VARCHAR(255) NOT NULL,
    customer_name VARCHAR(255) NOT NULL,
    bandwidth VARCHAR(100),
    event_date VARCHAR(255),
    usable_ip VARCHAR(255),
    gateway VARCHAR(255),
    subnet VARCHAR(255),
    customer_email VARCHAR(255),
    cc_emails TEXT,
    sent_by VARCHAR(255),
    sent_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

EOF

# ------------------------------------------------------------------------------
# STEP 4: SEED SEED DATA FOR TESTING / VERIFICATION
# ------------------------------------------------------------------------------
echo "==> Step 4: Seeding Initial Test Data..."

PGPASSWORD='SecureNocPassword2026!' psql -U noc_admin -d noc_ticketing -h localhost << 'EOF'

-- Insert Customer Records
INSERT INTO customers (circuit_id, customer_name, company_name, customer_email, phone_number, address) 
VALUES 
('CKT-MUM-0092', 'John Doe', 'Teleglobal Corp India', 'noc@teleglobal.in', '+91 20-48522500', 'Pune HQ Cerebrum Park'),
('CKT-DEL-1141', 'Alice Smith', 'Global Infrastructure Tech', 'noc@teleglobal.in', '+91 8855811141', 'Delhi Core POP Hub');

-- Insert System Operators
INSERT INTO users (username, password_hash, full_name, role) 
VALUES 
('admin', 'c8e693874aacdb1ffbe31071bdd2f3b55fee296309b967e262ea90a3484219b2', 'Backup Administrator Desk', 'admin'),
('prashant', 'c8e693874aacdb1ffbe31071bdd2f3b55fee296309b967e262ea90a3484219b2', 'Prashant Marathe | L2 support', 'operator');

-- Insert NOC Users
INSERT INTO noc_users (username, password_hash, full_name, email, signature, is_active)
VALUES
('agent.alex', 'hash', 'Alex Mercer (Tier 1 Support)', 'alex@company.com', 'Thanks,' || chr(10) || 'Alex Mercer' || chr(10) || 'NOC Tier 1 Analyst | Core Networks', true),
('agent.sarah', 'hash', 'Sarah Connor (Shift Lead)', 'sarah@company.com', 'Best Regards,' || chr(10) || 'Sarah Connor' || chr(10) || 'NOC Operations Shift Lead', true);

EOF

echo "==> PostgreSQL Setup & Schema Provisioning Completed Successfully!"
