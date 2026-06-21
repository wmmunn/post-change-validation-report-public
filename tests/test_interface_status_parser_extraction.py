import unittest

from src.post_change_validation_interface_status import InterfaceStatus, parse_interface_status


SANITIZED_INTERFACE_STATUS_SECTION = """
Port      Name               Status       Vlan       Duplex  Speed Type
Gi1/0/1   User Port          connected    100        a-full  a-1000 10/100/1000BaseTX
Gi1/0/2   Spare              notconnect   100        auto    auto   10/100/1000BaseTX
Te1/1/1   to router-0        connected    trunk      full    1000  1000BaseLX SFP
"""


class InterfaceStatusParserExtractionTests(unittest.TestCase):
    def test_parse_interface_status_extracts_expected_ports(self):
        parsed = parse_interface_status(SANITIZED_INTERFACE_STATUS_SECTION)

        self.assertEqual(
            {
                "Gi1/0/1": InterfaceStatus(
                    "Gi1/0/1",
                    "connected",
                    "100",
                    "a-full",
                    "a-1000",
                    "10/100/1000BaseTX",
                    raw="Gi1/0/1   User Port          connected    100        a-full  a-1000 10/100/1000BaseTX",
                ),
                "Gi1/0/2": InterfaceStatus(
                    "Gi1/0/2",
                    "notconnect",
                    "100",
                    "auto",
                    "auto",
                    "10/100/1000BaseTX",
                    raw="Gi1/0/2   Spare              notconnect   100        auto    auto   10/100/1000BaseTX",
                ),
                "Te1/1/1": InterfaceStatus(
                    "Te1/1/1",
                    "connected",
                    "trunk",
                    "full",
                    "1000",
                    "1000BaseLX SFP",
                    raw="Te1/1/1   to router-0        connected    trunk      full    1000  1000BaseLX SFP",
                ),
            },
            parsed,
        )

    def test_parse_interface_status_skips_header_and_blank_lines(self):
        parsed = parse_interface_status("Port      Name\n\n---\nGi1/0/3   AP connected 912 a-full a-1000 10/100/1000BaseTX")

        self.assertEqual(["Gi1/0/3"], list(parsed.keys()))
        self.assertEqual("connected", parsed["Gi1/0/3"].status)


if __name__ == "__main__":
    unittest.main()
