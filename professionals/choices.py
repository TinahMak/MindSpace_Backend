"""Fixed lists for professional profiles (South Africa)."""

PROFESSIONS = [
    ("psychologist", "Psychologist"),
    ("psychiatrist", "Psychiatrist"),
    ("general_practitioner", "General practitioner (doctor)"),
    ("registered_counsellor", "Registered counsellor"),
    ("social_worker", "Social worker"),
    ("therapist", "Therapist (other)"),
]

REGULATORS = [
    ("HPCSA", "HPCSA (Health Professions Council of South Africa)"),
    ("SACSSP", "SACSSP (South African Council for Social Service Professions)"),
    ("OTHER", "Other professional body"),
]

# Which body normally registers each profession. "therapist" varies, so it is chosen.
DEFAULT_REGULATOR = {
    "psychologist": "HPCSA",
    "psychiatrist": "HPCSA",
    "general_practitioner": "HPCSA",
    "registered_counsellor": "HPCSA",
    "social_worker": "SACSSP",
}

SPECIALTIES = [
    ("anxiety_stress", "Anxiety and stress"),
    ("low_mood", "Depression and low mood"),
    ("trauma", "Trauma"),
    ("grief", "Grief and loss"),
    ("relationships", "Relationships and family"),
    ("addiction", "Addiction and substance use"),
    ("youth", "Young people and students"),
    ("work", "Work stress and burnout"),
    ("general", "General wellbeing"),
]

LANGUAGES = [
    "English", "Afrikaans", "isiZulu", "isiXhosa", "Sesotho", "Setswana", "Sepedi",
    "Xitsonga", "siSwati", "Tshivenda", "isiNdebele", "South African Sign Language",
]

PROVINCES = [
    "Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo",
    "Mpumalanga", "Northern Cape", "North West", "Western Cape",
]

TITLES = ["Dr", "Mr", "Ms", "Mrs", "Mx", "Prof"]

DOC_KINDS = [
    ("registration", "Registration certificate"),
    ("qualification", "Qualification (degree or diploma)"),
    ("other", "Other supporting document"),
]
