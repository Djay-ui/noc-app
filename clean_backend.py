import ast
import re

def clean_main_py(file_path="main.py"):
    print(f"[*] Reading {file_path}...")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Remove duplicate lines (e.g., duplicated imports or redundant blank lines)
    lines = content.splitlines()
    cleaned_lines = []
    seen_imports = set()

    print("[*] Filtering duplicate imports and redundant code...")
    for line in lines:
        stripped = line.strip()
        
        # Check for duplicated import statements
        if stripped.startswith("import ") or stripped.startswith("from "):
            if stripped in seen_imports:
                continue  # Skip duplicate import
            seen_imports.add(stripped)
        
        cleaned_lines.append(line)

    new_content = "\n".join(cleaned_lines)

    # 2. Collapse 3 or more consecutive blank lines into a maximum of 2
    new_content = re.sub(r'\n{3,}', '\n\n', new_content)

    # 3. Verify Python Syntax before saving
    try:
        ast.parse(new_content)
        print("[+] Syntax validation successful!")
    except SyntaxError as e:
        print(f"[!] Syntax error detected while cleaning: {e}")
        print("[!] Aborting cleanup to prevent corrupting file.")
        return

    # 4. Save cleaned file
    backup_path = f"{file_path}.bak"
    with open(backup_path, "w", encoding="utf-8") as f_bak:
        f_bak.write(content)
    print(f"[+] Backup saved to {backup_path}")

    with open(file_path, "w", encoding="utf-8") as f_out:
        f_out.write(new_content)
    print(f"[+] Cleaned file successfully written to {file_path}!")

if __name__ == "__main__":
    clean_main_py()
