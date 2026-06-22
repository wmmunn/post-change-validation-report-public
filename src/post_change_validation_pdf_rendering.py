"""Shared ReportLab PDF rendering helpers for post-change reports."""

from __future__ import annotations

import html
from typing import List, Optional

POE_BUDGET_CARD_HORIZONTAL_PADDING_PT = 16  # 8pt LEFTPADDING + 8pt RIGHTPADDING on the card table


def poe_budget_bar_width(card_width: float) -> float:
    """Return drawable bar width that fits inside the PoE budget card content area."""
    return card_width - POE_BUDGET_CARD_HORIZONTAL_PADDING_PT


def pdf_paragraph(paragraph_cls, text: object, style):
    return paragraph_cls(html.escape(str(text or "")), style)


def build_poe_budget_pdf_card(
    detail: str,
    *,
    paragraph_cls,
    table_cls,
    table_style_cls,
    colors,
    tiny_style,
    normal_style,
    note_style,
    build_poe_budget_render_data,
    poe_budget_bar,
    card_width: float,
):
    data = build_poe_budget_render_data(detail)
    if not data:
        return None
    title = paragraph_cls(
        '<b>PoE Budget</b> <font color="#4f5b57" size="7">(gray = pre-change, black = post-change)</font>',
        normal_style,
    )
    summary = pdf_paragraph(paragraph_cls, data["summary"], tiny_style)
    pre_pct = data.get("pre_pct")
    bar = poe_budget_bar(
        float(pre_pct) if pre_pct is not None else None,
        float(data["post_pct"]),
        poe_budget_bar_width(card_width),
    )
    rows = [[title], [summary], [bar]]
    context_note = str(data.get("context_note") or "")
    if context_note:
        rows.append([pdf_paragraph(paragraph_cls, context_note, note_style)])
    card = table_cls(rows, colWidths=[card_width])
    card.setStyle(
        table_style_cls(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef8ef")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d2c7")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return card


def append_detail_table(
    story: list,
    title_text: str,
    finding_text: str,
    header: List[str],
    rows: List[List[object]],
    widths: List[float],
    *,
    styles,
    colors,
    table_cls,
    table_style_cls,
    paragraph_cls,
    spacer_cls,
    header_bg,
    normal_style,
    row_backgrounds: Optional[List[object]] = None,
    header_style=None,
    before_table: Optional[List[object]] = None,
) -> None:
    if not rows and not before_table:
        return
    header_style = header_style or normal_style
    story.append(spacer_cls(1, 14))
    story.append(paragraph_cls(title_text, styles["Heading2"]))
    story.append(pdf_paragraph(paragraph_cls, finding_text, normal_style))
    story.append(spacer_cls(1, 5))
    if before_table:
        for flowable in before_table:
            story.append(flowable)
        story.append(spacer_cls(1, 5))
    if not rows:
        return
    table_data = [[pdf_paragraph(paragraph_cls, c, header_style) for c in header]] + rows
    row_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
    ]
    for idx, bg in enumerate(row_backgrounds or [], start=1):
        row_styles.append(("BACKGROUND", (0, idx), (-1, idx), bg))
    table = table_cls(table_data, colWidths=widths, repeatRows=1)
    table.setStyle(table_style_cls(row_styles))
    story.append(table)
