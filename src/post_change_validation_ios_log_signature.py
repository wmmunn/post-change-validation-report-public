"""Cisco running-config log signature gate for Post Change Validation Tool."""

from __future__ import annotations

import re

from src.post_change_validation_command_sections import split_sections

# hostname cisco-access-sw01
CISCO_WORD_PATTERN = re.compile(r"\bcisco\b", re.IGNORECASE)


def extract_running_config_section(log_text: str) -> str:
    """Return the parsed show running-config section body from raw log text."""
    sections = split_sections(log_text or "")
    return sections.get("show running-config", "")


def validate_ios_xe_log_signature(log_text: str) -> tuple[bool, str]:
    """Return (ok, reason). reason is empty when ok."""
    running_config_section = extract_running_config_section(log_text)
    if not running_config_section.strip():
        return (
            False,
            "Missing or empty show running-config section. "
            "This tool requires logs with a show running-config block containing the word 'cisco'.",
        )

    if CISCO_WORD_PATTERN.search(running_config_section):
        return True, ""

    return (
        False,
        "Unsupported log: show running-config does not contain the word 'cisco'. "
        "This tool accepts Cisco IOS and IOS-XE command output only.",
    )
