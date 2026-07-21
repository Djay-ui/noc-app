import psycopg2
from psycopg2 import sql

# Database Connection Credentials
DB_CONFIG = {
    "dbname": "noc_ticketing",
    "user": "noc_admin",
    "password": "SecureNocPassword2026!",
    "host": "localhost",
    "port": 5432
}

def print_separator(title):
    print("\n" + "=" * 70)
    print(f" {title} ")
    print("=" * 70)

def inspect_database():
    try:
        # Establish connection
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print(" Successfully connected to PostgreSQL database: 'noc_ticketing'")

        # 1. PostgreSQL Version Info
        print_separator("DATABASE SYSTEM INFO")
        cursor.execute("SELECT version();")
        db_version = cursor.fetchone()[0]
        print(f"Server Version:\n{db_version}\n")

        # Get total database size
        cursor.execute("SELECT pg_size_pretty(pg_database_size('noc_ticketing'));")
        db_size = cursor.fetchone()[0]
        print(f"Total Database Size: {db_size}")

        # 2. Get All Tables in Public Schema
        print_separator("TABLES OVERVIEW")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        tables = [row[0] for row in cursor.fetchall()]

        if not tables:
            print("No public tables found in this database.")
            return

        print(f"Found {len(tables)} table(s): {', '.join(tables)}")

        # 3. Inspect Each Table Structure
        for table in tables:
            print_separator(f"TABLE: {table}")

            # Get Row Count
            query_count = sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
            cursor.execute(query_count)
            row_count = cursor.fetchone()[0]
            print(f"Total Rows: {row_count}\n")

            # Get Column Details
            cursor.execute("""
                SELECT 
                    column_name, 
                    data_type, 
                    character_maximum_length, 
                    is_nullable, 
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position;
            """, (table,))
            columns = cursor.fetchall()

            print("--- Columns Structure ---")
            print(f"{'Column Name':<30} | {'Data Type':<18} | {'Nullable':<10} | {'Default'}")
            print("-" * 75)
            for col in columns:
                col_name, data_type, char_len, nullable, default = col
                type_str = f"{data_type}({char_len})" if char_len else data_type
                default_str = str(default) if default else "None"
                print(f"{col_name:<30} | {type_str:<18} | {nullable:<10} | {default_str}")

            # Get Primary Keys & Indexes
            cursor.execute("""
                SELECT
                    i.relname AS index_name,
                    a.attname AS column_name,
                    idx.indisprimary AS is_primary
                FROM pg_class t
                JOIN pg_index idx ON t.oid = idx.indrelid
                JOIN pg_class i ON i.oid = idx.indexrelid
                JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(idx.indkey)
                WHERE t.relname = %s;
            """, (table,))
            indexes = cursor.fetchall()

            if indexes:
                print("\n--- Indexes & Keys ---")
                for idx in indexes:
                    idx_name, col_name, is_pk = idx
                    key_type = "PRIMARY KEY" if is_pk else "INDEX"
                    print(f"• [{key_type}] {idx_name} on column: ({col_name})")

            # Preview Data (Top 3 Rows)
            if row_count > 0:
                print("\n--- Data Preview (First 3 Rows) ---")
                query_preview = sql.SQL("SELECT * FROM {} LIMIT 3;").format(sql.Identifier(table))
                cursor.execute(query_preview)
                sample_rows = cursor.fetchall()
                
                col_names = [desc[0] for desc in cursor.description]
                print(" | ".join(col_names))
                print("-" * 75)
                for row in sample_rows:
                    print(row)

        cursor.close()
        conn.close()
        print_separator("INSPECTION COMPLETE")

    except psycopg2.Error as e:
        print(f"\n[Error] Database connection or query failed:\n{e}")

if __name__ == "__main__":
    inspect_database()
