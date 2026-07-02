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
from fastapi import Query
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.mime.application import MIMEApplication
from typing import Optional
from fastapi import Request, HTTPException

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
    """
    Centralized router mapping alert rules to target email templates.
    To add a new custom alarm in the future, simply append a new 'elif' branch here.
    """
    if not issue_category:
        cat = ""
    else:
        cat = issue_category.strip().lower()

    # 1. Configuration rule for "IP is not pingable"
    if cat == "ip is not pingable":
        return "ip_up.html" if status == "Closed" else "ip_down.html"

    # 2. Configuration rule for "Switch Isolated"
    elif cat in ["switch isolated", "switch is isolated"]:
        return "switch_up.html" if status == "Closed" else "switch_down.html"

    # Default Fallback for generic/other link incidents
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

class ReportPayload(BaseModel):
    report_type: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    team: Optional[str] = None

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

@app.get("/system-mail/welcome", response_class=HTMLResponse)
async def route_system_mail_welcome_page(request: Request, user=Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request=request, name="system_mail_welcome.html", context={"user": user})

@app.get("/system-mail/bandwidth", response_class=HTMLResponse)
async def route_bandwidth_change_page(request: Request, user=Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request=request, name="system_mail_bandwidth.html", context={"user": user})

@app.get("/system-mail/terminate", response_class=HTMLResponse)
async def route_link_termination_page(request: Request, user=Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request=request, name="system_mail_terminate.html", context={"user": user})

@app.get("/system-mail/rfo")
async def rfo_page(request: Request):
    # Ensure the second argument is a flat dictionary containing the 'request' object
    return templates.TemplateResponse(
        "system_mail_rfo.html", 
        {"request": request}
    )

@app.get("/admin/users", response_class=HTMLResponse)
async def route_user_management_page(request: Request, user=Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if user["role"] != "admin":
        return HTMLResponse("<html><body><h3>Access Denied: Administrative Clearance Required</h3><a href='/'>Return to Dashboard</a></body></html>", status_code=403)
    return templates.TemplateResponse(request=request, name="users.html", context={"user": user})

@app.get("/reports", response_class=HTMLResponse)
async def get_reports_page(request: Request, user=Depends(get_optional_user)):
    # 1. Enforce session security (redirect to login if session token is missing/invalid)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # 2. Render safely using explicit keyword arguments matching your environment
    return templates.TemplateResponse(
        request=request, 
        name="reports.html", 
        context={"user": user}
    )
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
# FIXED CIRCUITS MANAGEMENT PIPELINE (COMPANY REFACTOR & MULTI-EMAIL)
# =========================================================================

@app.post("/api/tools/send-welcome-mail")
async def api_send_provisioning_welcome_mail(
    background_tasks: BackgroundTasks,
    circuit_id: str = Form(...),
    company_name: str = Form(...),
    bandwidth_speed: str = Form(...),
    commissioning_date: str = Form(...),
    wan_ip_details: str = Form(...),
    usable_ips: str = Form(...),
    default_gateway: str = Form(...),
    subnet_mask: str = Form(...),
    customer_email: str = Form(...),
    cc_emails: str = Form(""),
    testing_snap: UploadFile = File(...),
    escalation_matrix: UploadFile = File(...), 
    user=Depends(get_current_user)
):
    engineer_identity = user.get("full_name", user.get("username", "NOC Specialist"))
    if "|" in engineer_identity:
        engineer_identity = engineer_identity.split("|")[0].strip()

    try:
        parsed_date = datetime.strptime(commissioning_date.strip(), "%Y-%m-%d")
        formatted_date = parsed_date.strftime("%d %B %Y")
    except Exception:
        formatted_date = commissioning_date.strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        db_query = """
            INSERT INTO customers (circuit_id, customer_name, customer_email)
            VALUES (%s, %s, %s)
            ON CONFLICT (circuit_id) DO UPDATE SET
                customer_name = EXCLUDED.customer_name,
                customer_email = EXCLUDED.customer_email;
        """
        cursor.execute(db_query, (circuit_id.strip(), company_name.strip(), customer_email.strip()))
        conn.commit()
    except Exception as db_err:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database synchronization failed: {str(db_err)}")
    finally:
        cursor.close()
        conn.close()

    try:
        template = templates.get_template("emails/welcome_mail.html")
        hydrated_body = template.render({
            "circuit_id": circuit_id.strip(),
            "company_name": company_name.strip(),
            "bandwidth_speed": bandwidth_speed.strip(),
            "commissioning_date": formatted_date,
            "wan_ip_details": wan_ip_details.strip(),
            "usable_ips": usable_ips.strip(),
            "default_gateway": default_gateway.strip(),
            "subnet_mask": subnet_mask.strip(),
            "operator_name": engineer_identity
        })
    except Exception as render_err:
        raise HTTPException(status_code=500, detail=f"Failed to compile template placeholders: {str(render_err)}")

    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    
    to_recipients = [addr.strip() for addr in customer_email.split(",") if addr.strip()]
    msg['To'] = ", ".join(to_recipients)
    msg['Subject'] = f"Welcome to TeleGlobal Communications Pvt. Ltd || {company_name.strip()} || {circuit_id.strip()}"
    
    recipients = list(to_recipients)
    cc_list = list(GLOBAL_MANDATORY_CC)
    if cc_emails.strip():
        for addr in cc_emails.split(","):
            if addr.strip():
                cc_list.append(addr.strip())
    if cc_list:
        msg['Cc'] = ", ".join(cc_list)
        recipients.extend(cc_list)

    msg.attach(MIMEText(hydrated_body, 'html'))

    if not escalation_matrix.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="The Escalation Matrix attachment must strictly be a PDF document.")
        
    try:
        matrix_bytes = await escalation_matrix.read()
        matrix_part = MIMEApplication(matrix_bytes)
        matrix_part['Content-Disposition'] = f'attachment; filename="{escalation_matrix.filename}"'
        msg.attach(matrix_part)
    except Exception as esc_err:
        raise HTTPException(status_code=500, detail=f"Failed compiling escalation matrix attachment: {str(esc_err)}")

    try:
        file_bytes = await testing_snap.read()
        snap_part = MIMEApplication(file_bytes)
        snap_part['Content-Disposition'] = f'attachment; filename="{testing_snap.filename}"'
        msg.attach(snap_part)
    except Exception as img_err:
         raise HTTPException(status_code=500, detail=f"Failed compiling network snapshot logs: {str(img_err)}")

    background_tasks.add_task(send_smtp_email_background, msg.as_string(), recipients)
    return {"status": "success", "message": "Database synchronized perfectly. Onboarding welcome pack sent successfully."}

