"""Update v17: adds the 'phonenumbers' library (country-aware phone checks). Safe to run twice.

    python patch_v17.py
    pip install -r requirements.txt
"""
from pathlib import Path

req = Path(__file__).resolve().parent / "requirements.txt"
lines = req.read_text(encoding="utf-8").splitlines() if req.exists() else []
if any(l.lower().startswith("phonenumbers") for l in lines):
    print("requirements.txt already has phonenumbers")
else:
    lines.append("phonenumbers>=8.13")
    req.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("added phonenumbers to requirements.txt")
print("\nNext: pip install -r requirements.txt")
