import unittest
from typing import Dict, Set

from src.post_change_validation_analysis_wrappers import analyze_neighbors
from src.post_change_validation_models import Finding
from src.post_change_validation_neighbor_parsers import parse_cdp_neighbors, parse_lldp_neighbors
from src.post_change_validation_neighbors import compare_neighbors


def legacy_analyze_neighbors(
    pre: Dict[str, str],
    post: Dict[str, str],
    old_to_new: Dict[str, str],
    mac_present_ports: Dict[str, int],
    poe_powered_ports: Set[str],
    post_if: Dict[str, object],
) -> list[Finding]:
    findings: list[Finding] = []
    for proto, parser, section_name in [("CDP", parse_cdp_neighbors, "show cdp neighbors"), ("LLDP", parse_lldp_neighbors, "show lldp neighbors")]:
        pre_section = pre.get(section_name, "")
        post_section = post.get(section_name, "")
        pre_recs = parser(pre_section)
        post_recs = parser(post_section)
        if pre_section and not pre_recs:
            findings.append(Finding("INFO", f"{proto} Neighbors", f"Pre-change {proto.lower()} section found, but no neighbor records were parsed.", "This may be normal if no neighbors were present, or the parser may need adjustment for this output format."))
        if post_section and not post_recs:
            findings.append(Finding("INFO", f"{proto} Neighbors", f"Post-change {proto.lower()} section found, but no neighbor records were parsed.", "This may be normal if no neighbors were present, or the parser may need adjustment for this output format."))
        neighbor_comparison = compare_neighbors(
            pre_recs,
            post_recs,
            old_to_new,
            mac_present_ports=mac_present_ports,
            poe_powered_ports=poe_powered_ports,
            post_if=post_if,
        )
        if neighbor_comparison.missing:
            findings.append(Finding("WARN", f"{proto} Neighbors", f"{len(neighbor_comparison.missing)} {proto.lower()} neighbor record(s) missing after change.", "\n".join(neighbor_comparison.missing)))
        if neighbor_comparison.missing_with_presence_evidence:
            findings.append(Finding("INFO", f"{proto} Neighbors", f"{len(neighbor_comparison.missing_with_presence_evidence)} {proto.lower()} neighbor advertisement(s) missing, but endpoint evidence is present on the mapped port.", "\n".join(neighbor_comparison.missing_with_presence_evidence)))
        if neighbor_comparison.matched:
            findings.append(Finding("PASS", f"{proto} Neighbors", f"{len(neighbor_comparison.matched)} {proto.lower()} neighbor record(s) matched after change.", "\n".join(neighbor_comparison.matched)))
        if neighbor_comparison.new:
            findings.append(Finding("INFO", f"{proto} Neighbors", f"{len(neighbor_comparison.new)} new {proto.lower()} neighbor record(s) appeared after change.", "\n".join(neighbor_comparison.new)))
    return findings


class NeighborFindingExtractionEquivalenceTests(unittest.TestCase):
    def test_extracted_analyze_neighbors_matches_legacy_for_matched_cdp(self):
        pre = {
            "show cdp neighbors": """
Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID
router-0.example Gig 1/0/25       120        R           ROUTER    Twe1/0/22
""",
        }
        post = {
            "show cdp neighbors": """
Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID
router-0.example Te1/1/1          120        R           ROUTER    Twe1/0/22
""",
        }
        old_to_new = {"Gi1/0/25": "Te1/1/1"}

        legacy = legacy_analyze_neighbors(pre, post, old_to_new, {}, set(), {})
        extracted = analyze_neighbors(pre, post, old_to_new, {}, set(), {})

        self.assertEqual(legacy, extracted)
        self.assertEqual(["PASS"], [finding.severity for finding in extracted])
        self.assertEqual("CDP Neighbors", extracted[0].category)
        self.assertIn("router-0.example: Gi1/0/25 -> Te1/1/1", extracted[0].detail)

    def test_extracted_analyze_neighbors_matches_legacy_for_missing_with_poe_evidence(self):
        pre = {
            "show cdp neighbors": """
Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID
phone-1.example  Gig 1/0/3        120        H           PHONE     Gig 0/1
""",
        }
        post = {
            "show cdp neighbors": """
Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID
""",
        }
        old_to_new = {"Gi1/0/3": "Te1/0/3"}
        poe_powered_ports = {"Te1/0/3"}

        legacy = legacy_analyze_neighbors(pre, post, old_to_new, {}, poe_powered_ports, {})
        extracted = analyze_neighbors(pre, post, old_to_new, {}, poe_powered_ports, {})

        self.assertEqual(legacy, extracted)
        downgraded = [finding for finding in extracted if "endpoint evidence is present on the mapped port" in finding.finding]
        self.assertEqual(["INFO"], [finding.severity for finding in downgraded])
        self.assertIn("PoE still delivering on mapped post port", downgraded[0].detail)

    def test_extracted_analyze_neighbors_matches_legacy_for_unparsed_section_info(self):
        pre = {
            "show cdp neighbors": "CDP is enabled but no neighbors are currently advertised.",
        }
        post = {
            "show cdp neighbors": "CDP is enabled but no neighbors are currently advertised.",
        }

        legacy = legacy_analyze_neighbors(pre, post, {}, {}, set(), {})
        extracted = analyze_neighbors(pre, post, {}, {}, set(), {})

        self.assertEqual(legacy, extracted)
        self.assertEqual(
            [
                "INFO",
                "INFO",
            ],
            [finding.severity for finding in extracted],
        )
        self.assertEqual(
            [
                "Pre-change cdp section found, but no neighbor records were parsed.",
                "Post-change cdp section found, but no neighbor records were parsed.",
            ],
            [finding.finding for finding in extracted],
        )

    def test_extracted_analyze_neighbors_matches_legacy_for_warn_missing_without_evidence(self):
        pre = {
            "show cdp neighbors": """
Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID
router-0.example Gig 1/0/25       120        R           ROUTER    Twe1/0/22
""",
        }
        post = {
            "show cdp neighbors": """
Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID
""",
        }
        old_to_new = {"Gi1/0/25": "Te1/1/1"}

        legacy = legacy_analyze_neighbors(pre, post, old_to_new, {}, set(), {})
        extracted = analyze_neighbors(pre, post, old_to_new, {}, set(), {})

        self.assertEqual(legacy, extracted)
        warn_missing = [finding for finding in extracted if finding.severity == "WARN" and "missing after change" in finding.finding]
        self.assertEqual(1, len(warn_missing))
        self.assertIn("expected post local Te1/1/1", warn_missing[0].detail)


if __name__ == "__main__":
    unittest.main()
