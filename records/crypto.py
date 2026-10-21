"""SSN encryption and lookup hashing.

SSNs are stored encrypted (Fernet). A keyed hash of the SSN is stored alongside
so records can be matched and searched by SSN without decrypting every row.
"""

import hashlib
import hmac
import re

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _fernet():
    key = settings.FIELD_ENCRYPTION_KEY
    if not key:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY is not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def normalize_ssn(value):
    """Return a 9-digit SSN string, or '' if the value is not a plausible SSN."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    digits = re.sub(r"\D", "", str(value))
    if not digits or len(digits) > 9:
        return ""
    digits = digits.zfill(9)
    # Reject placeholders like 000000000 and values with an all-zero area/group/serial.
    if digits[:3] in ("000", "666") or digits[3:5] == "00" or digits[5:] == "0000":
        return ""
    return digits


def encrypt(value):
    if not value:
        return ""
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token):
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""


def ssn_hash(ssn):
    if not ssn:
        return ""
    key = (settings.FIELD_ENCRYPTION_KEY or "").encode()
    return hmac.new(key, ssn.encode(), hashlib.sha256).hexdigest()
