import psycopg2
import sys

def verify_noc_schema():
    print("🔄 Initializing structural integrity checks on 'noc_ticketing'...")
    try:
        # Establish connection with the application user credentials
        conn = psycopg2.connect("dbname=noc_ticketing user=noc_admin password=SecureNocPassword2026! host=localhost")
        cursor = conn.cursor()
        
        # Comprehensive list of columns expected in production state
        target_columns = [
            'ticket_id', 'circuit_id', 'issue_category', 'root_cause_segment', 
            'status', 'assigned_team', 'open_by_name', 'closed_by_name', 
            'created_at', 'closed_at', 'resolution_minutes', 
            'priority', 'sla_deadline', 'is_sla_breached'
        ]
        
        missing_fields = []
        for col in target_columns:
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.columns 
                WHERE table_name = 'tickets' AND column_name = %s;
            """, (col,))
            if cursor.fetchone()[0] == 0:
                missing_fields.append(col)
                
        if missing_fields:
            print(f"❌ Schema alignment failed. Missing columns: {missing_fields}")
            sys.exit(1)
            
        print("✅ Database schema checks out completely. Ready for application lifecycle initialization.")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ Database engine error during verification: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    verify_noc_schema()
