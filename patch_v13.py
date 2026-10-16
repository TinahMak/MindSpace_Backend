"""
Update v13: professional onboarding (psychologists, psychiatrists, GPs,
registered counsellors, social workers, therapists) with admin approval.
Safe to run twice.

    python patch_v13.py
    python manage.py migrate
"""

from pathlib import Path

BASE = Path(__file__).resolve().parent
MARK = "# ── v13 professionals (added by patch_v13.py) ──"
BLOCK = f'''

{MARK}
if "professionals" not in INSTALLED_APPS:
    INSTALLED_APPS = list(INSTALLED_APPS) + ["professionals"]
# Qualification documents can be up to 10 MB.
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
'''
p = BASE / "mindspace" / "settings.py"
text = p.read_text(encoding="utf-8")
if MARK in text:
    print("already patched: mindspace/settings.py")
else:
    p.write_text(text.rstrip() + "\n" + BLOCK, encoding="utf-8")
    print("patched: mindspace/settings.py")
print("\nNext: python manage.py migrate")
