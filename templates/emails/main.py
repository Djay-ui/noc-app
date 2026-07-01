import smtplib
import io
import csv
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.mime.application import MIMEApplication

app = FastAPI(title="Teleglobal NOC Automation Platform")
templates = Jinja2Templates(directory="templates")

# Configuration Constants
SMTP_SERVER = "mail.teleglobal.in"
SMTP_PORT = 465
SMTP_USER = "noc@teleglobal.in"
SMTP_PASSWORD = "8QKti-lme88&"
GLOBAL_MANDATORY_CC = ["noc@teleglobal.in", "teleglobal2016@gmail.com"]

AUTH_SECRET_KEY = "SUPER_SECRET_NOC_KEY_2026_TRACK_SYSTEM_SECURE"
COOKIE_NAME = "noc_session_token"
PASSWORD_SALT = "noc_salt_2026"

def get_db_connection():
    return psycopg2.connect(
        dbname="noc_ticketing", 
        user="noc_admin", 
        password="SecureNocPassword2026!", 
        host="localhost"
    )

# Async Background Mail Dispatcher (Fixes App Hanging)
def send_smtp_email_background(msg_string: str, all_recipients: list):
    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=10)
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, all_recipients, msg_string)
        server.quit()
    except Exception as smtp_err:
        print(f"Background SMTP Dispatch Failure: {str(smtp_err)}")

# SCALABLE ALARM CONFIGURATION MATRIX
def determine_email_template(issue_category: str, status: str) -> str:
    if not issue_category:
        cat = ""
    else:
        cat = issue_category.strip().lower()

    if cat == "ip is not pingable":
        return "ip_up.html" if status == "Closed" else "ip_down.html"
    elif cat in ["switch isolated", "switch is isolated"]:
        return "switch_up.html" if status == "Closed" else "switch_down.html"

    if status == "Closed":
        return "link_up.html"
    elif status == "In Monitoring":
        return "link_monitoring.html"
    else:
        return "link_down.html"

# Security & Crypto Helpers
def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt_bytes = PASSWORD_SALT.encode('utf-8')
    dk = hashlib.pbkdf2_hmac('sha256', pwd_bytes, salt_bytes, 100000)
    return dk.hex()

