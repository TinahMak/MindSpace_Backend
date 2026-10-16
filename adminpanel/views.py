from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import services as svc

User = get_user_model()


def admin_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not svc.is_admin(request.user):
            return render(request, "adminpanel/forbidden.html", status=403)
        return view(request, *args, **kwargs)

    return wrapper


@admin_required
def dashboard(request):
    return render(
        request,
        "adminpanel/dashboard.html",
        {
            "nav": "dashboard",
            "stats": svc.dashboard_stats(),
            "ratings": svc.ratings_summary(),
            "recent": svc.recent_ratings(limit=5, only_with_comments=True),
            "audit": svc.audit_log(limit=8),
        },
    )


@admin_required
def users(request):
    q = request.GET.get("q", "")
    status = request.GET.get("status", "all")
    _, all_users = svc.search_users(q, status, limit=100000)
    page = Paginator(all_users, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "adminpanel/users.html",
        {"nav": "users", "page": page, "q": q, "status": status, "rows": [svc.user_summary(u) for u in page]},
    )


@admin_required
def user_detail(request, pk):
    target = get_object_or_404(User, pk=pk)
    return render(request, "adminpanel/user_detail.html", {"nav": "users", "u": svc.user_detail(target)})


@admin_required
@require_POST
def user_action(request, pk, action):
    target = get_object_or_404(User, pk=pk)
    try:
        if action == "suspend":
            svc.suspend_user(request.user, target)
            messages.success(request, f"{target.email} has been suspended and signed out.")
        elif action == "reactivate":
            svc.reactivate_user(request.user, target)
            messages.success(request, f"{target.email} has been reactivated.")
        elif action == "make-admin":
            svc.add_admin(request.user, target.email)
            messages.success(request, f"{target.email} is now an admin.")
        elif action == "remove-admin":
            svc.remove_admin(request.user, target)
            messages.success(request, f"{target.email} is no longer an admin.")
        elif action == "delete":
            email = svc.delete_user(request.user, target, request.POST.get("confirm_email"))
            messages.success(request, f"{email} and all their data were permanently deleted.")
            return redirect("adminpanel:users")
    except svc.AdminError as e:
        messages.error(request, str(e))
    return redirect("adminpanel:user_detail", pk=pk)


@admin_required
def admins(request):
    if request.method == "POST":
        try:
            t = svc.add_admin(request.user, request.POST.get("email"))
            messages.success(request, f"{t.email} is now an admin.")
        except svc.AdminError as e:
            messages.error(request, str(e))
        return redirect("adminpanel:admins")
    return render(
        request, "adminpanel/admins.html", {"nav": "admins", "rows": [svc.user_summary(u) for u in svc.list_admins()]}
    )


@admin_required
def ratings(request):
    only = request.GET.get("comments") == "1"
    summary = svc.ratings_summary()
    top = max([d["count"] for d in summary["distribution"]] + [1])
    return render(
        request,
        "adminpanel/ratings.html",
        {"nav": "ratings", "s": summary, "top": top, "only": only, "rows": svc.recent_ratings(limit=100, only_with_comments=only)},
    )


@admin_required
def audit(request):
    return render(request, "adminpanel/audit.html", {"nav": "audit", "rows": svc.audit_log(limit=300)})


# ── professionals ───────────────────────────────────────────────────────

@admin_required
def professionals(request):
    from professionals.models import ProfessionalProfile
    from professionals.services import profile_dict

    status = request.GET.get("status", "pending")
    q = request.GET.get("q", "").strip()
    qs = ProfessionalProfile.objects.select_related("user")
    if status != "all":
        qs = qs.filter(status=status)
    if q:
        from django.db.models import Q

        qs = qs.filter(Q(user__email__icontains=q) | Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q)
                       | Q(registration_number__icontains=q) | Q(city__icontains=q))
    counts = {s: ProfessionalProfile.objects.filter(status=s).count() for s, _ in ProfessionalProfile.STATUS_CHOICES}
    return render(request, "adminpanel/professionals.html", {
        "nav": "pros", "status": status, "q": q, "counts": counts,
        "tabs": [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("suspended", "Suspended"), ("all", "All")],
        "rows": [profile_dict(p, include_docs=False) for p in qs[:200]],
    })


