import psycopg2
import psycopg2.extras

# The exact tables your API relies on
TABLES_TO_CHECK = [
    "tickets",
    "customers",
    "welcome_mail_logs",
    "bandwidth_upgrade_logs",
    "link_termination_logs"
]

def check_database():
    print("--- Starting Database Diagnostic ---")
    try:
        conn = psycopg2.connect(
            dbname="noc_ticketing", 
            user="noc_admin", 
            password="SecureNocPassword2026!", 
            host="localhost"
        )
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        print("✅ Successfully connected to the database.\n")
        
        for table in TABLES_TO_CHECK:
            print(f"=========================================")
            print(f"Checking table: {table}")
            print(f"=========================================")
            
            # Check if table exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = %s
                );
            """, (table,))
            
            exists = cursor.fetchone()['exists']
            
            if not exists:
                print(f"❌ Table '{table}' DOES NOT EXIST in the database.\n")
                continue
            
            print(f"✅ Table '{table}' exists.")
            
            # Fetch data (Limiting to 5 rows to keep output readable, remove LIMIT 5 to see all)
            cursor.execute(f"SELECT * FROM {table} LIMIT 5;")
            records = cursor.fetchall()
            
            if not records:
                print(f"⚠️ Table is EMPTY (0 rows).\n")
            else:
                # Print column names based on the first record
                columns = list(records[0].keys())
                print(f"Columns: {', '.join(columns)}")
                print(f"Row count (showing up to 5): {len(records)}")
                for i, row in enumerate(records):
                    print(f"  Row {i+1}: {dict(row)}")
                print("\n")
                
    except Exception as e:
        print(f"❌ Database connection or execution failure: {str(e)}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    check_database()
