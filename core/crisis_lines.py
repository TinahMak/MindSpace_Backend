"""
Crisis line numbers, verified against each organization's own site.
Kept intentionally short — a handful of countries we're confident about,
plus a link to findahelpline.com (a maintained global directory covering
130+ countries) as the reliable fallback for everyone else. Numbers do
change over time; if you notice one is stale, please update it.
"""

DEFAULT_COUNTRY = "ZA"

CRISIS_LINES = {
    "ZA": {
        "name": "SADAG Suicide Crisis Line",
        "number": "0800 567 567",
        "hours": "24/7",
        "extra": "Also reachable by SMS/WhatsApp — see sadag.org",
    },
    "US": {
        "name": "988 Suicide & Crisis Lifeline",
        "number": "988",
        "hours": "24/7",
        "extra": "Call or text 988",
    },
    "GB": {
        "name": "Samaritans",
        "number": "116 123",
        "hours": "24/7",
        "extra": "Free to call",
    },
    "CA": {
        "name": "Talk Suicide Canada",
        "number": "1-833-456-4566",
        "hours": "24/7",
        "extra": "",
    },
    "AU": {
        "name": "Lifeline Australia",
        "number": "13 11 14",
        "hours": "24/7",
        "extra": "",
    },
    "IN": {
        "name": "iCall",
        "number": "9152987821",
        "hours": "Mon–Sat, 10am–8pm IST",
        "extra": "",
    },
}

FALLBACK_DIRECTORY_URL = "https://findahelpline.com"

THERAPIST_DIRECTORIES = [
    {
        "name": "SADAG (South Africa)",
        "url": "https://www.sadag.org/",
        "note": "South Africa's largest mental health support and referral organisation.",
    },
    {
        "name": "Psychology Today Therapist Directory",
        "url": "https://www.psychologytoday.com/us/therapists",
        "note": "Searchable directory of licensed therapists, strongest coverage in the US.",
    },
    {
        "name": "Find A Helpline",
        "url": "https://findahelpline.com",
        "note": "Global directory of crisis lines and support services by country.",
    },
]
