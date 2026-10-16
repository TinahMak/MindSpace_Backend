"""
Admin reports: Users, Professionals, Consultations and App usage, as
print-ready PDFs (with charts) or CSV.

Privacy: reports contain personal information, so every report is recorded
in the audit log and marked confidential. The Consultations report lists who
booked with whom and when, but NEVER topics, messages or mood summaries.
Usage figures are totals only.
"""

import csv
import io
from collections import Counter, OrderedDict
from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

KINDS = OrderedDict(
    users="Users",
    professionals="Professionals",
    consultations="Consultations",
    usage="App usage",
)
MAX_DAYS = 731


class ReportError(ValueError):
    pass


# ── period ──────────────────────────────────────────────────────────────

def parse_period(start=None, end=None, preset=None):
    today = timezone.localdate()
    if preset in ("7", "30", "90"):
        return today - timedelta(days=int(preset) - 1), today
    if preset == "month":
        return today.replace(day=1), today
    if preset == "last_month":
        last = today.replace(day=1) - timedelta(days=1)
        return last.replace(day=1), last
    try:
        s = date.fromisoformat(start) if start else today - timedelta(days=29)
        e = date.fromisoformat(end) if end else today
    except ValueError:
        raise ReportError("Dates must look like 2026-09-01.")
    if e < s:
        raise ReportError("The end date is before the start date.")
    if e > today:
        e = today
    if (e - s).days + 1 > MAX_DAYS:
        raise ReportError("Choose a period of up to 2 years.")
    return s, e


def _bounds(s, e):
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(s, time.min), tz), timezone.make_aware(datetime.combine(e, time.max), tz)


def _buckets(s, e):
    """Daily for up to 45 days, weekly up to a year, then monthly."""
    days = (e - s).days + 1
    out, cur = [], s
    if days <= 45:
        while cur <= e:
            out.append((cur, cur, cur.strftime("%d %b")))
            cur += timedelta(days=1)
    elif days <= 366:
        while cur <= e:
            end = min(cur + timedelta(days=6), e)
            out.append((cur, end, cur.strftime("%d %b")))
            cur = end + timedelta(days=1)
    else:
        while cur <= e:
            nxt = (cur.replace(day=1) + timedelta(days=32)).replace(day=1)
            end = min(nxt - timedelta(days=1), e)
            out.append((cur, end, cur.strftime("%b %Y")))
            cur = nxt
    return out


def _series(dates, s, e):
    """dates: iterable of date objects -> counts per bucket."""
    buckets = _buckets(s, e)
    counts = Counter(dates)
    return [lbl for _, _, lbl in buckets], [sum(v for d, v in counts.items() if a <= d <= b) for a, b, _ in buckets]


# ── data (plain dicts, shared by PDF, CSV and the app preview) ──────────

def users_data(s, e):
    a, b = _bounds(s, e)
    joined = User.objects.filter(date_joined__range=(a, b)).order_by("date_joined")
    labels, values = _series([timezone.localtime(u.date_joined).date() for u in joined], s, e)
    by_country = Counter(getattr(u, "country", "") or "Unknown" for u in User.objects.all())
    try:
        from professionals.services import role_of
    except Exception:  # professionals app not installed
        def role_of(u):
            return "admin" if (u.is_staff or u.is_superuser) else "user"
    roles = Counter(role_of(u) for u in User.objects.all())
    return {
        "kpis": [
            ("Total accounts", User.objects.count()),
            ("Joined in period", joined.count()),
            ("Active accounts", User.objects.filter(is_active=True).count()),
            ("Suspended", User.objects.filter(is_active=False).count()),
        ],
        "charts": [
            {"title": "New accounts", "labels": labels, "series": [("New accounts", values)], "type": "bar"},
            {"title": "All accounts by country", "labels": list(by_country.keys()), "series": [("Accounts", list(by_country.values()))], "type": "bar"},
            {"title": "All accounts by type", "labels": [r.capitalize() for r in roles], "series": [("Accounts", list(roles.values()))], "type": "bar"},
        ],
        "table": {
            "title": "Accounts that joined in this period",
            "columns": ["Name", "Email", "Country", "Joined", "Last login", "Status"],
            "rows": [
                [f"{u.first_name} {u.last_name}".strip() or "-", u.email, getattr(u, "country", "") or "-",
                 timezone.localtime(u.date_joined).strftime("%d %b %Y"),
                 timezone.localtime(u.last_login).strftime("%d %b %Y") if u.last_login else "never",
                 "Active" if u.is_active else "Suspended"]
                for u in joined
            ],
        },
    }


