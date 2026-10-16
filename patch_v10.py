"""
One-time setup for update v10 (mobile API). Safe to run more than once.

It appends a clearly marked block to mindspace/settings.py and
mindspace/urls.py. It does not change or remove any existing line.

    python patch_v10.py
"""

from pathlib import Path

BASE = Path(__file__).resolve().parent
MARK = "# ── v10 mobile API (added by patch_v10.py) ──"

SETTINGS_BLOCK = f'''

{MARK}
INSTALLED_APPS = list(INSTALLED_APPS) + [
    app for app in ("rest_framework", "rest_framework.authtoken", "api")
    if app not in INSTALLED_APPS
]

REST_FRAMEWORK = {{
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}}

# Links inside emails sent from the app (verify email, reset password).
# Set SITE_URL in .env once the site is deployed, e.g. https://mindspace.app
SITE_URL = os.environ.get("SITE_URL", "")

# During development your phone reaches Django through your computer's
# Wi-Fi IP address (for example 192.168.1.20), so allow any host while
# DEBUG is on. Keep an explicit list in production.
if DEBUG:
    ALLOWED_HOSTS = ["*"]
'''

URLS_BLOCK = f'''

{MARK}
from django.urls import include as _v10_include, path as _v10_path  # noqa: E402

urlpatterns += [_v10_path("api/v1/", _v10_include("api.urls"))]
'''


def patch(path, block, needs_os=False):
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"already patched: {path.relative_to(BASE)}")
        return
    if needs_os and "import os" not in text:
        block = "\nimport os" + block
    path.write_text(text.rstrip() + "\n" + block, encoding="utf-8")
    print(f"patched: {path.relative_to(BASE)}")


patch(BASE / "mindspace" / "settings.py", SETTINGS_BLOCK, needs_os=True)
patch(BASE / "mindspace" / "urls.py", URLS_BLOCK)

req = BASE / "requirements.txt"
if req.exists():
    lines = req.read_text(encoding="utf-8").splitlines()
    if not any(l.lower().startswith("djangorestframework") for l in lines):
        lines.append("djangorestframework>=3.15")
        req.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("added djangorestframework to requirements.txt")
    else:
        print("requirements.txt already has djangorestframework")
else:
    req.write_text("djangorestframework>=3.15\n", encoding="utf-8")
    print("created requirements.txt with djangorestframework")

print("\nDone. Next: pip install -r requirements.txt && python manage.py migrate")