# =========================================================================
# BANDWIDTH ALTERATION MANAGEMENT PIPELINE (UPGRADE / DOWNGRADE)
# =========================================================================

@app.post("/api/tools/send-bandwidth-change-mail")
async def api_send_bandwidth_change_mail(
    background_tasks: BackgroundTasks,
    change_type: str = Form(...),             
    circuit_id: str = Form(...),
    company_name: str = Form(...),
    old_bandwidth_speed: str = Form(...),
    new_bandwidth_speed: str = Form(...),
    effective_date: str = Form(...),          
    customer_email: str = Form(...),          
    cc_emails: str = Form(""),
    user=Depends(get_current_user)
):
    engineer_identity = user.get("full_name", user.get("username", "NOC Specialist"))
    if "|" in engineer_identity:
        engineer_identity = engineer_identity.split("|")[0].strip()

    try:
        parsed_date = datetime.strptime(effective_date.strip(), "%Y-%m-%d")
        formatted_date = parsed_date.strftime("%d %B %Y")
    except Exception:
        formatted_date = effective_date.strip()

    action_title = "Upgradation" if change_type.lower() == "upgrade" else "Downgradation"
    action_verb = "upgraded" if change_type.lower() == "upgrade" else "downgraded"

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        db_query = """
            INSERT INTO customers (circuit_id, customer_name, customer_email)
            VALUES (%s, %s, %s)
            ON CONFLICT (circuit_id) DO UPDATE SET
                customer_name = EXCLUDED.customer_name,
                customer_email = EXCLUDED.customer_email;
        """
        cursor.execute(db_query, (circuit_id.strip(), company_name.strip(), customer_email.strip()))
        conn.commit()
    except Exception as db_err:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database synchronization failed: {str(db_err)}")
    finally:
        cursor.close()
        conn.close()

    try:
        template = templates.get_template("emails/bandwidth_change_mail.html")
        hydrated_body = template.render({
            "action_title": action_title,
            "action_verb": action_verb,
            "circuit_id": circuit_id.strip(),
            "company_name": company_name.strip(),
            "old_bandwidth_speed": old_bandwidth_speed.strip(),
            "new_bandwidth_speed": new_bandwidth_speed.strip(),
            "effective_date": formatted_date,
            "operator_name": engineer_identity
        })
    except Exception as render_err:
        raise HTTPException(status_code=500, detail=f"Failed to compile template placeholders: {str(render_err)}")

    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    
    to_recipients = [addr.strip() for addr in customer_email.split(",") if addr.strip()]
    msg['To'] = ", ".join(to_recipients)
    msg['Subject'] = f"Link Bandwidth {action_title} Confirmation || {company_name.strip()} || {circuit_id.strip()}"
    
    recipients = list(to_recipients)
    cc_list = list(GLOBAL_MANDATORY_CC)
    if cc_emails.strip():
        for addr in cc_emails.split(","):
            if addr.strip():
                cc_list.append(addr.strip())
    if cc_list:
        msg['Cc'] = ", ".join(cc_list)
        recipients.extend(cc_list)

    msg.attach(MIMEText(hydrated_body, 'html'))
    background_tasks.add_task(send_smtp_email_background, msg.as_string(), recipients)
   # --- ADDED LOGGING TRIGGER ---
    log_operational_event("bandwidth_upgrade_logs", circuit_id.strip(), old_bandwidth_speed.strip(), new_bandwidth_speed.strip())
    
    return {"status": "success", "message": f"Bandwidth {action_title} notifications queued cleanly without file attachments."}
# =========================================================================
# LINK TERMINATION MANAGEMENT PIPELINE
# =========================================================================