def professionals_data(s, e):
    from professionals.models import ProfessionalProfile as P

    a, b = _bounds(s, e)
    approved = P.objects.filter(status=P.APPROVED).select_related("user").order_by("profession", "user__last_name")
    by_prof = Counter(p.get_profession_display() for p in approved)
    by_prov = Counter(p.province for p in approved)
    applied = P.objects.filter(created_at__range=(a, b))
    return {
        "kpis": [
            ("Available (approved)", approved.count()),
            ("Pending review", P.objects.filter(status=P.PENDING).count()),
            ("Applied in period", applied.count()),
            ("Offer online sessions", approved.filter(offers_online=True).count()),
        ],
        "charts": [
            {"title": "Available professionals by profession", "labels": list(by_prof.keys()), "series": [("Professionals", list(by_prof.values()))], "type": "bar"},
            {"title": "Available professionals by province", "labels": list(by_prov.keys()), "series": [("Professionals", list(by_prov.values()))], "type": "bar"},
        ],
        "table": {
            "title": "Available professionals (approved, as of today)",
            "columns": ["Name", "Profession", "Registered", "Location", "Sessions", "Fees (R)"],
            "rows": [
                [p.display_name, p.get_profession_display(),
                 f"{p.regulator if p.regulator != 'OTHER' else (p.regulator_other or 'Other')} {p.registration_number}",
                 f"{p.city}, {p.province}",
                 " + ".join(x for x, ok in (("In person", p.offers_in_person), ("Online", p.offers_online)) if ok),
                 f"{p.fee_min or '?'} to {p.fee_max or '?'}" if (p.fee_min or p.fee_max) else "-"]
                for p in approved
            ],
        },
    }


def consultations_data(s, e):
    from professionals.models import ConsultationRequest as CR

    a, b = _bounds(s, e)
    qs = CR.objects.filter(created_at__range=(a, b)).select_related("client", "professional__user").order_by("created_at")
    status = Counter(r.get_status_display() for r in qs)
    accepted = [r for r in qs if r.status == CR.ACCEPTED]
    l1, requested = _series([timezone.localtime(r.created_at).date() for r in qs], s, e)
    _, acc = _series([timezone.localtime(r.created_at).date() for r in accepted], s, e)
    fees = [r.fee for r in accepted if r.fee is not None]
    return {
        "kpis": [
            ("Requests", qs.count()),
            ("Accepted bookings", len(accepted)),
            ("Acceptance rate", f"{round(100 * len(accepted) / qs.count())}%" if qs.count() else "-"),
            ("Average agreed fee", f"R{round(sum(fees) / len(fees))}" if fees else "-"),
        ],
        "charts": [
            {"title": "Requests and accepted bookings", "labels": l1, "series": [("Requests", requested), ("Accepted", acc)], "type": "bar"},
            {"title": "Requests by outcome", "labels": list(status.keys()), "series": [("Requests", list(status.values()))], "type": "bar"},
        ],
        "table": {
            "title": "Consultation requests in this period (no topics, messages or mood details)",
            "columns": ["Requested", "Client", "Professional", "Type", "Status", "Agreed time", "Fee (R)"],
            "rows": [
                [timezone.localtime(r.created_at).strftime("%d %b %Y"),
                 f"{r.client.first_name} {r.client.last_name}".strip() or r.client.email,
                 r.professional.display_name,
                 dict(CR.MODES).get(r.quote_mode or r.mode, r.mode),
                 r.get_status_display(),
                 _fmt_slot(r.chosen_slot) if r.status == CR.ACCEPTED else "-",
                 str(r.fee) if r.fee is not None else "-"]
                for r in qs
            ],
        },
    }


def usage_data(s, e):
    from aichat.models import Message
    from wellness.models import MoodEntry

    a, b = _bounds(s, e)
    moods = MoodEntry.objects.filter(date__range=(s, e))
    msgs = Message.objects.filter(role="user", created_at__range=(a, b))
    mood_days = list(moods.values_list("date", "user_id"))
    msg_days = [(timezone.localtime(c).date(), u) for c, u in msgs.values_list("created_at", "conversation__user_id")]
    active_pairs = set(mood_days) | set(msg_days)
    labels, checkins = _series([d for d, _ in mood_days], s, e)
    _, chats = _series([d for d, _ in msg_days], s, e)
    buckets = _buckets(s, e)
    active = [len({u for d, u in active_pairs if x <= d <= y}) for x, y, _ in buckets]
    avg_by_bucket = []
    for x, y, _ in buckets:
        vals = [m for d, m in moods.values_list("date", "mood") if x <= d <= y]
        avg_by_bucket.append(round(sum(vals) / len(vals), 2) if vals else 0)
    active_users = len({u for _, u in active_pairs})
    total_moods = moods.count()
    return {
        "kpis": [
            ("Active users", active_users),
            ("Mood check-ins", total_moods),
            ("Chat messages sent", msgs.count()),
            ("Check-ins per active user", round(total_moods / active_users, 1) if active_users else "-"),
        ],
        "charts": [
            {"title": "Active users (checked in or chatted)", "labels": labels, "series": [("Active users", active)], "type": "line"},
            {"title": "Mood check-ins and chat messages", "labels": labels, "series": [("Check-ins", checkins), ("Chat messages", chats)], "type": "bar"},
            {"title": "Average mood across all users (1 to 5)", "labels": labels, "series": [("Average mood", avg_by_bucket)], "type": "line", "max": 5},
        ],
        "table": {
            "title": "Totals per period",
            "columns": ["Period", "Active users", "Check-ins", "Chat messages", "Average mood"],
            "rows": [[lbl, active[i], checkins[i], chats[i], avg_by_bucket[i] or "-"] for i, (_, _, lbl) in enumerate(buckets)],
        },
    }


