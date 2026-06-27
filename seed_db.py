import hashlib
import psycopg2

PASSWORD_SALT = "noc_salt_2026"

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt_bytes = PASSWORD_SALT.encode('utf-8')
    dk = hashlib.pbkdf2_hmac('sha256', pwd_bytes, salt_bytes, 100000)
    return dk.hex()

def sync_database():
    conn = psycopg2.connect(
        dbname="noc_ticketing", 
        user="noc_admin", 
        password="SecureNocPassword2026!", 
        host="localhost"
    )
    cursor = conn.cursor()
    
    # Clean recreate of users table
    cursor.execute("DROP TABLE IF EXISTS users CASCADE;")
    cursor.execute("""
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(100) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'operator'
        );
    """)
    
    default_hash = hash_password("Teleglobal2026!")
    
    # Dhananjay is seeded directly here with 'admin' authorization role privileges
    roster = [
        ('dhananjay', default_hash, 'Dhananjay Tupe | Admin Desk', 'admin'),
        ('admin', default_hash, 'Backup Administrator Desk', 'admin'),
        ('prashant', default_hash, 'Prashant Marathe | L2 support', 'operator'),
        ('rahul', default_hash, 'Rahul Dev | Senior Engineer', 'operator'),
        ('nihal', default_hash, 'Nihal Kamble | L3 support', 'operator'),
        ('aniruddha', default_hash, 'Aniruddha N | L2 support', 'operator'),
        ('amar', default_hash, 'Amar B | L3 support', 'operator'),
        ('nachiket', default_hash, 'Nachiket B | L1 support', 'operator'),
        ('murugendra', default_hash, 'Murugendra Narwade | Manager', 'operator')
    ]
    
    for username, p_hash, full_name, role in roster:
        cursor.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (%s, %s, %s, %s)",
            (username, p_hash, full_name, role)
        )
        
    conn.commit()
    cursor.close()
    conn.close()
    print("Database synced successfully! 'dhananjay' is now set to Admin.")

if __name__ == "__main__":
    sync_database()
