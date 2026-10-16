from django import template

register = template.Library()


@register.filter
def dictitem(d, key):
    """Look up ``key`` in dict ``d``. Used for e.g. {{ mood_emoji|dictitem:value }}."""
    if d is None:
        return ""
    return d.get(key, "")


@register.filter
def multiply(value, factor):
    try:
        return float(value) * float(factor)
    except (TypeError, ValueError):
        return 0
