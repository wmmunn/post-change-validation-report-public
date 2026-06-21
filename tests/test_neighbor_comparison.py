import unittest
from dataclasses import dataclass

from src.post_change_validation_neighbors import compare_neighbors


@dataclass
class NeighborRow:
    neighbor: str
    local_interface: str
    remote_interface: str
    raw: str


@dataclass
class StatusRow:
    status: str


def neighbor(name: str, local: str, remote: str) -> NeighborRow:
    return NeighborRow(name, local, remote, f"{name} {local} {remote}")


class NeighborComparisonTests(unittest.TestCase):
    def test_mapped_neighbors_match_through_old_to_new_ports(self):
        result = compare_neighbors(
            [
                neighbor("router-0.net.location.com", "Gi1/0/25", "Twe1/0/22"),
                neighbor("router-1.net.location.com", "Gi2/0/52", "Twe1/0/22"),
            ],
            [
                neighbor("router-0.net.location.com", "Te1/1/1", "Twe1/0/22"),
                neighbor("router-1.net.location.com", "Te2/1/8", "Twe1/0/22"),
            ],
            {"Gi1/0/25": "Te1/1/1", "Gi2/0/52": "Te2/1/8"},
        )

        self.assertEqual(
            [
                "router-0.net.location.com: Gi1/0/25 -> Te1/1/1, remote Twe1/0/22",
                "router-1.net.location.com: Gi2/0/52 -> Te2/1/8, remote Twe1/0/22",
            ],
            result.matched,
        )
        self.assertEqual([], result.missing)
        self.assertEqual([], result.new)

    def test_matched_neighbor_uses_post_name_when_pre_name_is_unknown(self):
        result = compare_neighbors(
            [neighbor("unknown", "Gi1/0/25", "Twe1/0/22")],
            [neighbor("router-0.net.location.com", "Te1/1/1", "Twe1/0/22")],
            {"Gi1/0/25": "Te1/1/1"},
        )

        self.assertEqual(
            ["router-0.net.location.com: Gi1/0/25 -> Te1/1/1, remote Twe1/0/22"],
            result.matched,
        )

    def test_compatible_neighbor_on_observed_post_port_matches(self):
        result = compare_neighbors(
            [neighbor("core-router-0.net.location.com", "Gi1/0/25", "Twe1/0/22")],
            [neighbor("router-0.net.location.com", "Te1/1/2", "Twe1/0/22")],
            {"Gi1/0/25": "Te1/1/1"},
        )

        self.assertEqual(
            ["core-router-0.net.location.com: Gi1/0/25 -> Te1/1/2, remote Twe1/0/22"],
            result.matched,
        )
        self.assertEqual([], result.missing)

    def test_missing_neighbor_reports_expected_post_port(self):
        result = compare_neighbors(
            [neighbor("router-0.net.location.com", "Gi1/0/25", "Twe1/0/22")],
            [],
            {"Gi1/0/25": "Te1/1/1"},
        )

        self.assertEqual(
            [
                "router-0.net.location.com on Gi1/0/25, remote Twe1/0/22 | "
                "expected post local Te1/1/1, remote Twe1/0/22 | "
                "raw=router-0.net.location.com Gi1/0/25 Twe1/0/22"
            ],
            result.missing,
        )

    def test_missing_neighbor_with_endpoint_evidence_is_informational(self):
        result = compare_neighbors(
            [neighbor("access-ap.net.location.com", "Gi1/0/3", "Gi0/1")],
            [],
            {"Gi1/0/3": "Te1/0/3"},
            mac_present_ports={"Te1/0/3": 1},
            poe_powered_ports={"Te1/0/3"},
            post_if={"Te1/0/3": StatusRow("connected")},
        )

        self.assertEqual([], result.missing)
        self.assertEqual(
            [
                "access-ap.net.location.com on Gi1/0/3, remote Gi0/1 | "
                "expected post local Te1/0/3, remote Gi0/1 | "
                "raw=access-ap.net.location.com Gi1/0/3 Gi0/1 | "
                "supporting evidence: 1 expected MAC(s) present on mapped post port; "
                "PoE still delivering on mapped post port; mapped post port is connected"
            ],
            result.missing_with_presence_evidence,
        )

    def test_new_neighbor_reports_post_record(self):
        result = compare_neighbors(
            [],
            [neighbor("new-router.net.location.com", "Te1/1/4", "Twe1/0/24")],
            {},
        )

        self.assertEqual(
            [
                "new-router.net.location.com on Te1/1/4, remote Twe1/0/24 | "
                "raw=new-router.net.location.com Te1/1/4 Twe1/0/24"
            ],
            result.new,
        )


if __name__ == "__main__":
    unittest.main()
