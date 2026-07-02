import psycopg2

def verify_database_schema():
    try:
        # Using your exact configuration strings
        conn = psycopg2.connect(
            dbname="noc_ticketing", 
            user="noc_admin", 
            password="SecureNocPassword2026!", 
            host="localhost"
        )
        cursor = conn.cursor()
        
        print("\n=========================================")
        print("1. AVAILABLE TABLES IN YOUR DATABASE:")
        print("=========================================")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        for row in cursor.fetchall():
            print(f"🔹 Table found: {row[0]}")
            
        print("\n=========================================")
        print("2. ACTUAL COLUMNS INSIDE THE 'tickets' TABLE:")
        print("=========================================")
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'tickets'
            ORDER BY column_name;
        """)
        for row in cursor.fetchall():
            print(f"🔸 Column: {row[0]:<20} | Type: {row[1]}")
            
        cursor.close()
        conn.close()
        print("\n=========================================\n")

    except Exception as e:
        print(f"\n❌ Connection Failed: {e}\n")

if __name__ == "__main__":
    verify_database_schema()
