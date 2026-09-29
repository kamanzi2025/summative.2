import re

# MTN (078/079) and Airtel (072/073) mobile numbers, in local or international form.
_RW_PHONE = re.compile(r"^(?:\+?250|0)(7[2389]\d{7})$")


def normalise_rwandan_phone(raw: str) -> str | None:
    """Return the E.164 form (+2507XXXXXXXX) of a Rwandan mobile number, or None if invalid."""
    match = _RW_PHONE.match(re.sub(r"[\s-]", "", raw))
    return f"+250{match.group(1)}" if match else None
