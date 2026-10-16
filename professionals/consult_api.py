from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from . import consultations as svc
from .api import IsProfessional
from .models import ConsultationRequest as CR


def _err(e):
    body = {"detail": str(e)}
    if getattr(e, "field", None):
        body[e.field] = [str(e)]
    return Response(body, status=400)


# ── client ──────────────────────────────────────────────────────────────

@api_view(["GET", "POST"])
def client_requests_view(request):
    if request.method == "GET":
        qs = CR.objects.filter(client=request.user).select_related("professional__user")
        return Response([svc.to_dict(r, "client") for r in qs[:100]])
    try:
        r = svc.create_request(request.user, request.data.get("professional_id"), request.data)
    except svc.ConsultError as e:
        return _err(e)
    data = svc.to_dict(r, "client")
    # Crisis language in the message: point to the crisis line first.
    try:
        from aichat.services import detect_crisis

        if detect_crisis(r.message):
            from api.views import _crisis_line_for

            data["crisis_line"] = _crisis_line_for(request.user)
    except Exception:
        pass
    return Response(data, status=201)


@api_view(["GET"])
def client_request_detail_view(request, pk):
    r = CR.objects.filter(pk=pk, client=request.user).select_related("professional__user").first()
    if not r:
        return Response({"detail": "Request not found."}, status=404)
    return Response(svc.to_dict(r, "client"))


@api_view(["POST"])
def client_request_action_view(request, pk, action):
    try:
        if action == "accept":
            r = svc.accept(request.user, pk, request.data.get("slot_index", 0))
        elif action == "decline":
            r = svc.decline(request.user, pk, request.data.get("reason", ""))
        elif action == "cancel":
            r = svc.cancel(request.user, pk)
        else:
            return Response({"detail": "Unknown action."}, status=404)
    except svc.ConsultError as e:
        return _err(e)
    return Response(svc.to_dict(r, "client"))


# ── professional ────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsProfessional])
def pro_requests_view(request):
    qs = CR.objects.filter(professional__user=request.user).select_related("client")
    status = request.query_params.get("status")
    if status == "open":
        qs = qs.filter(status__in=CR.OPEN)
    elif status == "accepted":
        qs = qs.filter(status=CR.ACCEPTED)
    elif status == "closed":
        qs = qs.exclude(status__in=CR.OPEN + (CR.ACCEPTED,))
    items = [svc.to_dict(r, "pro") for r in qs[:100]]
    new = CR.objects.filter(professional__user=request.user, status=CR.REQUESTED).count()
    return Response({"new": new, "results": items})


@api_view(["GET"])
@permission_classes([IsProfessional])
def pro_request_detail_view(request, pk):
    r = CR.objects.filter(pk=pk, professional__user=request.user).select_related("client").first()
    if not r:
        return Response({"detail": "Request not found."}, status=404)
    return Response(svc.to_dict(r, "pro"))


@api_view(["POST"])
@permission_classes([IsProfessional])
def pro_request_action_view(request, pk, action):
    try:
        if action == "quote":
            r = svc.quote(request.user, pk, request.data)
        elif action == "decline":
            r = svc.pro_decline(request.user, pk, request.data.get("reason", ""))
        else:
            return Response({"detail": "Unknown action."}, status=404)
    except svc.ConsultError as e:
        return _err(e)
    return Response(svc.to_dict(r, "pro"))
