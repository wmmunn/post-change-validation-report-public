"""Shared ReportLab PDF rendering helpers for post-change reports."""

from __future__ import annotations

import html
from typing import List, Optional


def pdf_paragraph(paragraph_cls, text: object, style):
    return paragraph_cls(html.escape(str(text or "")), style)


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
) -> None:
    if not rows:
        return
    header_style = header_style or normal_style
    story.append(spacer_cls(1, 14))
    story.append(paragraph_cls(title_text, styles["Heading2"]))
    story.append(pdf_paragraph(paragraph_cls, finding_text, normal_style))
    story.append(spacer_cls(1, 5))
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
