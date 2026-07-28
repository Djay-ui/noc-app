import os
import sys
import re
import pandas as pd
import psycopg2

# Database Connection Settings
DB_SETTINGS = {
    "dbname": "noc_ticketing",
    "user": "noc_admin",
    "password": "SecureNocPassword2026!",
    "host": "localhost"
}

EXCEL_FILE_PATH = "/opt/noc-app/fiber_db.xlsx"

def clean_and_parse_excel(file_path):
    """Parses Excel file safely regardless of NaN formatting and maps to DB table."""
    # Read raw Excel file and convert NaN values directly to empty strings
    df_raw = pd.read_excel(file_path)
    df_raw = df_raw.fillna("").astype(str)

    # Normalize column names
    cols = {str(c).strip().lower(): c for c in df_raw.columns}

    # Find columns dynamically
    path_col = next((cols[c] for c in cols if 'path' in c), None)
    vendor_col = next((cols[c] for c in cols if 'vendor' in c and 'fiber' not in c), None)
    pvkl_col = next((cols[c] for c in cols if 'pvkl' in c), None)
    contact_col = next((cols[c] for c in cols if 'contact' in c), None)
    extra_col = cols.get('unnamed: 4')
    dist_col = next((cols[c] for c in cols if 'distance' in c), None)

    email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
    records = []

    for _, row in df_raw.iterrows():
        path_val = str(row[path_col]).strip() if path_col else ""
        vendor_val = str(row[vendor_col]).strip() if vendor_col else ""
        pvkl_val = str(row[pvkl_col]).strip() if pvkl_col else ""
        contact_val = str(row[contact_col]).strip() if contact_col else ""
        extra_val = str(row[extra_col]).strip() if extra_col else ""
        dist_val = str(row[dist_col]).strip() if dist_col else ""

        # Remove string literal 'nan' if left over
        vals = [v if v.lower() != 'nan' else '' for v in [path_val, vendor_val, pvkl_val, contact_val, extra_val, dist_val]]
        path_val, vendor_val, pvkl_val, contact_val, extra_val, dist_val = vals

        # Skip rows with no content across all target fields
        if not any([path_val, vendor_val, pvkl_val, contact_val, extra_val, dist_val]):
            continue

        # Format Fiber Name
        fiber_name = path_val if path_val else (f"PVKL-{pvkl_val}" if pvkl_val else "Fiber Route Entry")
        fiber_vendor = vendor_val if vendor_val else "N/A"

        # Extract Emails and clean Contact Info
        combined_text = " / ".join([c for c in [contact_val, extra_val] if c])
        emails = email_pattern.findall(combined_text)
        email_address = ", ".join(list(set(emails)))

        clean_contacts = combined_text
        for em in emails:
            clean_contacts = clean_contacts.replace(em, "")
        clean_contacts = re.sub(r'\s+', ' ', clean_contacts).strip(" /;,|")

        # Format Route Details
        route_details = f"Path: {path_val}" if path_val else fiber_name
        if dist_val:
            route_details += f" | Distance: {dist_val}"

        records.append({
            "fiber_name": fiber_name,
            "fiber_vendor": fiber_vendor,
            "contact_numbers": clean_contacts,
            "email_address": email_address,
            "route_details": route_details
        })

    return pd.DataFrame(records)

def import_fiber_excel_to_db():
    if not os.path.exists(EXCEL_FILE_PATH):
        print(f"[-] Operational Error: Source spreadsheet not found at {EXCEL_FILE_PATH}")
        sys.exit(1)

    print("[+] Reading and cleaning Fiber DB file...")
    try:
        df = clean_and_parse_excel(EXCEL_FILE_PATH)
    except Exception as read_err:
        print(f"[-] Error parsing fiber spreadsheet: {str(read_err)}")
        sys.exit(1)

    print(f"[+] Loaded {len(df)} cleaned fiber route records. Connecting to database engine...")

    try:
        conn = psycopg2.connect(**DB_SETTINGS)
        cursor = conn.cursor()
    except Exception as db_conn_err:
        print(f"[-] Failed to open database execution pipe: {str(db_conn_err)}")
        sys.exit(1)

    # Optional: Clear old/empty records if re-importing
    cursor.execute("TRUNCATE TABLE fiber_db RESTART IDENTITY;")

    insert_query = """
        INSERT INTO fiber_db 
            (fiber_name, fiber_vendor, contact_numbers, email_address, route_details)
        VALUES (%s, %s, %s, %s, %s);
    """

    print("[+] Beginning safe database insertions...")
    try:
        success_count = 0
        for idx, row in df.iterrows():
            cursor.execute(insert_query, (
                row['fiber_name'],
                row['fiber_vendor'],
                row['contact_numbers'],
                row['email_address'],
                row['route_details']
            ))
            success_count += 1

        conn.commit()
        print(f"[+] Operational Success: {success_count} fiber route records processed/synchronized cleanly.")
    except Exception as transaction_err:
        conn.rollback()
        print(f"[-] Database insertion rolled back due to error: {str(transaction_err)}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    import_fiber_excel_to_db()
