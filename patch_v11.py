"""
Update v11: lets people choose several reasons for joining, plus "Other".

Adds two fields to the User model in accounts/models.py (right after
`focus`), leaving every existing line untouched. Safe to run twice.

    python patch_v11.py
    python manage.py makemigrations accounts
    python manage.py migrate
"""

from pathlib import Path

path = Path(__file__).resolve().parent / "accounts" / "models.py"
text = path.read_text(encoding="utf-8")

if "focus_reasons" in text:
    print("already patched: accounts/models.py")
else:
    lines = text.splitlines()
    idx = next((i for i, l in enumerate(lines) if l.strip().startswith("focus = models.")), None)
    if idx is None:
        raise SystemExit("Could not find the `focus = models...` line in accounts/models.py. Paste the file to Claude.")
    # Follow a field definition that spans several lines, until brackets balance.
    depth, end = 0, idx
    for j in range(idx, len(lines)):
        depth += lines[j].count("(") - lines[j].count(")")
        end = j
        if depth <= 0:
            break
    indent = lines[idx][: len(lines[idx]) - len(lines[idx].lstrip())]
    lines[end + 1 : end + 1] = [
        f"{indent}# v11: several reasons can be chosen; `focus` keeps the first one for the website.",
        f"{indent}focus_reasons = models.JSONField(default=list, blank=True)",
        f"{indent}focus_other = models.CharField(max_length=100, blank=True)",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("patched: accounts/models.py")

print("\nNext: python manage.py makemigrations accounts && python manage.py migrate")
