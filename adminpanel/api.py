"""Admin endpoints for the mobile app. Same rules as the web panel (services.py)."""

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from . import services as svc
from .models import AppRating

User = get_user_model()


class IsMindSpaceAdmin(BasePermission):
    message = "Admins only."

    def has_permission(self, request, view):
        return svc.is_admin(request.user)


def _err(e, code=400):
    return Response({"detail": str(e)}, status=code)


# ── for everyone: rate the app ──────────────────────────────────────────

@api_view(["GET", "POST"])
def my_rating_view(request):
    if request.method == "GET":
        r = AppRating.objects.filter(user=request.user).first()
        return Response({"stars": r.stars, "comment": r.comment, "updated_at": r.updated_at} if r else None)
    try:
        stars = int(request.data.get("stars"))
    except (TypeError, ValueError):
        stars = 0
    if not 1 <= stars <= 5:
        return _err("Choose between 1 and 5 stars.")
    comment = (request.data.get("comment") or "").strip()[:1000]
    platform = (request.data.get("platform") or "")[:16]
    r, _ = AppRating.objects.update_or_create(
        user=request.user, defaults={"stars": stars, "comment": comment, "platform": platform}
    )
    return Response({"stars": r.stars, "comment": r.comment, "updated_at": r.updated_at}, status=201)


# ── admins only ─────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsMindSpaceAdmin])
def stats_view(request):
    return Response(svc.dashboard_stats())


@api_view(["GET"])
@permission_classes([IsMindSpaceAdmin])
def users_view(request):
    try:
        offset = max(0, int(request.query_params.get("offset", 0)))
    except ValueError:
        offset = 0
    total, users = svc.search_users(
        request.query_params.get("q", ""), request.query_params.get("status", "all"), limit=30, offset=offset
    )
    return Response({"total": total, "results": [svc.user_summary(u) for u in users]})


@api_view(["GET"])
@permission_classes([IsMindSpaceAdmin])
def user_detail_view(request, pk):
    return Response(svc.user_detail(get_object_or_404(User, pk=pk)))


@api_view(["POST"])
@permission_classes([IsMindSpaceAdmin])
def user_action_view(request, pk, action):
    target = get_object_or_404(User, pk=pk)
    try:
        if action == "suspend":
            svc.suspend_user(request.user, target)
        elif action == "reactivate":
            svc.reactivate_user(request.user, target)
        elif action == "delete":
            email = svc.delete_user(request.user, target, request.data.get("confirm_email"))
            return Response({"detail": f"{email} was permanently deleted."})
        elif action == "make-admin":
            svc.add_admin(request.user, target.email)
        elif action == "remove-admin":
            svc.remove_admin(request.user, target)
        else:
            return _err("Unknown action.", 404)
    except svc.AdminError as e:
        return _err(e)
    return Response(svc.user_detail(target))


@api_view(["GET", "POST"])
@permission_classes([IsMindSpaceAdmin])
def admins_view(request):
    if request.method == "POST":
        try:
            svc.add_admin(request.user, request.data.get("email"))
        except svc.AdminError as e:
            return _err(e)
    return Response([svc.user_summary(u) for u in svc.list_admins()])


@api_view(["GET"])
@permission_classes([IsMindSpaceAdmin])
def ratings_view(request):
    return Response(
        {
            "summary": svc.ratings_summary(),
            "recent": svc.recent_ratings(only_with_comments=request.query_params.get("comments") == "1"),
        }
    )


@api_view(["GET"])
@permission_classes([IsMindSpaceAdmin])
def audit_view(request):
    return Response(svc.audit_log())



# ── reports ─────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsMindSpaceAdmin])
def report_preview_view(request, kind):
    """Headline numbers for the app, so admins see a summary before downloading."""
    from . import reports

    try:
        s, e = reports.parse_period(request.query_params.get("start"), request.query_params.get("end"), request.query_params.get("preset"))
        data = reports.build(kind, s, e)
    except reports.ReportError as err:
        return _err(err)
    return Response({"kind": kind, "title": reports.KINDS[kind], "start": s, "end": e,
                     "kpis": [{"label": k, "value": v} for k, v in data["kpis"]], "rows": len(data["table"]["rows"])})


@api_view(["GET"])
@permission_classes([IsMindSpaceAdmin])
def report_file_view(request, kind, fmt):
    from . import reports

    if kind not in reports.KINDS:
        return _err("Unknown report.", 404)
    try:
        return reports.response(request, kind, fmt)
    except reports.ReportError as err:
        return _err(err)
