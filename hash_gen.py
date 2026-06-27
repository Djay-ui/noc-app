import hashlib

PASSWORD_SALT = "noc_salt_2026"
password_to_hash = "Teleglobal2026!"  # <-- Set your password here

pwd_bytes = password_to_hash.encode('utf-8')
salt_bytes = PASSWORD_SALT.encode('utf-8')

# This matches the 100,000 iterations hash signature required by main.py
dk = hashlib.pbkdf2_hmac('sha256', pwd_bytes, salt_bytes, 100000)

print("\n========================================================")
print("YOUR COMPLIANT PASSWORD HASH FOR POSTGRESQL:")
print("========================================================")
print(dk.hex())
print("========================================================\n")
