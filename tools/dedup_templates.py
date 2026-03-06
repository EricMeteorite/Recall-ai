"""
One-time script to replace inline api_keys.env templates in 4 scripts
with references to the canonical recall/config_template.env file.
"""
import re
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def replace_ps1_template(filepath, indent):
    """Replace PowerShell here-string template with file read."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern: $defaultConfig = @'....'@  followed by Set-Content line
    # The here-string starts with $defaultConfig = @' and ends with '@
    # Note: PowerShell here-string closing '@ MUST be at column 0
    pattern = re.compile(
        r"^" + re.escape(indent) + r"\$defaultConfig = @'\n"
        r"(.*?\n)"
        r"'@\n"
        r"" + re.escape(indent) + r"Set-Content -Path \$configFile -Value \$defaultConfig -Encoding UTF8",
        re.MULTILINE | re.DOTALL
    )
    
    replacement = (
        f'{indent}$templateFile = Join-Path $ScriptDir "recall\\config_template.env"\n'
        f'{indent}if (Test-Path $templateFile) {{\n'
        f'{indent}    $defaultConfig = Get-Content $templateFile -Raw -Encoding UTF8\n'
        f'{indent}}} else {{\n'
        f'{indent}    Write-Host "  [ERROR] Template file not found: $templateFile" -ForegroundColor Red\n'
        f'{indent}    return\n'
        f'{indent}}}\n'
        f'{indent}Set-Content -Path $configFile -Value $defaultConfig -Encoding UTF8'
    )
    
    match = pattern.search(content)
    if not match:
        print(f"  WARNING: No match found in {filepath}")
        return False
    
    new_content = content[:match.start()] + replacement + content[match.end():]
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"  OK: {filepath}")
    return True


def replace_sh_template(filepath, indent):
    """Replace bash heredoc template with file copy."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern: cat > "$config_file" << 'EOF' ... EOF
    pattern = re.compile(
        r"^(" + re.escape(indent) + r")cat > \"\$config_file\" << 'EOF'\n"
        r"(.*?\n)"
        r"EOF",
        re.MULTILINE | re.DOTALL
    )
    
    replacement = (
        f'{indent}template_file="$SCRIPT_DIR/recall/config_template.env"\n'
        f'{indent}if [ -f "$template_file" ]; then\n'
        f'{indent}    cp "$template_file" "$config_file"\n'
        f'{indent}else\n'
        f'{indent}    print_error "Template file not found: $template_file"\n'
        f'{indent}    exit 1\n'
        f'{indent}fi'
    )
    
    match = pattern.search(content)
    if not match:
        print(f"  WARNING: No match found in {filepath}")
        return False
    
    new_content = content[:match.start()] + replacement + content[match.end():]
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"  OK: {filepath}")
    return True


def main():
    print("=== Deduplicating api_keys.env templates ===\n")
    
    # 1. start.ps1 - indent is 8 spaces
    ok1 = replace_ps1_template(os.path.join(BASE, 'start.ps1'), '        ')
    
    # 2. start.sh - indent is 8 spaces 
    ok2 = replace_sh_template(os.path.join(BASE, 'start.sh'), '        ')
    
    # 3. manage.ps1 - indent is 16 spaces (deeper nesting)
    ok3 = replace_ps1_template(os.path.join(BASE, 'manage.ps1'), '                ')
    
    # 4. manage.sh - indent is 16 spaces
    ok4 = replace_sh_template(os.path.join(BASE, 'manage.sh'), '                ')
    
    print()
    if all([ok1, ok2, ok3, ok4]):
        print("All 4 scripts updated successfully!")
    else:
        print("Some replacements failed - check warnings above.")


if __name__ == '__main__':
    main()
