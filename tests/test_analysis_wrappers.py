import unittest

from src.post_change_validation_analysis_wrappers import (
    analyze_cpu,
    analyze_environment,
    analyze_inventory,
    analyze_version,
    parse_inventory_records,
)


class AnalysisWrapperTests(unittest.TestCase):
    def test_environment_ignores_threshold_legend_but_warns_on_fault_line(self):
        section = """
Temperature threshold legend: alarm means above limit
Fan 1 OK
Power Supply 2 Fault
"""

        findings = analyze_environment(section)

        self.assertEqual(["WARN"], [finding.severity for finding in findings])
        self.assertIn("1 possible environment health concern", findings[0].finding)
        self.assertIn("Power Supply 2 Fault", findings[0].detail)
        self.assertNotIn("threshold legend", findings[0].detail.lower())

    def test_inventory_records_parse_sanitized_component_pid_vid_and_serial(self):
        section = """
NAME: "Switch 1", DESCR: "Cisco C9300"
PID: C9300-48U       , VID: V01  , SN: SANITIZED1234
"""

        records = parse_inventory_records(section)
        findings = analyze_inventory(section)

        self.assertEqual(
            [
                {
                    "component": "Switch 1",
                    "description": "Cisco C9300",
                    "pid": "C9300-48U",
                    "vid": "V01",
                    "serial": "SANITIZED1234",
                }
            ],
            records,
        )
        self.assertEqual("INFO", findings[0].severity)
        self.assertIn("Inventory parsed: 1 PID/model value(s), 1 serial value(s).", findings[0].finding)
        self.assertIn("Switch 1|Cisco C9300|C9300-48U|V01|SANITIZED1234", findings[0].detail)

    def test_version_captures_documentation_lines_only(self):
        section = """
Cisco IOS XE Software, Version 17.09.04
Switch uptime is 2 weeks, 1 day
System image file is "flash:packages.conf"
Unrelated operational line
"""

        findings = analyze_version(section)

        self.assertEqual("INFO", findings[0].severity)
        self.assertIn("Version 17.09.04", findings[0].detail)
        self.assertIn("System image file", findings[0].detail)
        self.assertNotIn("Unrelated operational line", findings[0].detail)

    def test_cpu_warns_when_five_second_utilization_is_high(self):
        findings = analyze_cpu("CPU utilization for five seconds: 92%/0%; one minute: 20%; five minutes: 10%")

        self.assertEqual("WARN", findings[0].severity)
        self.assertEqual("CPU five-second utilization: 92%", findings[0].finding)


if __name__ == "__main__":
    unittest.main()
