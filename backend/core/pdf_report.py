"""Місячний PDF-звіт про прогрес учня (M15). Бренд тенанта, без згадок WordSnap.
reportlab. Повертає bytes для надсилання файлом у Telegram."""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

_MONTHS = ["", "січня", "лютого", "березня", "квітня", "травня", "червня",
           "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]


def _hex(c: str) -> colors.Color:
    try:
        return colors.HexColor(c)
    except Exception:
        return colors.HexColor("#7C3AED")


def build_student_report(
    *, brand: str, color_primary: str, student_name: str,
    month: int, year: int,
    reviews: int, learned: int, new_words: int, streak: int,
    activity: dict, target_lang: str | None = None,
) -> bytes:
    """activity: {'YYYY-MM-DD': count} за місяць — рендеримо стовпчиками."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    primary = _hex(color_primary)

    # Хедер-смуга з брендом
    c.setFillColor(primary)
    c.rect(0, H - 40 * mm, W, 40 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(20 * mm, H - 22 * mm, brand)
    c.setFont("Helvetica", 12)
    c.drawString(20 * mm, H - 32 * mm, f"Звіт про прогрес · {_MONTHS[month]} {year}")

    # Імʼя учня
    c.setFillColor(colors.HexColor("#0F0F14"))
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, H - 58 * mm, student_name)
    if target_lang:
        c.setFont("Helvetica", 11)
        c.setFillColor(colors.grey)
        c.drawString(20 * mm, H - 66 * mm, f"Мова: {target_lang}")

    # Картки метрик
    metrics = [("Повторень", reviews), ("Вивчено слів", learned),
               ("Нових слів", new_words), ("Днів поспіль", streak)]
    x0, y0, cw, ch, gap = 20 * mm, H - 100 * mm, 40 * mm, 26 * mm, 5 * mm
    for i, (label, val) in enumerate(metrics):
        x = x0 + i * (cw + gap)
        c.setFillColor(colors.HexColor("#F3F4F6"))
        c.roundRect(x, y0, cw, ch, 4, fill=1, stroke=0)
        c.setFillColor(primary)
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(x + cw / 2, y0 + ch - 12 * mm, str(val))
        c.setFillColor(colors.grey)
        c.setFont("Helvetica", 8)
        c.drawCentredString(x + cw / 2, y0 + 5 * mm, label)

    # Графік активності
    c.setFillColor(colors.HexColor("#0F0F14"))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, y0 - 18 * mm, "Активність за місяць")
    days = sorted(activity.keys())
    if days:
        max_n = max([activity[d] for d in days] + [1])
        chart_x, chart_y, chart_w, chart_h = 20 * mm, y0 - 60 * mm, 170 * mm, 35 * mm
        bar_w = chart_w / max(len(days), 1)
        c.setFillColor(primary)
        for i, d in enumerate(days):
            h = (activity[d] / max_n) * chart_h
            c.rect(chart_x + i * bar_w, chart_y, max(bar_w - 1, 1), h, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#E5E7EB"))
        c.line(chart_x, chart_y, chart_x + chart_w, chart_y)
    else:
        c.setFillColor(colors.grey)
        c.setFont("Helvetica", 10)
        c.drawString(20 * mm, y0 - 30 * mm, "Активності цього місяця не було.")

    # Футер
    c.setFillColor(colors.grey)
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 15 * mm, f"{brand} · {datetime(year, month, 1).strftime('%m.%Y')}")

    c.showPage()
    c.save()
    return buf.getvalue()
