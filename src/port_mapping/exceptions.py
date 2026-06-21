"""Port-mapping profile exceptions."""


class ProfileLoadError(Exception):
    """Raised when a profile file cannot be loaded."""


class ProfileValidationError(Exception):
    """Raised when a profile fails schema validation."""
