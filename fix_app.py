import sys
import ast

def inspect_and_fix(file_path):
    print(f"🔍 Checking {file_path} for syntax and indentation errors...\n")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Step 1: Try parsing AST to pinpoint exact line number
    try:
        ast.parse("".join(lines), filename=file_path)
        print("✅ No syntax or indentation errors found! The code structure is valid.")
        return
    except IndentationError as e:
        print(f"❌ IndentationError detected at Line {e.lineno}, Column {e.offset}:")
        print(f"   Message: {e.msg}\n")
        
        # Display surrounding context
        start = max(0, e.lineno - 6)
        end = min(len(lines), e.lineno + 5)
        
        print("--- CODE CONTEXT ---")
        for idx in range(start, end):
            line_num = idx + 1
            marker = "➡️ " if line_num == e.lineno else "   "
            print(f"{marker}{line_num:4d} | {repr(lines[idx])}")
        print("--------------------\n")
        
    except SyntaxError as e:
        print(f"❌ SyntaxError at Line {e.lineno}: {e.msg}")
        return

if __name__ == "__main__":
    inspect_and_fix("main.py")