def generate_session_token(user_row: dict) -> str:
    expires = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    payload = {
        "id": user_row["id"],
        "username": user_row["username"],
        "full_name": user_row["full_name"],
        "role": user_row["role"],
        "expires": expires
    }
    payload_str = json.dumps(payload)
    signature = hmac.new(AUTH_SECRET_KEY.encode('utf-8'), payload_str.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{payload_str}.{signature}"

def verify_session_token(token: str) -> dict:
    if not token:
        return None
    try:
        payload_str, signature = token.rsplit('.', 1)
        expected_sig = hmac.new(AUTH_SECRET_KEY.encode('utf-8'), payload_str.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        payload = json.loads(payload_str)
        if datetime.fromisoformat(payload["expires"]) < datetime.now(timezone.utc):
            return None
        return payload
    except Exception:
        return None

# Dependency Providers
async def get_current_user(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    user = verify_session_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized session.")
    return user

async def get_optional_user(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    return verify_session_token(token)

class CircuitModel(BaseModel):
    circuit_id: str
    customer_name: str
    company_name: str
    customer_email: str
    phone_number: str
    address: str

class UserUpdateModel(BaseModel):
    user_id: int
    username: str
    full_name: str
    role: str
    password: str = None

# Page Routing Interceptors
@app.get("/login", response_class=HTMLResponse)
async def route_login_page(request: Request, user=Depends(get_optional_user)):
    if user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/", response_class=HTMLResponse)
async def route_dashboard(request: Request, user=Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user})

@app.get("/tickets", response_class=HTMLResponse)
async def route_tickets_page(request: Request, user=Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request=request, name="tickets.html", context={"user": user})

@app.get("/circuits", response_class=HTMLResponse)
async def route_circuits_page(request: Request, user=Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if user["role"] != "admin":
        return HTMLResponse("<html><body><h3>Access Denied: Administrative Clearance Required</h3><a href='/'>Return to Dashboard</a></body></html>", status_code=403)
    return templates.TemplateResponse(request=request, name="circuits.html", context={"user": user})

@app.get("/admin/users", response_class=HTMLResponse)
async def route_user_management_page(request: Request, user=Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if user["role"] != "admin":
        return HTMLResponse("<html><body><h3>Access Denied: Administrative Clearance Required</h3><a href='/'>Return to Dashboard</a></body></html>", status_code=403)
    return templates.TemplateResponse(request=request, name="users.html", context={"user": user})

# Auth Actions
@app.post("/api/auth/login")
async def api_login(username: str = Form(...), password: str = Form(...)):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(%s)", (username.strip(),))
    user = cursor.fetchone()
    cursor.close(); conn.close()

    if not user or user["password_hash"] != hash_password(password):
        return HTMLResponse("<html><body><script>alert('Invalid operational credentials.'); window.location.href='/login';</script></body></html>", status_code=400)
    
    token = generate_session_token(user)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key=COOKIE_NAME, value=token, httponly=True, max_age=43200, samesite="lax")
    return response

@app.get("/api/auth/logout")
async def api_logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response

@app.get("/api/auth/me")
async def api_get_me(user=Depends(get_current_user)):
    return user

# =========================================================================
# FIXED CIRCUITS MANAGEMENT PIPELINE
# =========================================================================

@app.post("/api/tools/send-welcome-mail")
async def api_send_provisioning_welcome_mail(
    background_tasks: BackgroundTasks,
    circuit_id: str = Form(...),
    customer_name: str = Form(...),
    bandwidth_speed: str = Form(...),
    commissioning_date: str = Form(...),
    wan_ip_details: str = Form(...),
    usable_ips: str = Form(...),
    default_gateway: str = Form(...),
    subnet_mask: str = Form(...),
    customer_email: str = Form(...),
    cc_emails: str = Form(""),
    testing_snap: UploadFile = File(...),
    user=Depends(get_current_user)
):
    engineer_identity = user.get("full_name", user.get("username", "NOC Specialist"))
    try:
        with open("/opt/noc-app/templates/emails/welcome_mail.html", "r", encoding="utf-8") as f:
            html_content = f.read()
    except Exception as io_err:
        raise HTTPException(status_code=500, detail=f"Failed to access layout template: {str(io_err)}")

    hydrated_body = html_content \
        .replace("{circuit_id}", str(circuit_id).strip()) \
        .replace("{customer_name}", str(customer_name).strip()) \
        .replace("{bandwidth_speed}", str(bandwidth_speed).strip()) \
        .replace("{commissioning_date}", str(commissioning_date).strip()) \
        .replace("{wan_ip_details}", str(wan_ip_details).strip()) \
        .replace("{usable_ips}", str(usable_ips).strip()) \
        .replace("{default_gateway}", str(default_gateway).strip()) \
        .replace("{subnet_mask}", str(subnet_mask).strip()) \
        .replace("{operator_name}", str(engineer_identity))

    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = customer_email.strip()
    msg['Subject'] = f"Welcome to TeleGlobal Communications Pvt. Ltd || {customer_name.strip()} || {circuit_id.strip()}"
    
    recipients = [customer_email.strip()]
    cc_list = list(GLOBAL_MANDATORY_CC)
    if cc_emails.strip():
        for addr in cc_emails.split(","):
            if addr.strip():
                cc_list.append(addr.strip())
    if cc_list:
        msg['Cc'] = ", ".join(cc_list)
        recipients.extend(cc_list)

    msg.attach(MIMEText(hydrated_body, 'html'))

    try:
        with open("/opt/noc-app/templates/emails/escalation_matrix.html", "r", encoding="utf-8") as esc_file:
            matrix_data = esc_file.read()
        matrix_part = MIMEText(matrix_data, 'html')
        matrix_part.add_header('Content-Disposition', 'attachment', filename="TeleGlobal_Customer_Escalation_Matrix.html")
        msg.attach(matrix_part)
    except Exception as exc_err:
        print(f"Warning: Escalation matrix tracking file not accessible: {str(exc_err)}")

    try:
        file_bytes = await testing_snap.read()
        snap_part = MIMEApplication(file_bytes, Name=testing_snap.filename)
        snap_part['Content-Disposition'] = f'attachment; filename="{testing_snap.filename}"'
        msg.attach(snap_part)
    except Exception as img_err:
         raise HTTPException(status_code=500, detail=f"Failed compiling network log attachments: {str(img_err)}")

    background_tasks.add_task(send_smtp_email_background, msg.as_string(), recipients)
    return {"status": "success", "message": "Provisioning welcome package distributed cleanly via background task layers."}

@app.get("/api/circuits/all")
async def get_all_circuits_fixed(user=Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT circuit_id, customer_name, company_name, customer_email, phone_number, address FROM customers ORDER BY circuit_id ASC")
        return cursor.fetchall()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to fetch matrix rows: {str(e)}")
    finally:
        cursor.close(); conn.close()

@app.post("/api/circuit/save")
async def api_save_or_update_circuit(
    circuit_id: str = Form(...),
    customer_name: str = Form(...),
    company_name: str = Form(""),
    customer_email: str = Form(...),
    phone_number: str = Form(""),
    address: str = Form(""),
    user=Depends(get_current_user)
):
    c_id, c_name, c_email = circuit_id.strip(), customer_name.strip(), customer_email.strip()
    if not c_id or not c_name or not c_email:
        raise HTTPException(status_code=400, detail="Required fields (*) cannot be empty.")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = """
            INSERT INTO customers (circuit_id, customer_name, company_name, customer_email, phone_number, address)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (circuit_id) DO UPDATE SET 
                customer_name = EXCLUDED.customer_name, company_name = EXCLUDED.company_name,
                customer_email = EXCLUDED.customer_email, phone_number = EXCLUDED.phone_number, address = EXCLUDED.address;
        """
        cursor.execute(query, (c_id, c_name, company_name.strip(), c_email, phone_number.strip(), address.strip()))
        conn.commit()
        return {"status": "success", "detail": f"Circuit {c_id} saved successfully."}
    except Exception as e:
        conn.rollback()  
        raise HTTPException(status_code=500, detail=f"Database execution error: {str(e)}")
    finally:
        cursor.close(); conn.close()

@app.get("/api/circuit/{circuit_id}")
async def get_circuit_details(circuit_id: str, user=Depends(get_current_user)):
    search_term = circuit_id.strip()
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    query = """
        SELECT circuit_id, customer_name, company_name, customer_email, phone_number, address FROM customers 
        WHERE LOWER(circuit_id) LIKE LOWER(%s) OR LOWER(customer_name) LIKE LOWER(%s) OR LOWER(company_name) LIKE LOWER(%s)
           OR LOWER(customer_email) LIKE LOWER(%s) OR phone_number LIKE %s OR LOWER(address) LIKE LOWER(%s)
        ORDER BY (LOWER(circuit_id) = LOWER(%s)) DESC
    """
    w = f"%{search_term}%"
    cursor.execute(query, (w, w, w, w, w, w, search_term))
    circuit_records = cursor.fetchall()
    cursor.close(); conn.close()
    if not circuit_records:
        raise HTTPException(status_code=404, detail="No matching customer profile or circuit was found.")
    return circuit_records

@app.post("/api/provision/welcome-handover")
async def api_welcome_handover(
    background_tasks: BackgroundTasks,
    customer_name: str = Form(...),
    circuit_id: str = Form(...),
    bandwidth_speed: str = Form(...),
    commissioning_date: str = Form(...),
    wan_ip_details: str = Form(...),
    usable_ips: str = Form(...),
    default_gateway: str = Form(...),
    subnet_mask: str = Form(...),
    customer_email: str = Form(...),
    cc_emails: str = Form(""),
    testing_snap: UploadFile = File(...),
    escalation_file: UploadFile = File(...), 
    user=Depends(get_current_user)
):
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = customer_email.strip()
    recipients_cc = list(GLOBAL_MANDATORY_CC)
    if cc_emails:
        for c_email in [e.strip() for e in cc_emails.split(",") if e.strip()]:
            if c_email not in recipients_cc: recipients_cc.append(c_email)
    msg['Cc'] = ", ".join(recipients_cc)
    msg['Subject'] = f"Welcome to TeleGlobal Communications || Link Delivery Handover - {circuit_id}"
    
    msg.attach(MIMEText("<h3>Link Handover Delivery</h3>", 'html'))
    
    if testing_snap and testing_snap.filename:
        snap_bytes = await testing_snap.read()
        part1 = MIMEBase('application', 'octet-stream')
        part1.set_payload(snap_bytes); encoders.encode_base64(part1)
        part1.add_header('Content-Disposition', f'attachment; filename="{testing_snap.filename}"')
        msg.attach(part1)
        
    if escalation_file and escalation_file.filename:
        esc_bytes = await escalation_file.read()
        part2 = MIMEBase('application', 'octet-stream')
        part2.set_payload(esc_bytes); encoders.encode_base64(part2)
        part2.add_header('Content-Disposition', f'attachment; filename="{escalation_file.filename}"')
        msg.attach(part2)

    background_tasks.add_task(send_smtp_email_background, msg.as_string(), [customer_email.strip()] + recipients_cc)
    return {"status": "success", "message": "Welcome Onboarding Pack with Multi-Logs dispatched successfully."}

@app.post("/api/ticket/raise")
async def process_raise_ticket(
    background_tasks: BackgroundTasks,
    circuit_id: str = Form(...),
    issue_category: str = Form(...),
    root_cause_segment: str = Form(...),
    status: str = Form(...),
    assigned_team: str = Form(...),
    cc_emails: str = Form(""),
    attachment: UploadFile = File(None),
    user=Depends(get_current_user)
):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT * FROM customers WHERE LOWER(TRIM(circuit_id)) = LOWER(%s)", (circuit_id.strip(),))
        customer = cursor.fetchone()
        if not customer: raise HTTPException(status_code=400, detail="Cannot log ticket against unverified Circuit.")
        
        engineer_identity = user["full_name"].split("|")[0].strip()
        closed_at_timestamp = datetime.now() if status == "Closed" else None
        
        cursor.execute(
            """INSERT INTO tickets (circuit_id, issue_category, root_cause_segment, status, assigned_team, open_by_name, closed_by_name, created_at, closed_at, resolution_minutes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, 0) RETURNING ticket_id, created_at""",
            (circuit_id.strip(), issue_category, root_cause_segment, status, assigned_team, engineer_identity, engineer_identity if status == "Closed" else None, closed_at_timestamp)
        )
        inserted_row = cursor.fetchone()
        conn.commit()
    except Exception as db_err:
        conn.rollback(); raise HTTPException(status_code=500, detail=str(db_err))
    finally:
        cursor.close(); conn.close()

    return {"status": "success", "ticket_id": inserted_row['ticket_id']}

@app.post("/api/ticket/update-status")
async def update_ticket_status(payload: dict, background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    return {"status": "success"}

@app.get("/api/tickets/recent")
async def read_recent_tickets(limit: int = 10, search: str = "", status: str = "", user=Depends(get_current_user)):
    return []

@app.get("/api/reports/download")
async def export_tickets_report(circuit_id: str = "", status: str = "", date_range: str = "all", user=Depends(get_current_user)):
    return None

# =========================================================================
# SYSTEM DIRECT MAIL GENERATION PROCESSING PIPELINE
# =========================================================================

@app.post("/api/system-mail/welcome")
async def api_system_mail_welcome_onboarding(
    background_tasks: BackgroundTasks,
    circuit_id: str = Form(...),
    customer_name: str = Form(...),
    bandwidth_speed: str = Form(...),
    commissioning_date: str = Form(...),
    wan_ip_details: str = Form(...),
    usable_ips: str = Form(...),
    default_gateway: str = Form(...),
    subnet_mask: str = Form(...),
    customer_email: str = Form(...),
    cc_emails: str = Form(""),
    escalation_matrix: UploadFile = File(...),
    testing_snap: UploadFile = File(...),
    user=Depends(get_current_user)
):
    engineer_identity = user.get("full_name", user.get("username", "NOC Operator"))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO customers (circuit_id, customer_name, customer_email, company_name, phone_number, address)
            VALUES (%s, %s, '', %s, '', '')
            ON CONFLICT (circuit_id) DO UPDATE SET
                customer_name = EXCLUDED.customer_name,
                customer_email = EXCLUDED.customer_email;
        """, (circuit_id.strip(), customer_name.strip(), customer_email.strip()))
        conn.commit()
    except Exception as db_sync_err:
        conn.rollback()
        print(f"Non-critical DB Upsert Error: {str(db_sync_err)}")
    finally:
        cursor.close(); conn.close()

    try:
        with open("/opt/noc-app/templates/emails/welcome_mail.html", "r", encoding="utf-8") as f:
            html_content = f.read()
    except Exception as io_err:
        raise HTTPException(status_code=500, detail=f"Failed to access local welcome_mail.html template file: {str(io_err)}")

    hydrated_body = html_content \
        .replace("{circuit_id}", str(circuit_id).strip()) \
        .replace("{customer_name}", str(customer_name).strip()) \
        .replace("{bandwidth_speed}", str(bandwidth_speed).strip()) \
        .replace("{commissioning_date}", str(commissioning_date).strip()) \
        .replace("{wan_ip_details}", str(wan_ip_details).strip()) \
        .replace("{usable_ips}", str(usable_ips).strip()) \
        .replace("{default_gateway}", str(default_gateway).strip()) \
        .replace("{subnet_mask}", str(subnet_mask).strip()) \
        .replace("{operator_name}", str(engineer_identity))

    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = customer_email.strip()
    msg['Subject'] = f"Welcome to TeleGlobal Communications Pvt. Ltd || {customer_name.strip()} || {circuit_id.strip()}"

    recipients = [customer_email.strip()]
    cc_list = list(GLOBAL_MANDATORY_CC)
    if cc_emails.strip():
        for addr in cc_emails.split(","):
            if addr.strip(): cc_list.append(addr.strip())
    msg['Cc'] = ", ".join(cc_list)
    recipients.extend(cc_list)

    msg.attach(MIMEText(hydrated_body, 'html'))

    try:
        esc_bytes = await escalation_matrix.read()
        if esc_bytes:
            part_esc = MIMEBase('application', 'pdf')
            part_esc.set_payload(esc_bytes)
            encoders.encode_base64(part_esc)
            part_esc.add_header('Content-Disposition', f'attachment; filename="{escalation_matrix.filename or "Escalation Matrix.pdf"}"')
            msg.attach(part_esc)
    except Exception as err:
        print(f"Error processing Escalation Matrix attachment: {str(err)}")

    try:
        snap_bytes = await testing_snap.read()
        if snap_bytes:
            part_snap = MIMEBase('application', 'octet-stream')
            part_snap.set_payload(snap_bytes)
            encoders.encode_base64(part_snap)
            part_snap.add_header('Content-Disposition', f'attachment; filename="{testing_snap.filename or "Bandwidth_Testing_Snapshot.png"}"')
            msg.attach(part_snap)
    except Exception as err:
        print(f"Error processing Bandwidth Testing Snapshot: {str(err)}")

    background_tasks.add_task(send_smtp_email_background, msg.as_string(), recipients)
    return {"status": "success", "message": "System onboarding email packet with attachments transmitted smoothly."}
