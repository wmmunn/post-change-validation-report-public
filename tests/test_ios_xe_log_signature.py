import unittest

from src.post_change_validation_ios_log_signature import validate_ios_xe_log_signature

IOS_XE_LOG = """
ACCESS-SW01#show version
Cisco IOS XE Software, Version 17.09.04
Switch uptime is 2 weeks, 1 day

ACCESS-SW01#show running-config
version 17.9
!
hostname cisco-access-sw01
interface GigabitEthernet1/0/1
 description User Port
 switchport access vlan 100
!

ACCESS-SW01#show int status
Port      Name               Status       Vlan       Duplex  Speed Type
Gi1/0/1   User Port          connected    100        a-full  a-1000 10/100/1000BaseTX
"""

IOS_CLASSIC_LOG = """
ACCESS-SW01#show version
Cisco IOS Software, Version 15.2(7)E
Switch uptime is 10 weeks, 2 days

ACCESS-SW01#show running-config
version 15.2
!
hostname cisco-access-sw01
!
"""

NXOS_LOG = """
NEXUS-SW01#show version
Cisco NX-OS(tm) Software, Version 10.2(3)

NEXUS-SW01#show running-config
version 10.2(3)
!
hostname nexus-access-sw01
!
"""

UNSUPPORTED_GENERIC_LOG = """
GENERIC-SW01#show version
Vendor Switch OS Version 9.9.9
Switch uptime is 1 day

GENERIC-SW01#show running-config
version 9.9.9
!
hostname generic-access-sw01
!
"""

EMPTY_RUNNING_CONFIG_LOG = """
ACCESS-SW01#show running-config

ACCESS-SW01#show int status
Port      Name               Status       Vlan       Duplex  Speed Type
Gi1/0/1   User Port          connected    100        a-full  a-1000 10/100/1000BaseTX
"""

NO_RUNNING_CONFIG_SECTION_LOG = """
ACCESS-SW01#show int status
Port      Name               Status       Vlan       Duplex  Speed Type
Gi1/0/1   User Port          connected    100        a-full  a-1000 10/100/1000BaseTX
"""


class IosXeLogSignatureTests(unittest.TestCase):
    def test_ios_xe_sanitized_log_passes(self):
        ok, reason = validate_ios_xe_log_signature(IOS_XE_LOG)

        self.assertTrue(ok)
        self.assertEqual("", reason)

    def test_ios_classic_sanitized_log_passes(self):
        ok, reason = validate_ios_xe_log_signature(IOS_CLASSIC_LOG)

        self.assertTrue(ok)
        self.assertEqual("", reason)

    def test_nxos_log_blocked_without_cisco_in_running_config(self):
        ok, reason = validate_ios_xe_log_signature(NXOS_LOG)

        self.assertFalse(ok)
        self.assertIn("does not contain the word 'cisco'", reason)

    def test_unsupported_generic_log_blocked(self):
        ok, reason = validate_ios_xe_log_signature(UNSUPPORTED_GENERIC_LOG)

        self.assertFalse(ok)
        self.assertIn("does not contain the word 'cisco'", reason)

    def test_empty_show_running_config_section_blocked_without_crash(self):
        ok, reason = validate_ios_xe_log_signature(EMPTY_RUNNING_CONFIG_LOG)

        self.assertFalse(ok)
        self.assertIn("Missing or empty show running-config", reason)

    def test_missing_show_running_config_section_blocked_without_crash(self):
        ok, reason = validate_ios_xe_log_signature(NO_RUNNING_CONFIG_SECTION_LOG)

        self.assertFalse(ok)
        self.assertIn("Missing or empty show running-config", reason)

    def test_empty_log_text_blocked_without_crash(self):
        ok, reason = validate_ios_xe_log_signature("")

        self.assertFalse(ok)
        self.assertIn("Missing or empty show running-config", reason)

    def test_cisco_word_match_is_case_insensitive(self):
        log = """
ACCESS-SW01#show running-config
version 17.9
!
hostname CISCO-access-sw01
!
"""
        ok, reason = validate_ios_xe_log_signature(log)

        self.assertTrue(ok)
        self.assertEqual("", reason)


if __name__ == "__main__":
    unittest.main()
