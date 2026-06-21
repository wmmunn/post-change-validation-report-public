"""IOS/IOS-XE log signature gate for Post Change Validation Tool."""

from __future__ import annotations

import re

from src.post_change_validation_command_sections import split_sections

# Cisco IOS Software, Version 15.2(7)E
IOS_SOFTWARE_SIGNATURE_PATTERN = re.compile(r"\bCisco IOS Software\b", re.IGNORECASE)

# Cisco IOS XE Software, Version 17.09.04
IOS_XE_SOFTWARE_SIGNATURE_PATTERN = re.compile(r"\bCisco IOS XE Software\b", re.IGNORECASE)

# Cisco NX-OS(tm) Software, Version 10.2(3)
NXOS_SOFTWARE_SIGNATURE_PATTERN = re.compile(r"\bCisco NX-OS\b", re.IGNORECASE)

# Cisco IOS XR Software, Version 7.5.2
IOS_XR_SOFTWARE_SIGNATURE_PATTERN = re.compile(r"\bCisco IOS XR Software\b", re.IGNORECASE)

_UNSUPPORTED_OS_SIGNATURES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        NXOS_SOFTWARE_SIGNATURE_PATTERN,
        "NX-OS logs are not supported. This tool accepts Cisco IOS and IOS-XE command output only.",
    ),
    (
        IOS_XR_SOFTWARE_SIGNATURE_PATTERN,
        "IOS-XR logs are not supported. This tool accepts Cisco IOS and IOS-XE command output only.",
    ),
)


def extract_show_version_section(log_text: str) -> str:
    """Return the parsed show version section body from raw log text."""
    sections = split_sections(log_text or "")
    return sections.get("show version", "")


def validate_ios_xe_log_signature(log_text: str) -> tuple[bool, str]:
    """Return (ok, reason). reason is empty when ok."""
    version_section = extract_show_version_section(log_text)
    if not version_section.strip():
        return (
            False,
            "Missing or empty show version section. "
            "This tool requires Cisco IOS or IOS-XE logs with a recognizable show version block.",
        )

    for pattern, reason in _UNSUPPORTED_OS_SIGNATURES:
        if pattern.search(version_section):
            return False, reason

    if IOS_SOFTWARE_SIGNATURE_PATTERN.search(version_section) or IOS_XE_SOFTWARE_SIGNATURE_PATTERN.search(
        version_section
    ):
        return True, ""

    return (
        False,
        "Unsupported log: show version does not contain a Cisco IOS or IOS-XE software signature. "
        "NX-OS, IOS-XR, and other Cisco OS families are not supported.",
    )
