"""Mobile API for professionals (their own area) and for admins reviewing them."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response

from adminpanel.api import IsMindSpaceAdmin
from adminpanel.services import is_admin

from . import services as svc
from .models import ProfessionalDocument, ProfessionalProfile

User = get_user_model()


class IsProfessional(BasePermission):
    message = "This area is for registered professionals."

    def has_permission(self, request, view):
        return request.user.is_authenticated and hasattr(request.user, "professional")


def _err(e, code=400):
    body = {"detail": str(e)}
    if getattr(e, "field", None):
        body[e.field] = [str(e)]
    return Response(body, status=code)


@api_view(["GET"])
@permission_classes([AllowAny])
def pro_meta_view(request):
    return Response(svc.meta())


@api_view(["POST"])
@permission_classes([AllowAny])
def pro_signup_view(request):
    from api.serializers import UserSerializer
    from api.views import AuthRateThrottle

    # throttle manually so the import stays local
    if not AuthRateThrottle().allow_request(request, None):
        return Response({"detail": "Too many attempts. Wait a minute and try again."}, status=429)
    d = request.data
    if not d.get("terms_accepted"):
        return Response({"terms_accepted": ["You must agree to the terms."], "detail": "You must agree to the terms."}, status=400)
    if not d.get("declaration"):
        return Response(
            {"declaration": ["Please confirm your details are true."], "detail": "Please confirm your details are true."},
            status=400,
        )
    try:
        profile = svc.create_professional(
            email=d.get("email"),
            first_name=d.get("first_name", ""),
            last_name=d.get("last_name", ""),
            password=d.get("password") or "",
            profile_data=d,
        )
    except svc.ProError as e:
        return _err(e)
    user = profile.user
    token, _ = Token.objects.get_or_create(user=user)
    return Response(
        {"token": token.key, "user": UserSerializer(user, context={"request": request}).data,
         "profile": svc.profile_dict(profile)},
        status=201,
    )


@api_view(["GET", "PATCH"])
@permission_classes([IsProfessional])
def pro_me_view(request):
    profile = request.user.professional
    if request.method == "GET":
        return Response(svc.profile_dict(profile))
    if profile.status == ProfessionalProfile.SUSPENDED:
        return Response({"detail": "Your profile is suspended. Contact MindSpace support."}, status=403)
    try:
        with transaction.atomic():
            from api import validators as V

            for f, label in (("first_name", "First name"), ("last_name", "Last name")):
                if f in request.data:
                    try:
                        setattr(request.user, f, V.clean_name(request.data[f], label))
                    except V.InputError as e:
                        raise svc.ProError(str(e), f)
            request.user.save(update_fields=["first_name", "last_name"])
            profile, rereview = svc.update_own_profile(profile, request.data)
    except svc.ProError as e:
        return _err(e)
    data = svc.profile_dict(profile)
    data["sent_for_review"] = rereview
    return Response(data)


@api_view(["POST"])
@permission_classes([IsProfessional])
def pro_resubmit_view(request):
    try:
        svc.resubmit(request.user.professional)
    except svc.ProError as e:
        return _err(e)
    return Response(svc.profile_dict(request.user.professional))


@api_view(["POST"])
@permission_classes([IsProfessional])
@parser_classes([MultiPartParser, FormParser])
def pro_upload_view(request):
    f = request.FILES.get("file")
    if not f:
        return Response({"detail": "Choose a file to upload."}, status=400)
    try:
        svc.add_document(request.user.professional, f, request.data.get("kind", "other"))
    except svc.ProError as e:
        return _err(e)
    return Response(svc.profile_dict(request.user.professional), status=201)


@api_view(["DELETE"])
@permission_classes([IsProfessional])
def pro_document_delete_view(request, pk):
    profile = request.user.professional
    doc = get_object_or_404(ProfessionalDocument, pk=pk, profile=profile)
    try:
        svc.delete_document(profile, doc)
    except svc.ProError as e:
        return _err(e)
    return Response(svc.profile_dict(profile))


@api_view(["GET"])
def document_file_view(request, pk):
    """Private: only the professional who uploaded it, or an admin."""
    doc = get_object_or_404(ProfessionalDocument.objects.select_related("profile"), pk=pk)
    if not (is_admin(request.user) or doc.profile.user_id == request.user.pk):
        raise Http404
    resp = FileResponse(doc.file.open("rb"), content_type=doc.content_type)
    resp["Content-Disposition"] = f'inline; filename="{doc.original_name}"'
    resp["Cache-Control"] = "private, no-store"
    return resp


# ── admin ───────────────────────────────────────────────────────────────

def _admin_list(request):
    status = request.query_params.get("status", "pending")
    q = (request.query_params.get("q") or "").strip()
    qs = ProfessionalProfile.objects.select_related("user")
    if status != "all":
        qs = qs.filter(status=status)
    if q:
        from django.db.models import Q

        qs = qs.filter(
            Q(user__email__icontains=q) | Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q)
            | Q(registration_number__icontains=q) | Q(city__icontains=q)
        )
    counts = {s: ProfessionalProfile.objects.filter(status=s).count() for s, _ in ProfessionalProfile.STATUS_CHOICES}
    return Response({"counts": counts, "results": [svc.profile_dict(p, include_docs=False) for p in qs[:100]]})


@api_view(["GET", "POST"])
@permission_classes([IsMindSpaceAdmin])
def admin_pros_view(request):
    if request.method == "GET":
        return _admin_list(request)
    d = request.data
    try:
        profile = svc.create_professional(
            email=d.get("email"), first_name=d.get("first_name", ""), last_name=d.get("last_name", ""),
            profile_data=d, admin=request.user,
        )
    except svc.ProError as e:
        return _err(e)
    sent = svc.send_set_password_email(request, profile.user)
    data = svc.profile_dict(profile)
    data["set_password_email_sent"] = sent
    return Response(data, status=201)


@api_view(["GET"])
@permission_classes([IsMindSpaceAdmin])
def admin_pro_detail_view(request, pk):
    return Response(svc.profile_dict(get_object_or_404(ProfessionalProfile, pk=pk)))


@api_view(["POST"])
@permission_classes([IsMindSpaceAdmin])
def admin_pro_action_view(request, pk, action):
    profile = get_object_or_404(ProfessionalProfile, pk=pk)
    try:
        svc.decide(request.user, profile, action, request.data.get("reason", ""))
    except svc.ProError as e:
        return _err(e)
    return Response(svc.profile_dict(profile))


# ── clients: find and view approved professionals (Phase 3) ────────────

@api_view(["POST"])
def match_view(request):
    """POST so the client's location stays out of URLs and server logs."""
    from . import matching
    from .choices import LANGUAGES, PROFESSIONS, PROVINCES

    d = request.data
    point = matching.parse_point(d.get("lat"), d.get("lng")) if d.get("lat") is not None else None
    mode = d.get("mode") if d.get("mode") in ("in_person", "online", "any") else "any"
    province = d.get("province") if d.get("province") in PROVINCES else None
    profession = d.get("profession") if d.get("profession") in dict(PROFESSIONS) else None
    language = d.get("language") if d.get("language") in LANGUAGES else None
    results, meta = matching.match(
        request.user, point=point, mode=mode, province=province, profession=profession, language=language
    )
    return Response({"results": results, **meta})


@api_view(["GET"])
def public_profile_view(request, pk):
    from . import matching

    p = get_object_or_404(ProfessionalProfile, pk=pk, status=ProfessionalProfile.APPROVED)
    return Response(matching.public_profile(p))
