"""
Generates a printable/shareable PDF summary of a user's mood check-ins.

This is meant for the PERSON to hand to a therapist or doctor themselves,
if and when they choose to — MindSpace never transmits health data to
anyone automatically. This is a factual log, not a diagnosis.
"""
from datetime import timedelta
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .services import analyze_mood_patterns

SAGE = colors.HexColor("#4a6b57")
CREAM_DARK = colors.HexColor("#ede8de")
CHARCOAL = colors.HexColor("#2c2c2c")
MID_GRAY = colors.HexColor("#6b6b6b")
LIGHT_GRAY = colors.HexColor("#d4d0ca")
CREAM = colors.HexColor("#f8f4ee")


def build_mood_report_pdf(user, days=14) -> bytes:
    from .models import MoodEntry

    cutoff = timezone.localdate() - timedelta(days=days - 1)
    entries = MoodEntry.objects.filter(user=user, date__gte=cutoff).order_by("date", "created_at")
    stats = analyze_mood_patterns(user, days=days)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleSage", parent=styles["Title"], textColor=SAGE)
    small_gray = ParagraphStyle("SmallGray", parent=styles["Normal"], textColor=MID_GRAY, fontSize=9, leading=13)

    elements = [
        Paragraph("MindSpace — Mood Summary Report", title_style),
        Paragraph(f"Prepared for: {user.get_full_name() or user.email}", styles["Normal"]),
        Paragraph(
            f"Period: last {days} days (generated {timezone.localdate():%d %b %Y})",
            styles["Normal"],
        ),
        Spacer(1, 14),
        Paragraph(
            "This report is a factual log of self-reported mood check-ins from the "
            "MindSpace app. It is <b>not</b> a clinical assessment, diagnosis, or "
            "treatment recommendation. It's provided so the person above can share it "
            "with a healthcare professional at their own discretion, to support — not "
            "replace — a real conversation.",
            small_gray,
        ),
        Spacer(1, 16),
        Paragraph("Summary", styles["Heading2"]),
    ]

    for line in [
        f"Total check-ins: {stats['total_entries']}",
        f"Average mood (1=very low, 5=great): {stats['avg_mood'] if stats['avg_mood'] is not None else 'n/a'}",
        f"Share of low/very-low check-ins: {int(stats['low_ratio'] * 100)}%",
        f"Trend: {stats['trend']}",
        f"Most common feelings tagged: {', '.join(stats['top_emotions']) or 'none tagged'}",
    ]:
        elements.append(Paragraph(line, styles["Normal"]))

    elements.append(Spacer(1, 10))
    elements.append(Paragraph("Reflection", styles["Heading3"]))
    elements.append(Paragraph(stats["reflection"], styles["Normal"]))
    elements.append(Spacer(1, 18))

    elements.append(Paragraph("Check-in log", styles["Heading2"]))
    mood_labels = dict(MoodEntry.MOOD_CHOICES)
    table_data = [["Date", "Time", "Mood", "Tags", "Note"]]
    for e in entries:
        note = e.note or ""
        if len(note) > 80:
            note = note[:80] + "…"
        table_data.append(
            [
                e.date.strftime("%d %b %Y"),
                e.created_at.strftime("%H:%M"),
                mood_labels.get(e.mood, str(e.mood)),
                ", ".join(t.title() for t in e.emotions) if e.emotions else "—",
                note or "—",
            ]
        )

    if len(table_data) == 1:
        elements.append(Paragraph("No check-ins recorded in this period.", styles["Normal"]))
    else:
        table = Table(
            table_data,
            colWidths=[0.9 * inch, 0.55 * inch, 0.75 * inch, 1.5 * inch, 2.3 * inch],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), CREAM_DARK),
                    ("TEXTCOLOR", (0, 0), (-1, 0), CHARCOAL),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CREAM]),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        elements.append(table)

    elements.append(Spacer(1, 20))
    elements.append(
        Paragraph(
            "If you are in crisis or thinking about suicide or self-harm, please contact "
            "the SA Suicide Crisis Line on 0800 567 567 (24/7) or your local emergency "
            "services.",
            small_gray,
        )
    )

    doc.build(elements)
    return buf.getvalue()
