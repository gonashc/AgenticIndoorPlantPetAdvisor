"""Validation for You.com credentials at the provider boundary."""


def validate_you_api_key(value: str) -> str:
    """Return a header-safe key without ever including it in validation errors."""
    invalid = (
        not value
        or value != value.strip()
        or value.startswith(('"', "'"))
        or value.endswith(('"', "'"))
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    )
    if invalid:
        raise ValueError("You.com API key format is invalid")
    return value
