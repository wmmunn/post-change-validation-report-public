"""Pure transceiver HTML rendering helpers."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Tuple

from src.post_change_validation_transceivers import (
    parse_transceiver_visual_rows,
    transceiver_level_class,
)


@dataclass
class TransceiverHtmlRow:
    interface: str
    metric: str
    unit: str
    value: float
    low_alarm: float
    low_warn: float
    high_warn: float
    high_alarm: float
    pre_value: float | None = None


def transceiver_scale_bounds(low_alarm: float, high_alarm: float) -> Tuple[float, float]:
    span = high_alarm - low_alarm
    if span <= 0:
        return low_alarm - 1.0, high_alarm + 1.0
    pad = span * 0.15
    return low_alarm - pad, high_alarm + pad


def transceiver_scale_pct(value: float, scale_min: float, scale_max: float) -> float:
    if scale_max == scale_min:
        return 50.0
    pct = ((value - scale_min) / (scale_max - scale_min)) * 100.0
    return max(0.0, min(100.0, pct))


def transceiver_delta_text(value: float, pre_value: float | None) -> str:
    if pre_value is None:
        return "n/a"
    return f"{value - pre_value:+.2f}"


def transceiver_value_text(unit: str, value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{unit} {value:.2f}"


def transceiver_html_row_from_visual_row(row: dict[str, object]) -> TransceiverHtmlRow:
    pre_raw = row.get("pre_value")
    return TransceiverHtmlRow(
        interface=str(row["interface"]),
        metric=str(row["metric"]),
        unit=str(row.get("unit", "")),
        value=float(row["value"]),
        low_alarm=float(row["low_alarm"]),
        low_warn=float(row["low_warn"]),
        high_warn=float(row["high_warn"]),
        high_alarm=float(row["high_alarm"]),
        pre_value=float(pre_raw) if pre_raw is not None else None,
    )


def transceiver_row_class(row: TransceiverHtmlRow) -> str:
    return transceiver_level_class(row.value, row.low_alarm, row.low_warn, row.high_warn, row.high_alarm)


def transceiver_range_bar(
    value: float,
    pre_value: float | None,
    low_alarm: float,
    low_warn: float,
    high_warn: float,
    high_alarm: float,
) -> str:
    scale_min, scale_max = transceiver_scale_bounds(low_alarm, high_alarm)
    marker = transceiver_scale_pct(value, scale_min, scale_max)
    pre_marker = transceiver_scale_pct(pre_value, scale_min, scale_max) if pre_value is not None else None
    low_alarm_pct = transceiver_scale_pct(low_alarm, scale_min, scale_max)
    low_warn_pct = transceiver_scale_pct(low_warn, scale_min, scale_max)
    high_warn_pct = transceiver_scale_pct(high_warn, scale_min, scale_max)
    high_alarm_pct = transceiver_scale_pct(high_alarm, scale_min, scale_max)
    alarm_low_w = max(0.0, low_alarm_pct)
    warn_low_w = max(0.0, low_warn_pct - low_alarm_pct)
    ok_w = max(0.0, high_warn_pct - low_warn_pct)
    warn_high_w = max(0.0, high_alarm_pct - high_warn_pct)
    alarm_high_w = max(0.0, 100.0 - high_alarm_pct)
    pre_marker_html = (
        "<span class='xcvr-marker xcvr-pre-marker' title='Pre-change' style='left: %.1f%%'></span>" % pre_marker
        if pre_marker is not None
        else ""
    )
    return (
        "<div class='xcvr-bar'>"
        "<div class='xcvr-zone xcvr-alarm-low' style='width: %.2f%%'></div>"
        "<div class='xcvr-zone xcvr-warn-low' style='width: %.2f%%'></div>"
        "<div class='xcvr-zone xcvr-ok-zone' style='width: %.2f%%'></div>"
        "<div class='xcvr-zone xcvr-warn-high' style='width: %.2f%%'></div>"
        "<div class='xcvr-zone xcvr-alarm-high' style='width: %.2f%%'></div>"
        "%s"
        "<span class='xcvr-marker xcvr-post-marker' title='Post-change' style='left: %.1f%%'></span>"
        "</div>"
    ) % (
        alarm_low_w,
        warn_low_w,
        ok_w,
        warn_high_w,
        alarm_high_w,
        pre_marker_html,
        marker,
    )


def build_transceiver_row_html(row: TransceiverHtmlRow) -> str:
    bar = transceiver_range_bar(row.value, row.pre_value, row.low_alarm, row.low_warn, row.high_warn, row.high_alarm)
    return (
        "<tr class='xcvr-%s'><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
        % (
            transceiver_row_class(row),
            html.escape(row.interface),
            html.escape(row.metric),
            html.escape(transceiver_value_text(row.unit, row.pre_value)),
            html.escape(transceiver_value_text(row.unit, row.value)),
            html.escape(transceiver_delta_text(row.value, row.pre_value)),
            html.escape(transceiver_value_text(row.unit, row.low_alarm)),
            html.escape(transceiver_value_text(row.unit, row.low_warn)),
            html.escape(transceiver_value_text(row.unit, row.high_warn)),
            html.escape(transceiver_value_text(row.unit, row.high_alarm)),
            bar,
        )
    )


def build_transceiver_table_html(rows: list[TransceiverHtmlRow]) -> str:
    body = "".join(build_transceiver_row_html(row) for row in rows)
    return """
<table class='detail-table transceiver-table'>
<tr><th>Interface</th><th>Metric</th><th>Pre</th><th>Post</th><th>Delta</th><th>Low Alarm</th><th>Low Warn</th><th>High Warn</th><th>High Alarm</th><th>Range <span class='xcvr-legend'>(gray = pre-change, black = post-change)</span></th></tr>
%s
</table>
""" % body


def build_transceiver_html(detail: str) -> str:
    rows = parse_transceiver_visual_rows(detail)
    if not rows:
        return f"<pre>{html.escape(detail)}</pre>"
    return build_transceiver_table_html([transceiver_html_row_from_visual_row(row) for row in rows])
