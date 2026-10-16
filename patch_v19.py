"""
Update v19: self-care tools (journal endpoints and safety plan).
Adds the 'selfcare' app to settings.py. Safe to run twice.

    python patch_v19.py
    python manage.py migrate
"""
from pathlib import Path

MARK = "# ── v19 self-care (added by patch_v19.py) ──"
p = Path(__file__).resolve().parent / "mindspace" / "settings.py"
text = p.read_text(encoding="utf-8")
if MARK in text:
    print("already patched: mindspace/settings.py")
else:
    p.write_text(text.rstrip() + f'''

{MARK}
if "selfcare" not in INSTALLED_APPS:
    INSTALLED_APPS = list(INSTALLED_APPS) + ["selfcare"]
''', encoding="utf-8")
    print("patched: mindspace/settings.py")
print("\\nNext: python manage.py migrate")