@app.post("/api/tools/send-termination-mail")
async def api_send_termination_mail(
    background_tasks: BackgroundTasks,
    circuit_id: str = Form(...),
    company_name: str = Form(...),
    termination_date: str = Form(...),        
    customer_email: str = Form(...),          
    cc_emails: str = Form(""),
    user=Depends(get_current_user)
):
    engineer_identity = user.get("full_name", user.get("username", "NOC Specialist"))
    if "|" in engineer_identity:
        engineer_identity = engineer_identity.split("|")[0].strip()

    try:
        parsed_date = datetime.strptime(termination_date.strip(), "%Y-%m-%d")
        formatted_date = parsed_date.strftime("%d %B %Y")
    except Exception:
        formatted_date = termination_date.strip()

    try:
        template = templates.get_template("emails/terminate.html")
        hydrated_body = template.render({
            "CIRCUIT_ID": circuit_id.strip(),
            "CUSTOMER_NAME": company_name.strip(),
            "TERMINATION_DATE": formatted_date,
            "ENGINEER_NAME": engineer_identity
        })
    except Exception as render_err:
        raise HTTPException(status_code=500, detail=f"Failed to find or parse emails/terminate.html: {str(render_err)}")

    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    
    to_recipients = [addr.strip() for addr in customer_email.split(",") if addr.strip()]
    msg['To'] = ", ".join(to_recipients)
    msg['Subject'] = f"Link Termination Notification || {company_name.strip()} || {circuit_id.strip()}"
    
    recipients = list(to_recipients)
    cc_list = list(GLOBAL_MANDATORY_CC)
    if cc_emails.strip():
        for addr in cc_emails.split(","):
            if addr.strip():
                cc_list.append(addr.strip())
    if cc_list:
        msg['Cc'] = ", ".join(cc_list)
        recipients.extend(cc_list)

    msg.attach(MIMEText(hydrated_body, 'html'))
    background_tasks.add_task(send_smtp_email_background, msg.as_string(), recipients)
    
    # --- ADDED LOGGING TRIGGER ---
    log_operational_event("link_termination_logs", circuit_id.strip(), "Termination requested by client", None)
    
    return {"status": "success", "message": "Link termination announcement queued cleanly via background layers."}

