from django.shortcuts import render


def index_view(request):
    return render(request, "index.html")


def about_view(request):
    return render(request, "about.html")


def contact_view(request):
    return render(request, "contact.html")


def privacy_view(request):
    return render(request, "privacy.html")


def get_help_view(request):
    from .crisis_lines import CRISIS_LINES, DEFAULT_COUNTRY

    country = request.GET.get("country")
    if not country or country not in CRISIS_LINES:
        if request.user.is_authenticated and getattr(request.user, "country", None) in CRISIS_LINES:
            country = request.user.country
        else:
            country = DEFAULT_COUNTRY

    context = {
        "crisis_lines": CRISIS_LINES,
        "selected_country": country,
        "line": CRISIS_LINES.get(country, CRISIS_LINES[DEFAULT_COUNTRY]),
    }
    return render(request, "get_help.html", context)
