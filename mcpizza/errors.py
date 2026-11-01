"""Safe error descriptions.

Raw exception text from HTTP/API libraries can contain URLs, response bodies,
or order/payment JSON. Anything shown to the model or written to logs on the
order/payment path goes through safe_error() instead of str(exception).
"""
from typing import Any, Dict, List


class OrderError(Exception):
    """A user-correctable problem (no active order, bad token, etc).

    Messages of this type are written by us and are safe to show.
    """


def safe_error(exc: BaseException) -> str:
    """Return a short, non-sensitive description of an exception."""
    if isinstance(exc, OrderError):
        return str(exc)
    try:
        import requests
    except ImportError:  # pragma: no cover
        requests = None
    if requests is not None:
        if isinstance(exc, requests.exceptions.Timeout):
            return "request to Domino's timed out"
        if isinstance(exc, requests.exceptions.ConnectionError):
            return "could not connect to Domino's"
        if isinstance(exc, requests.exceptions.HTTPError):
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            return f"Domino's returned HTTP {status}" if status else "Domino's returned an HTTP error"
        if isinstance(exc, requests.exceptions.RequestException):
            return "request to Domino's failed"
    return f"unexpected {type(exc).__name__}"


def safe_status_summary(response: Dict[str, Any]) -> str:
    """Summarise a Domino's price/place response without echoing its body."""
    status = response.get('Status')
    items: List[Dict[str, Any]] = (response.get('Order') or {}).get('StatusItems') or []
    codes = ', '.join(str(i.get('Code', '?')) for i in items if isinstance(i, dict))
    return f"status {status}" + (f" ({codes})" if codes else "")