@app.get("/api/ticket/details/{id}")
async def get_ticket_details(id: str, user=Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    # Adjust this query to match your actual database schema
    cursor.execute("""
        SELECT t.circuit_id, t.issue_category, t.created_at as timestamp, 
               t.closed_at as closed_timestamp, c.customer_name 
        FROM tickets t 
        JOIN customers c ON t.circuit_id = c.circuit_id 
        WHERE t.ticket_id::text = %s OR t.circuit_id = %s
    """, (id, id))
    data = cursor.fetchone()
    cursor.close(); conn.close()
    
    if not data:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return data

@app.get("/api/circuit/{circuit_id}")
async def get_circuit_details(circuit_id: str, user=Depends(get_current_user)):
    search_term = circuit_id.strip()
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    query = """
        SELECT circuit_id, customer_name, company_name, customer_email, phone_number, address 
        FROM customers 
        WHERE LOWER(circuit_id) LIKE LOWER(%s)
           OR LOWER(customer_name) LIKE LOWER(%s)
           OR LOWER(company_name) LIKE LOWER(%s)
           OR LOWER(customer_email) LIKE LOWER(%s)
           OR phone_number LIKE %s
           OR LOWER(address) LIKE LOWER(%s)
        ORDER BY (LOWER(circuit_id) = LOWER(%s)) DESC
    """
    wildcard_term = f"%{search_term}%"
    cursor.execute(query, (
        wildcard_term, wildcard_term, wildcard_term, 
        wildcard_term, wildcard_term, wildcard_term, search_term
    ))
    circuit_records = cursor.fetchall()
    cursor.close(); conn.close()
    
    if not circuit_records:
        raise HTTPException(status_code=404, detail="No matching customer profile or circuit was found.")
    return circuit_records

# --- REGISTERED CIRCUITS MATRIX DATA VIEW ---
@app.get("/api/circuit/all")
@app.get("/api/circuits/all")
@app.get("/api/circuits")
async def api_get_all_circuits(search: str = "", user=Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        if search:
            term = f"%{search.strip()}%"
            cursor.execute("""
                SELECT circuit_id, customer_name, company_name, customer_email, phone_number, address 
                FROM customers 
                WHERE LOWER(circuit_id) LIKE LOWER(%s)
                   OR LOWER(customer_name) LIKE LOWER(%s)
                   OR LOWER(company_name) LIKE LOWER(%s)
                   OR phone_number LIKE %s
                ORDER BY circuit_id ASC
            """, (term, term, term, term))
        else:
            cursor.execute("""
                SELECT circuit_id, customer_name, company_name, customer_email, phone_number, address 
                FROM customers 
                ORDER BY circuit_id ASC
            """)
        return cursor.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database fetch failure: {str(e)}")
    finally:
        cursor.close(); conn.close()

# --- CONFLICT-FREE CIRCUIT UPSERT ENGINE ---
@app.post("/api/circuit/save")
@app.post("/api/circuit/add")
@app.post("/api/circuits/save")
@app.post("/api/circuits")
async def api_save_circuit(request: Request, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin authorization required.")
    
    content_type = request.headers.get("content-type", "")
    data = {}
    if "application/json" in content_type:
        try: data = await request.json()
        except: pass
    else:
        try:
            form_data = await request.form()
            data = dict(form_data)
        except: pass

    circuit_id = data.get("circuit_id") or data.get("Circuit ID")
    customer_name = data.get("customer_name") or data.get("Customer Name")
    company_name = data.get("company_name") or data.get("Company Name") or ""
    customer_email = data.get("customer_email") or data.get("customer_email_target") or data.get("Customer Email Target") or ""
    phone_number = data.get("phone_number") or data.get("Phone Number") or ""
    address = data.get("address") or data.get("site_address") or data.get("Site / POP Address") or ""

    if not circuit_id or not customer_name:
        raise HTTPException(status_code=400, detail="Circuit ID and Customer Name are mandatory fields.")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = """
            INSERT INTO customers (circuit_id, customer_name, company_name, customer_email, phone_number, address)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (circuit_id) DO UPDATE SET
                customer_name = EXCLUDED.customer_name,
                company_name = EXCLUDED.company_name,
                customer_email = EXCLUDED.customer_email,
                phone_number = EXCLUDED.phone_number,
                address = EXCLUDED.address
        """
        cursor.execute(query, (circuit_id.strip(), customer_name.strip(), company_name.strip(), customer_email.strip(), phone_number.strip(), address.strip()))
        conn.commit()
        return {"status": "success", "message": "Circuit pipeline record synced cleanly."}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database pipeline transactional break: {str(e)}")
    finally:
        cursor.close(); conn.close()

@app.get("/api/admin/users/all")
async def api_get_all_users(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin authorization required.")
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT id, username, full_name, role FROM users ORDER BY id ASC")
    user_records = cursor.fetchall()
    cursor.close(); conn.close()
    return user_records

@app.post("/api/admin/users/update")
async def api_update_user_profile(payload: UserUpdateModel, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin authorization required.")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if payload.password and payload.password.strip():
            new_hash = hash_password(payload.password.strip())
            cursor.execute(
                """UPDATE users 
                   SET username = %s, full_name = %s, role = %s, password_hash = %s 
                   WHERE id = %s""",
                (payload.username.strip().lower(), payload.full_name.strip(), payload.role, new_hash, payload.user_id)
            )
        else:
            cursor.execute(
                """UPDATE users 
                   SET username = %s, full_name = %s, role = %s 
                   WHERE id = %s""",
                (payload.username.strip().lower(), payload.full_name.strip(), payload.role, payload.user_id)
            )
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Database constraint violation: {str(e)}")
    finally:
        cursor.close(); conn.close()

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
        custom_emails = [email.strip() for email in cc_emails.split(",") if email.strip()]
        for c_email in custom_emails:
            if c_email not in recipients_cc:
                recipients_cc.append(c_email)
    msg['Cc'] = ", ".join(recipients_cc)
    msg['Subject'] = f"Welcome to TeleGlobal Communications || Link Delivery Handover - {circuit_id}"
    
    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Welcome to TeleGlobal Communications || Link Delivery Handover</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f7fa;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f4f7fa" style="table-layout:fixed;">
    <tr>
        <td align="center" style="padding:30px 15px;">
            <table class="email-container" width="700" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.08);">
                <tr>
                    <td bgcolor="#0b4d91" align="center" style="padding:35px 25px; text-align:center;">
                        <h2 style="margin:0; color:#ffffff; font-size:24px; font-weight:bold;">Link Delivery Confirmation</h2>
                        <p style="margin:8px 0 0 0; color:#d9e8f5; font-size:14px;">TeleGlobal Communications Pvt. Ltd.</p>
                    </td>
                </tr>
                <tr>
                    <td style="padding:40px 35px; color:#333333; font-size:14px; line-height:24px;">
                        <p><strong>Dear Sir,</strong></p>
                        <p>Thank you for choosing <strong>TeleGlobal Communications Pvt. Ltd.</strong> as your Internet Service Provider.</p>
                        <p>Your <strong>{bandwidth_speed} Internet Leased Line</strong> has been successfully installed, configured, and commissioned.</p>
                        <table width="100%" cellpadding="12" cellspacing="0" border="1" style="border-collapse:collapse; margin-top:25px; border:2px solid #a0aec0;">
                            <thead>
                                <tr><th colspan="2" bgcolor="#0b4d91" style="color:#ffffff; text-align:center;">TECHNICAL COMMISSIONING DETAILS</th></tr>
                            </thead>
                            <tbody>
                                <tr bgcolor="#f7f9fc"><td>Circuit ID</td><td><strong>{circuit_id}</strong></td></tr>
                                <tr><td>Customer Name</td><td>{customer_name}</td></tr>
                                <tr bgcolor="#f7f9fc"><td>Bandwidth Speed</td><td>{bandwidth_speed}</td></tr>
                                <tr><td>Commissioning Date</td><td>{commissioning_date}</td></tr>
                                <tr bgcolor="#f7f9fc"><td>WAN IP Details</td><td>Usable Range: <strong>{usable_ips}</strong> ({wan_ip_details})</td></tr>
                                <tr><td>Default Gateway</td><td>{default_gateway}</td></tr>
                                <tr bgcolor="#f7f9fc"><td>Subnet Mask</td><td>{subnet_mask}</td></tr>
                            </tbody>
                        </table>
                        <p style="margin-top:30px;">Please find the logs and customer escalation matrix attached.</p>
                    </td>
                </tr>
            </table>
        </td>
    </tr>
</table>
</body>
</html>"""
    
    msg.attach(MIMEText(html_template, 'html'))
    
    if testing_snap and testing_snap.filename:
        try:
            snap_bytes = await testing_snap.read()
            if len(snap_bytes) > 0:
                part1 = MIMEBase('application', 'octet-stream')
                part1.set_payload(snap_bytes)
                encoders.encode_base64(part1)
                part1.add_header('Content-Disposition', f'attachment; filename="{testing_snap.filename}"')
                msg.attach(part1)
        except Exception as e:
            print(f"Testing Snap processing error: {str(e)}")

    if escalation_file and escalation_file.filename:
        try:
            esc_bytes = await escalation_file.read()
            if len(esc_bytes) > 0:
                part2 = MIMEBase('application', 'octet-stream')
                part2.set_payload(esc_bytes)
                encoders.encode_base64(part2)
                part2.add_header('Content-Disposition', f'attachment; filename="{escalation_file.filename}"')
                msg.attach(part2)
        except Exception as e:
            print(f"Escalation Matrix File processing error: {str(e)}")

    all_recipients = [customer_email.strip()] + recipients_cc
    background_tasks.add_task(send_smtp_email_background, msg.as_string(), all_recipients)
    return {"status": "success", "message": "Welcome Onboarding Pack with Multi-Logs dispatched successfully."}

@app.post("/api/ticket/raise")
async def process_raise_ticket(
    background_tasks: BackgroundTasks,
    circuit_id: str = Form(...),
    issue_category: str = Form(...),
    root_cause_segment: str = Form(...),
    status: str = Form(...),
    assigned_team: str = Form(...),
    generate_ticket: str = Form("true"),
    cc_emails: str = Form(""),
    attachment: UploadFile = File(None),
    user=Depends(get_current_user)
):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("SELECT * FROM customers WHERE LOWER(TRIM(circuit_id)) = LOWER(%s)", (circuit_id.strip(),))
        customer = cursor.fetchone()
        if not customer:
            raise HTTPException(status_code=400, detail="Cannot log ticket against unverified Circuit.")

        engineer_identity = user["full_name"]
        if "|" in engineer_identity:
            engineer_identity = engineer_identity.split("|")[0].strip()

        if generate_ticket == "true":
            closed_at_timestamp = datetime.now() if status == "Closed" else None
            closed_by_identity = engineer_identity if status == "Closed" else None

            cursor.execute(
                """INSERT INTO tickets (circuit_id, issue_category, root_cause_segment, status, assigned_team, open_by_name, closed_by_name, created_at, closed_at, resolution_minutes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, 0) RETURNING ticket_id, created_at""",
                (circuit_id.strip(), issue_category, root_cause_segment, status, assigned_team, engineer_identity, closed_by_identity, closed_at_timestamp)
            )
            inserted_row = cursor.fetchone()
            ticket_id = inserted_row['ticket_id']
            
            if status == "Closed":
                time_delta = closed_at_timestamp - inserted_row['created_at'].replace(tzinfo=None)
                duration_minutes = max(1, int(time_delta.total_seconds() / 60))
                cursor.execute("UPDATE tickets SET resolution_minutes = %s WHERE ticket_id = %s", (duration_minutes, ticket_id))
                
            conn.commit()
            formatted_ticket_id = f"TCPL{inserted_row['created_at'].strftime('%d%m%y')}{ticket_id:02d}"
        else:
            formatted_ticket_id = f"DIRECT-{datetime.now().strftime('%d%m%y%H%M%S')}"
    except Exception as db_err:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database Logging Error: {str(db_err)}")
    finally:
        cursor.close(); conn.close()

    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = customer['customer_email']
    
    recipients_cc = list(GLOBAL_MANDATORY_CC)
    if cc_emails:
        custom_emails = [email.strip() for email in cc_emails.split(",") if email.strip()]
        for c_email in custom_emails:
            if c_email not in recipients_cc:
                recipients_cc.append(c_email)
                
    msg['Cc'] = ", ".join(recipients_cc)
    msg['Subject'] = f"[NOC Ticket #{formatted_ticket_id}] {issue_category} | Circuit ID: {circuit_id}"
    
    template_file = determine_email_template(issue_category, status)

    try:
        with open(f"/opt/noc-app/templates/emails/{template_file}", "r", encoding="utf-8") as html_file:
            html_template_data = html_file.read()

        resolved_customer_name = customer["customer_name"] if customer else "Valued Client"
        final_body = html_template_data\
            .replace("{customer_name}", str(resolved_customer_name))\
            .replace("{circuit_id}", str(circuit_id))\
            .replace("{{IP_ADDRESS}}", str(circuit_id))\
            .replace("{ticket_id}", str(formatted_ticket_id))\
            .replace("{operator_name}", str(engineer_identity))\
            .replace("{status}", str(status))\
            .replace("{issue_category}", str(issue_category))\
            .replace("{root_cause_segment}", str(root_cause_segment))\
            .replace("{assigned_team}", str(assigned_team))\
            .replace("{remark_note}", "Ticket Initialization.")
        
        msg.attach(MIMEText(final_body, 'html'))
    except Exception as io_err:
        print(f"Fallback text triggered: {str(io_err)}")
        mail_signature = f"Regards,\n{engineer_identity}\nTeleglobal Communications Pvt. Ltd."
        mail_body = (
            f"Dear Operations Team,\n\n"
            f"An active infrastructural incident notice has changed profile state status to [{status}].\n\n"
            f"■ Incident System Ticket Reference: #{formatted_ticket_id}\n"
            f"■ Link Circuit Core Reference: {circuit_id}\n"
            f"■ Core Alarm Event Profile: {issue_category}\n"
            f"■ Fault Topology Path Segment: {root_cause_segment}\n"
            f"■ Assigned Team Work Group: {assigned_team}\n\n"
            f"{mail_signature}"
        )
        msg.attach(MIMEText(mail_body, 'plain'))

    if attachment and attachment.filename:
        try:
            file_bytes = await attachment.read()
            if len(file_bytes) > 0:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(file_bytes)
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{attachment.filename}"')
                msg.attach(part)
        except Exception as attachment_err:
            print(f"Attachment processing bypassed: {str(attachment_err)}")

    all_recipients = [customer['customer_email']] + recipients_cc
    background_tasks.add_task(send_smtp_email_background, msg.as_string(), all_recipients)
    return {"status": "success", "ticket_id": formatted_ticket_id}

@app.post("/api/ticket/update-status")
async def update_ticket_status(payload: dict, background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    ticket_id = payload.get("ticket_id")
    target_status = payload.get("status")
    remark_note = payload.get("remark_note", "")

    clean_remark = remark_note.strip() if remark_note.strip() else "No additional engineering comments provided."

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("SELECT circuit_id, assigned_team, open_by_name, created_at, issue_category FROM tickets WHERE ticket_id = %s", (ticket_id,))
        ticket_meta = cursor.fetchone()
        if not ticket_meta:
            raise HTTPException(status_code=404, detail="Ticket record not found.")

        engineer_identity = user["full_name"]
        if "|" in engineer_identity:
            engineer_identity = engineer_identity.split("|")[0].strip()
        
        if target_status == "Closed":
            closed_at = datetime.now(timezone.utc)
            created_at_tz = ticket_meta['created_at'].replace(tzinfo=timezone.utc)
            time_delta = closed_at - created_at_tz
            duration_minutes = max(1, int(time_delta.total_seconds() / 60))
            cursor.execute(
                """UPDATE tickets SET status = %s, closed_by_name = %s, closed_at = %s, resolution_minutes = %s 
                   WHERE ticket_id = %s""",
                (target_status, engineer_identity, closed_at, duration_minutes, ticket_id)
            )
        else:
            cursor.execute(
                "UPDATE tickets SET status = %s, closed_by_name = NULL, closed_at = NULL, resolution_minutes = 0 WHERE ticket_id = %s",
                (target_status, ticket_id)
            )
            
        cursor.execute("SELECT customer_name, customer_email FROM customers WHERE LOWER(TRIM(circuit_id)) = LOWER(TRIM(%s))", (ticket_meta["circuit_id"],))
        customer_meta = cursor.fetchone()
        conn.commit()
    except Exception as db_err:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database operational failure: {str(db_err)}")
    finally:
        cursor.close(); conn.close()

    template_file = determine_email_template(ticket_meta.get("issue_category"), target_status)

    try:
        with open(f"/opt/noc-app/templates/emails/{template_file}", "r", encoding="utf-8") as html_file:
            html_template_data = html_file.read()
    except Exception as io_err:
        raise HTTPException(status_code=500, detail=f"Failed loading HTML template from file path: {str(io_err)}")

    recipients_cc = list(GLOBAL_MANDATORY_CC)
    formatted_ticket_id = f"TCPL{ticket_meta['created_at'].strftime('%d%m%y')}{ticket_id:02d}"
    resolved_customer_name = customer_meta["customer_name"] if customer_meta else "Valued Client"

    final_html_body = html_template_data\
        .replace("{customer_name}", str(resolved_customer_name))\
        .replace("{circuit_id}", str(ticket_meta["circuit_id"]))\
        .replace("{{IP_ADDRESS}}", str(ticket_meta["circuit_id"]))\
        .replace("{ticket_id}", str(formatted_ticket_id))\
        .replace("{operator_name}", str(engineer_identity))\
        .replace("{status}", str(target_status))\
        .replace("{remark_note}", str(clean_remark))

    email_subject = f"CRITICAL: Internet Link Status Notice [{target_status}] - Circuit ID: {ticket_meta['circuit_id']}"

    if customer_meta and customer_meta.get("customer_email"):
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = customer_meta["customer_email"]
        msg['Cc'] = ", ".join(recipients_cc)
        msg['Subject'] = email_subject
        msg.attach(MIMEText(final_html_body, 'html'))

        all_recipients = [customer_meta["customer_email"]] + recipients_cc
        background_tasks.add_task(send_smtp_email_background, msg.as_string(), all_recipients)
    return {"status": "success"}

@app.get("/api/tickets/recent")
async def read_recent_tickets(limit: int = 10, search: str = "", status: str = "", user=Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    query = """
        SELECT ticket_id, circuit_id, issue_category, status, assigned_team, open_by_name,
               COALESCE(closed_by_name, '--') as closed_by_name, 
               created_at,
               TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI') as timestamp,
               COALESCE(TO_CHAR(closed_at, 'YYYY-MM-DD HH24:MI'), '--') as closed_timestamp,
               resolution_minutes
        FROM tickets WHERE 1=1
    """
    params = []
    if search:
        query += " AND (LOWER(circuit_id) LIKE LOWER(%s) OR LOWER(open_by_name) LIKE LOWER(%s) OR CAST(ticket_id AS TEXT) LIKE %s)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if status:
        query += " AND status = %s"
        params.append(status)
        
    query += " ORDER BY ticket_id DESC LIMIT %s"
    params.append(limit)
    
    cursor.execute(query, tuple(params))
    records = cursor.fetchall()
    cursor.close(); conn.close()
    
    formatted_records = []
    for row in records:
        ticket_date = row['created_at']
        custom_ticket_id = f"TCPL{ticket_date.strftime('%d%m%y')}{row['ticket_id']:02d}"
        
        formatted_records.append({
            "ticket_id": custom_ticket_id,
            "raw_ticket_id": row['ticket_id'],
            "circuit_id": row['circuit_id'],
            "issue_category": row['issue_category'],
            "status": row['status'],
            "assigned_team": row['assigned_team'],
            "open_by_name": row['open_by_name'],
            "closed_by_name": row['closed_by_name'],
            "timestamp": row['timestamp'],
            "closed_timestamp": row['closed_timestamp'],
            "resolution_minutes": row['resolution_minutes']
        })
    return formatted_records

################################################################################################
####################DOWNLOAD_REPORTs_FILES########################################
####################################################################################################

@app.post("/api/reports/download")
async def stream_csv_report_dataset(
    payload: ReportPayload,
    user: dict = Depends(get_current_user)
):
    """ Dynamically executes raw PostgreSQL queries using psycopg2 and streams CSV datasets """
    report_type = payload.report_type
    start_date = payload.start_date
    end_date = payload.end_date
    team = payload.team

    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    
    timestamp_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    computed_filename = f"teleglobal_{report_type}_{timestamp_suffix}.csv"
    
    writer.writerow(["TELEGLOBAL COMMUNICATIONS PVT. LTD."])
    writer.writerow(["NOC AUTOMATION ENGINE - COMPLIANCE EXPORT DATA AUDIT"])
    
    operator_name = user.full_name if hasattr(user, 'full_name') else user.get('full_name', 'System Desk')
    writer.writerow([f"Generated By: {operator_name}", f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([]) 

    try:
        conn = psycopg2.connect(
            dbname="noc_ticketing", 
            user="noc_admin", 
            password="SecureNocPassword2026!", 
            host="localhost"
        )
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as e:
        print(f"Database connection failure during report export: {str(e)}")
        raise HTTPException(status_code=500, detail="Unable to connect to the backend database engine.")

    try:
        if report_type == "tickets":
            writer.writerow(["Ticket ID", "Circuit ID", "Alarm Category", "Assigned Team", "Fault Location Segment", "Status", "Opened By", "Closed By", "Opened Time", "Closed Time", "Duration Log"])
            
            query = "SELECT * FROM tickets WHERE 1=1"
            params = []
            if start_date:
                query += " AND created_at >= %s"
                params.append(f"{start_date} 00:00:00")
            if end_date:
                query += " AND created_at <= %s"
                params.append(f"{end_date} 23:59:59")
            if team and team != "All":
                query += " AND assigned_team = %s"
                params.append(team)
            query += " ORDER BY ticket_id DESC"
            
            cursor.execute(query, tuple(params))
            records = cursor.fetchall()
            
            for item in records:
                res_mins = item.get('resolution_minutes')
                duration = f"{res_mins} Mins" if item.get('status') == 'Closed' and res_mins else 'Active'
                writer.writerow([f"#{item.get('ticket_id')}", item.get('circuit_id', ''), item.get('issue_category', ''), item.get('assigned_team', ''), item.get('root_cause_segment', ''), item.get('status', ''), item.get('open_by_name', ''), item.get('closed_by_name', ''), str(item.get('created_at', '')), str(item.get('closed_at', '') or ''), duration])

        elif report_type == "welcome_links":
            writer.writerow(["Circuit ID", "Customer Name", "Company Name", "Contact Phone / Email", "Site Location Address", "Dispatched Timestamp"])
            
            query = "SELECT c.circuit_id, c.customer_name, c.company_name, c.customer_email, c.address, wl.dispatched_at FROM customers c INNER JOIN welcome_mail_logs wl ON c.circuit_id = wl.circuit_id WHERE 1=1"
            params = []
            if start_date:
                query += " AND wl.dispatched_at >= %s"
                params.append(f"{start_date} 00:00:00")
            if end_date:
                query += " AND wl.dispatched_at <= %s"
                params.append(f"{end_date} 23:59:59")
            query += " ORDER BY wl.dispatched_at DESC"
            
            cursor.execute(query, tuple(params))
            records = cursor.fetchall()
            for item in records:
                writer.writerow([item.get('circuit_id', ''), item.get('customer_name', ''), item.get('company_name', 'Teleglobal Client'), item.get('customer_email', ''), item.get('address', 'NOC Managed Location'), str(item.get('dispatched_at', ''))])

        elif report_type == "bandwidth_changes":
            writer.writerow(["Circuit ID", "Customer Name", "Company Name", "Old Bandwidth", "New Bandwidth", "Upgradation Date"])
            query = "SELECT c.customer_name, c.company_name, bl.circuit_id, bl.old_bandwidth, bl.new_bandwidth, bl.upgraded_at FROM bandwidth_upgrade_logs bl LEFT JOIN customers c ON bl.circuit_id = c.circuit_id WHERE 1=1"
            params = []
            if start_date:
                query += " AND bl.upgraded_at >= %s"
                params.append(f"{start_date} 00:00:00")
            if end_date:
                query += " AND bl.upgraded_at <= %s"
                params.append(f"{end_date} 23:59:59")
            query += " ORDER BY bl.upgraded_at DESC"
            cursor.execute(query, tuple(params))
            records = cursor.fetchall()
            
            if not records:
                fb_query = "SELECT c.customer_name, c.company_name, t.circuit_id, 'Current/Standard' as old_bandwidth, t.root_cause_segment as new_bandwidth, t.created_at as upgraded_at FROM tickets t INNER JOIN customers c ON t.circuit_id = c.circuit_id WHERE t.issue_category ILIKE %s"
                fb_params = ["%bandwidth%"]
                if start_date:
                    fb_query += " AND t.created_at >= %s"
                    fb_params.append(f"{start_date} 00:00:00")
                if end_date:
                    fb_query += " AND t.created_at <= %s"
                    fb_params.append(f"{end_date} 23:59:59")
                fb_query += " ORDER BY t.created_at DESC"
                cursor.execute(fb_query, tuple(fb_params))
                records = cursor.fetchall()
            
            for item in records:
                writer.writerow([item.get('circuit_id'), item.get('customer_name'), item.get('company_name', 'Teleglobal Client'), item.get('old_bandwidth', 'N/A'), item.get('new_bandwidth', 'N/A'), str(item.get('upgraded_at', ''))])

        elif report_type == "link_terminations":
            writer.writerow(["Circuit ID", "Customer Name", "Company Name", "Termination Reason", "Termination Date"])
            query = "SELECT c.customer_name, c.company_name, tl.circuit_id, tl.reason, tl.terminated_at FROM link_termination_logs tl LEFT JOIN customers c ON tl.circuit_id = c.circuit_id WHERE 1=1"
            params = []
            if start_date:
                query += " AND tl.terminated_at >= %s"
                params.append(f"{start_date} 00:00:00")
            if end_date:
                query += " AND tl.terminated_at <= %s"
                params.append(f"{end_date} 23:59:59")
            query += " ORDER BY tl.terminated_at DESC"
            cursor.execute(query, tuple(params))
            records = cursor.fetchall()
            
            if not records:
                fb_query = "SELECT c.customer_name, c.company_name, t.circuit_id, t.root_cause_segment as reason, t.created_at as terminated_at FROM tickets t INNER JOIN customers c ON t.circuit_id = c.circuit_id WHERE (t.issue_category ILIKE %s OR t.issue_category ILIKE %s)"
                fb_params = ["%terminat%", "%decommission%"]
                if start_date:
                    fb_query += " AND t.created_at >= %s"
                    fb_params.append(f"{start_date} 00:00:00")
                if end_date:
                    fb_query += " AND t.created_at <= %s"
                    fb_params.append(f"{end_date} 23:59:59")
                fb_query += " ORDER BY t.created_at DESC"
                cursor.execute(fb_query, tuple(fb_params))
                records = cursor.fetchall()
            
            for item in records:
                writer.writerow([item.get('circuit_id'), item.get('customer_name'), item.get('company_name', 'Teleglobal Client'), item.get('reason', 'Decommission Request Issued'), str(item.get('terminated_at', ''))])
        else:
            raise HTTPException(status_code=400, detail="Requested operational metrics category mapping does not exist.")
    except Exception as err:
        print(f"Execution handling error during query parsing: {str(err)}")
        raise HTTPException(status_code=500, detail=f"Database data extraction fault: {str(err)}")
    finally:
        cursor.close()
        conn.close()

    csv_buffer.seek(0)
    return StreamingResponse(
        iter([csv_buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=\"{computed_filename}\"",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )




import psycopg2

def log_operational_event(table_name, circuit_id, field1, field2):
    """
    Standardized logger to ensure data hits the tables.
    table_name: 'bandwidth_upgrade_logs' or 'link_termination_logs'
    field1: 'old_bandwidth' or 'reason'
    field2: 'new_bandwidth' (None for termination)
    """
    try:
        conn = psycopg2.connect(dbname="noc_ticketing", user="noc_admin", password="SecureNocPassword2026!", host="localhost")
        cur = conn.cursor()
        
        if table_name == "bandwidth_upgrade_logs":
            cur.execute(
                "INSERT INTO bandwidth_upgrade_logs (circuit_id, old_bandwidth, new_bandwidth, upgraded_at) VALUES (%s, %s, %s, CURRENT_TIMESTAMP)",
                (circuit_id, field1, field2)
            )
        elif table_name == "link_termination_logs":
            cur.execute(
                "INSERT INTO link_termination_logs (circuit_id, reason, terminated_at) VALUES (%s, %s, CURRENT_TIMESTAMP)",
                (circuit_id, field1)
            )
        
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Logging error: {e}")