@admin_required
def professional_detail(request, pk):
    from professionals.models import ProfessionalProfile
    from professionals.services import SPECIALTIES, profile_dict

    p = get_object_or_404(ProfessionalProfile, pk=pk)
    d = profile_dict(p)
    labels = dict(SPECIALTIES)
    d["specialty_labels"] = [labels.get(s, s) for s in d["specialties"]]
    return render(request, "adminpanel/professional_detail.html", {"nav": "pros", "p": d})


@admin_required
@require_POST
def professional_action(request, pk, action):
    from professionals import services as psvc
    from professionals.models import ProfessionalProfile

    p = get_object_or_404(ProfessionalProfile, pk=pk)
    try:
        psvc.decide(request.user, p, action, request.POST.get("reason", ""))
        messages.success(request, {"approve": "Approved.", "reject": "Rejected. They've been told the reason.",
                                   "suspend": "Suspended.", "reinstate": "Reinstated."}.get(action, "Done."))
    except psvc.ProError as e:
        messages.error(request, str(e))
    return redirect("adminpanel:professional_detail", pk=pk)


@admin_required
def professional_document(request, doc_pk):
    from django.http import FileResponse

    from professionals.models import ProfessionalDocument

    doc = get_object_or_404(ProfessionalDocument, pk=doc_pk)
    resp = FileResponse(doc.file.open("rb"), content_type=doc.content_type)
    resp["Content-Disposition"] = f'inline; filename="{doc.original_name}"'
    resp["Cache-Control"] = "private, no-store"
    return resp


@admin_required
def professional_add(request):
    from professionals import services as psvc

    form = {}
    if request.method == "POST":
        form = request.POST.dict()
        data = request.POST.dict()
        data["specialties"] = request.POST.getlist("specialties")
        data["languages"] = request.POST.getlist("languages")
        for k in ("offers_in_person", "offers_online", "accepts_medical_aid"):
            data[k] = k in request.POST
        try:
            p = psvc.create_professional(
                email=data.get("email"), first_name=data.get("first_name", ""), last_name=data.get("last_name", ""),
                profile_data=data, admin=request.user,
            )
            sent = psvc.send_set_password_email(request, p.user)
            messages.success(request, f"{p.display_name} was added and approved. "
                             + ("A 'set your password' email was sent." if sent else
                                "The 'set your password' email couldn't be sent; ask them to use Forgot password."))
            return redirect("adminpanel:professional_detail", pk=p.pk)
        except psvc.ProError as e:
            messages.error(request, str(e))
        form["specialties"] = request.POST.getlist("specialties")
        form["languages"] = request.POST.getlist("languages")
    return render(request, "adminpanel/professional_add.html", {"nav": "pros", "m": psvc.meta(), "f": form})



# ── reports ─────────────────────────────────────────────────────────────

@admin_required
def reports_page(request):
    from . import reports

    kind = request.GET.get("kind", "users")
    if kind not in reports.KINDS:
        kind = "users"
    preset = request.GET.get("preset", "30")
    start, end = request.GET.get("start", ""), request.GET.get("end", "")
    ctx = {"nav": "reports", "kinds": reports.KINDS.items(), "kind": kind, "preset": preset, "start": start, "end": end}
    try:
        s, e = reports.parse_period(start, end, None if preset == "custom" else preset)
        data = reports.build(kind, s, e)
        ctx.update(s=s, e=e, kpis=data["kpis"], rows=len(data["table"]["rows"]),
                   query=f"preset={'' if preset == 'custom' else preset}&start={s:%Y-%m-%d}&end={e:%Y-%m-%d}")
    except reports.ReportError as err:
        ctx["error"] = str(err)
    return render(request, "adminpanel/reports.html", ctx)


@admin_required
def report_file(request, kind, fmt):
    from . import reports

    if kind not in reports.KINDS or fmt not in ("pdf", "csv"):
        return redirect("adminpanel:reports")
    try:
        return reports.response(request, kind, fmt)
    except reports.ReportError as err:
        messages.error(request, str(err))
        return redirect("adminpanel:reports")
