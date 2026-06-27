import os
import sys
import pandas as pd
import psycopg2

# Database Connection Context
DB_SETTINGS = {
    "dbname": "noc_ticketing",
    "user": "noc_admin",
    "password": "SecureNocPassword2026!",
    "host": "localhost"
}

EXCEL_FILE_PATH = "/opt/noc-app/circuits_inventory.xlsx"

def import_excel_to_db():
    if not os.path.exists(EXCEL_FILE_PATH):
        print(f"[-] Operational Error: Source spreadsheet not found at {EXCEL_FILE_PATH}")
        sys.exit(1)
        
    print("[+] Reading data file...")
    try:
        # Reads both standard .xlsx and legacy .xls files
        df = pd.read_excel(EXCEL_FILE_PATH)
    except Exception as read_err:
        print(f"[-] Error parsing spreadsheet columns: {str(read_err)}")
        sys.exit(1)

    # Normalize column names to match database targets
    df.columns = df.columns.str.strip().str.lower()
    
    required_columns = ['circuit_id', 'customer_name', 'company_name', 'customer_email', 'phone_number', 'address']
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        print(f"[-] Data Structural Alignment Error. Missing columns: {missing}")
        print(f"Available columns found: {list(df.columns)}")
        sys.exit(1)

    # Convert all values to string data and drop NaN dropouts cleanly
    df = df.fillna("")
    for col in required_columns:
        df[col] = df[col].astype(str).str.strip()

    print(f"[+] Loaded {len(df)} inventory profiles from file. Connecting to database engine...")
    
    try:
        conn = psycopg2.connect(**DB_SETTINGS)
        cursor = conn.cursor()
    except Exception as db_conn_err:
        print(f"[-] Failed to open database execution pipe: {str(db_conn_err)}")
        sys.exit(1)

    success_count = 0
    
    # Bulk upsert query loop logic
    upsert_query = """
        INSERT INTO customers (circuit_id, customer_name, company_name, customer_email, phone_number, address)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (circuit_id) 
        DO UPDATE SET 
            customer_name = EXCLUDED.customer_name,
            company_name = EXCLUDED.company_name,
            customer_email = EXCLUDED.customer_email,
            phone_number = EXCLUDED.phone_number,
            address = EXCLUDED.address;
    """

    print("[+] Beginning safe database upsert transactions...")
    try:
        for idx, row in df.iterrows():
            if not row['circuit_id']:
                continue  # Skip rows with empty unique values
                
            cursor.execute(upsert_query, (
                row['circuit_id'],
                row['customer_name'],
                row['company_name'],
                row['customer_email'],
                row['phone_number'],
                row['address']
            ))
            success_count += 1
            
        conn.commit()
        print(f"[+] Operational Success: {success_count} customer circuits processed/synchronized cleanly.")
    except Exception as transaction_err:
        conn.rollback()
        print(f"[-] Database insertion rolled back due to error: {str(transaction_err)}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    import_excel_to_db()
