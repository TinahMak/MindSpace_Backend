"""
Update v12: admin panel (web at /panel/, plus mobile API) and app ratings.
Appends a marked block to settings.py and urls.py. Safe to run twice.

    python patch_v12.py
    python manage.py migrate
"""

from pathlib import Path

BASE = Path(__file__).resolve().parent
MARK = "# ── v12 admin panel (added by patch_v12.py) ──"

SETTINGS = f'''

{MARK}
if "adminpanel" not in INSTALLED_APPS:
    INSTALLED_APPS = list(INSTALLED_APPS) + ["adminpanel"]
'''

URLS = f'''

{MARK}
from django.urls import include as _v12_include, path as _v12_path  # noqa: E402

urlpatterns += [_v12_path("panel/", _v12_include("adminpanel.urls"))]
'''

for rel, block in (("mindspace/settings.py", SETTINGS), ("mindspace/urls.py", URLS)):
    p = BASE / rel
    text = p.read_text(encoding="utf-8")
    if MARK in text:
        print(f"already patched: {rel}")
    else:
        p.write_text(text.rstrip() + "\n" + block, encoding="utf-8")
        print(f"patched: {rel}")

print("\nNext: python manage.py migrate")