def _fmt_slot(v):
    try:
        return timezone.localtime(datetime.fromisoformat(v)).strftime("%d %b %Y %H:%M")
    except (TypeError, ValueError):
        return v or "-"


BUILDERS = {"users": users_data, "professionals": professionals_data, "consultations": consultations_data, "usage": usage_data}


def build(kind, s, e):
    if kind not in BUILDERS:
        raise ReportError("Unknown report.")
    return BUILDERS[kind](s, e)


def log_report(admin, kind, s, e, fmt):
    from .services import log

    log(admin, "report", None, f"{KINDS[kind]} report ({fmt.upper()}), {s:%d %b %Y} to {e:%d %b %Y}")


# ── CSV ─────────────────────────────────────────────────────────────────

def to_csv(kind, s, e, data):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"MindSpace {KINDS[kind]} report", f"{s:%Y-%m-%d} to {e:%Y-%m-%d}", "CONFIDENTIAL"])
    w.writerow([])
    for k, v in data["kpis"]:
        w.writerow([k, v])
    w.writerow([])
    w.writerow(data["table"]["columns"])
    w.writerows(data["table"]["rows"])
    return buf.getvalue().encode("utf-8-sig")  # BOM so Excel opens accents correctly


# ── PDF ─────────────────────────────────────────────────────────────────

