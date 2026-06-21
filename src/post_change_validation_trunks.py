"""Pure trunk comparison helpers for Post Change Validation Tool."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Set


@dataclass
class TrunkComparison:
    has_evidence: bool = False
    matched_mapped: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def compare_mapped_trunks(
    pre_trunks: Set[str],
    post_trunks: Set[str],
    old_to_new: Mapping[str, str],
) -> TrunkComparison:
    result = TrunkComparison(has_evidence=bool(pre_trunks or post_trunks))
    if not result.has_evidence:
        return result

    for pre_port in sorted(pre_trunks):
        expected = old_to_new.get(pre_port, pre_port)
        if expected in post_trunks:
            if expected != pre_port:
                result.matched_mapped.append(f"{pre_port} -> {expected}")
        else:
            result.missing.append(f"{pre_port} expected post {expected}")
    return result