def to_pdf(kind, s, e, data, generated_by=""):
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.legends import Legend
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    SAGE, SAGE_D, CREAM, CHAR, MID, TERRA = (colors.HexColor(x) for x in ("#7A9E87", "#4A6B57", "#F8F4EE", "#2C2C2C", "#6B6B6B", "#C4714A"))
    PAL = [SAGE_D, TERRA, SAGE, colors.HexColor("#B5CEBF")]
    wide = len(data["table"]["columns"]) > 5
    pagesize = landscape(A4) if wide else A4
    W, H = pagesize
    body_w = W - 30 * mm

    ss = {
        "title": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=CHAR),
        "sub": ParagraphStyle("s", fontName="Helvetica", fontSize=10, leading=14, textColor=MID),
        "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=CHAR, spaceBefore=10, spaceAfter=6),
        "cell": ParagraphStyle("c", fontName="Helvetica", fontSize=8.3, leading=10.5, textColor=CHAR, alignment=TA_LEFT),
        "note": ParagraphStyle("n", fontName="Helvetica-Oblique", fontSize=8.5, leading=11, textColor=MID),
    }
    story = [
        Paragraph(f"MindSpace {KINDS[kind]} report", ss["title"]),
        Spacer(1, 3),
        Paragraph(f"{s:%d %B %Y} to {e:%d %B %Y}  ·  generated {timezone.localtime():%d %B %Y %H:%M}"
                  + (f" by {generated_by}" if generated_by else ""), ss["sub"]),
        Spacer(1, 10),
    ]

    # KPI boxes
    kpi = Table(
        [[Paragraph(f'<font size="18" color="#4A6B57"><b>{v}</b></font><br/><font size="8.5" color="#6B6B6B">{k}</font>', ss["cell"]) for k, v in data["kpis"]]],
        colWidths=[body_w / len(data["kpis"])] * len(data["kpis"]),
    )
    kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CREAM), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#EDE8DE")),
        ("INNERGRID", (0, 0), (-1, -1), 2, colors.white), ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story += [kpi, Spacer(1, 8)]

    # charts, two per row when there is room
    def chart(c):
        dw, dh = (body_w / 2 - 6) if wide else body_w, 175
        d = Drawing(dw, dh)
        d.add(String(0, dh - 12, c["title"], fontName="Helvetica-Bold", fontSize=9.5, fillColor=CHAR))
        labels = [str(x)[:20] for x in c["labels"]] or ["No data"]
        series = [list(v) for _, v in c["series"]] or [[0]]
        if not c["labels"]:
            series = [[0] for _ in series]
        many = len(labels) > (6 if wide else 10)
        ch = HorizontalLineChart() if c["type"] == "line" else VerticalBarChart()
        ch.x, ch.y, ch.width, ch.height = 30, 38 if many else 26, dw - 45, dh - (78 if many else 62)
        ch.data = series
        ch.categoryAxis.categoryNames = labels
        ch.categoryAxis.labels.fontSize = 6.5
        ch.categoryAxis.labels.fontName = "Helvetica"
        if many:
            ch.categoryAxis.labels.angle = 45
            ch.categoryAxis.labels.boxAnchor = "ne"
            max_labels = 8 if wide else 12
            step = max(1, -(-len(labels) // max_labels))  # ceiling division
            ch.categoryAxis.categoryNames = [l if i % step == 0 else "" for i, l in enumerate(labels)]
        ch.valueAxis.valueMin = 0
        top = max([max(v) for v in series if v] + [1])
        ch.valueAxis.valueMax = c.get("max") or max(4, int(top * 1.2) + 1)
        ch.valueAxis.labels.fontSize = 7
        ch.valueAxis.labels.fontName = "Helvetica"
        ch.valueAxis.strokeColor = ch.categoryAxis.strokeColor = colors.HexColor("#D4D0CA")
        for i in range(len(series)):
            if c["type"] == "line":
                ch.lines[i].strokeColor = PAL[i % 4]
                ch.lines[i].strokeWidth = 1.8
            else:
                ch.bars[i].fillColor = PAL[i % 4]
                ch.bars[i].strokeColor = None
        d.add(ch)
        if len(c["series"]) > 1:
            lg = Legend()
            lg.x, lg.y = dw - 150, dh - 8
            lg.fontName, lg.fontSize = "Helvetica", 7.5
            lg.columnMaximum, lg.alignment = 1, "right"
            lg.colorNamePairs = [(PAL[i % 4], n) for i, (n, _) in enumerate(c["series"])]
            d.add(lg)
        return d

    charts = [chart(c) for c in data["charts"]]
    if wide:
        for i in range(0, len(charts), 2):
            pair = charts[i : i + 2] + ([""] if len(charts[i : i + 2]) == 1 else [])
            t = Table([pair], colWidths=[body_w / 2] * 2)
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            story += [t, Spacer(1, 6)]
    else:
        for d in charts:
            story += [d, Spacer(1, 6)]

    # table
    tbl = data["table"]
    story.append(Paragraph(tbl["title"], ss["h"]))
    if not tbl["rows"]:
        story.append(Paragraph("Nothing to show for this period.", ss["note"]))
    else:
        rows = [[Paragraph(f"<b>{c}</b>", ss["cell"]) for c in tbl["columns"]]]
        rows += [[Paragraph(str(v).replace("&", "&amp;").replace("<", "&lt;"), ss["cell"]) for v in r] for r in tbl["rows"]]
        t = Table(rows, repeatRows=1, colWidths=[body_w / len(tbl["columns"])] * len(tbl["columns"]))
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDE8DE")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CREAM]),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, SAGE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
    story += [Spacer(1, 10), Paragraph(f"{len(tbl['rows'])} row{'s' if len(tbl['rows']) != 1 else ''}.", ss["note"])]

    def frame(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(SAGE_D)
        canvas.rect(0, H - 8, W, 8, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MID)
        canvas.drawString(15 * mm, 9 * mm, "CONFIDENTIAL: contains personal information. Store securely and share only with authorised people.")
        canvas.drawRightString(W - 15 * mm, 9 * mm, f"MindSpace · page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=pagesize, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"MindSpace {KINDS[kind]} report", author="MindSpace")
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()


def response(request, kind, fmt):
    """Builds the HTTP response for the web panel and the API."""
    from django.http import HttpResponse

    s, e = parse_period(request.GET.get("start"), request.GET.get("end"), request.GET.get("preset"))
    data = build(kind, s, e)
    log_report(request.user, kind, s, e, fmt)
    name = f"mindspace-{kind}-report-{s:%Y%m%d}-{e:%Y%m%d}"
    if fmt == "csv":
        resp = HttpResponse(to_csv(kind, s, e, data), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{name}.csv"'
    else:
        resp = HttpResponse(to_pdf(kind, s, e, data, request.user.email), content_type="application/pdf")
        disp = "attachment" if request.GET.get("download") else "inline"  # inline opens ready to print
        resp["Content-Disposition"] = f'{disp}; filename="{name}.pdf"'
    resp["Cache-Control"] = "private, no-store"
    return resp
