"""
Logging module for MCP Pizza
Logs all two-way interactions between the MCP server and clients
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Setup logging directory
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Create logger
logger = logging.getLogger("mcpizza")
logger.setLevel(logging.DEBUG)

# File handler for all interactions
interaction_log = LOG_DIR / f"interactions_{datetime.now().strftime('%Y%m%d')}.log"
file_handler = logging.FileHandler(interaction_log)
file_handler.setLevel(logging.DEBUG)

# Console handler for errors
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)

# Formatter
formatter = logging.Formatter(
    '%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Regex for 12+ digit runs with optional spaces/dashes (e.g. 4111 1111 1111 1111 or 4111-1111-1111-1111)
_DIGIT_RUN_RE = re.compile(r'(?:\d[ -]*){12,}')
# Keys that indicate sensitive payment data (case-insensitive)
_PAYMENT_KEYS = frozenset({
    'card', 'cvv', 'cvc', 'security', 'expiry', 'expiration', 'payment'
})


def redact(value: Any) -> Any:
    """Recursively redact sensitive data from a value.

    - Replace values whose key (case-insensitive) contains
      card/cvv/cvc/security/expiry/expiration/payment with "[REDACTED]".
    - Mask any string run of 12+ digits (with optional spaces/dashes)
      with "[REDACTED-NUM]".

    Args:
        value: Any dict, list, or primitive value.

    Returns:
        The value with sensitive data redacted.
    """
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [redact(item) for item in value]
    elif isinstance(value, str):
        return _DIGIT_RUN_RE.sub('[REDACTED-NUM]', value)
    return value


def _redact_by_key(value: Any) -> Any:
    """Redact dict values whose key contains sensitive payment keywords.

    Args:
        value: Any dict, list, or primitive value.

    Returns:
        The value with keys redacted.
    """
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            kl = k.lower()
            if any(term in kl for term in _PAYMENT_KEYS):
                result[k] = '[REDACTED]'
            else:
                result[k] = _redact_by_key(redact(v))
        return result
    elif isinstance(value, list):
        return [_redact_by_key(item) for item in value]
    elif isinstance(value, str):
        return _DIGIT_RUN_RE.sub('[REDACTED-NUM]', value)
    return value


def _redact_log_data(log_data: dict) -> dict:
    """Redact all sensitive fields from a log data dict.

    Applies both the key-based redaction and the digit-masking pass.
    """
    # First pass: replace values for matching keys
    data = redact(log_data)
    # Second pass: ensure key-based redaction propagates correctly
    return _redact_by_key(data)


class InteractionLogger:
    """Logger for MCP interactions"""

    @staticmethod
    def log_tool_call(tool_name: str, arguments: dict, request_id: Optional[str] = None):
        """Log incoming tool call"""
        log_data = {
            "type": "tool_call",
            "direction": "incoming",
            "tool_name": tool_name,
            "arguments": _redact_log_data(arguments),
            "request_id": request_id,
            "timestamp": datetime.now().isoformat()
        }
        logger.info(f"TOOL_CALL | {json.dumps(log_data)}")

    @staticmethod
    def log_tool_response(tool_name: str, success: bool, response: Any,
                         request_id: Optional[str] = None, error: Optional[str] = None):
        """Log outgoing tool response"""
        # Truncate large responses for logging
        response_preview = str(response)[:500] if response else None

        log_data = {
            "type": "tool_response",
            "direction": "outgoing",
            "tool_name": tool_name,
            "success": success,
            "response_preview": _redact_log_data(response_preview) if response_preview else None,
            "request_id": request_id,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }
        logger.info(f"TOOL_RESPONSE | {json.dumps(log_data)}")

    @staticmethod
    def log_tool_list_request():
        """Log tools/list request"""
        log_data = {
            "type": "list_tools",
            "direction": "incoming",
            "timestamp": datetime.now().isoformat()
        }
        logger.info(f"LIST_TOOLS | {json.dumps(log_data)}")

    @staticmethod
    def log_initialization(client_info: dict):
        """Log MCP initialization"""
        log_data = {
            "type": "initialization",
            "direction": "incoming",
            "client_info": _redact_log_data(client_info),
            "timestamp": datetime.now().isoformat()
        }
        logger.info(f"INIT | {json.dumps(log_data)}")

    @staticmethod
    def log_error(error_type: str, error_message: str, context: Optional[dict] = None):
        """Log errors"""
        log_data = {
            "type": "error",
            "error_type": error_type,
            "error_message": error_message,
            "context": _redact_log_data(context) if context else {},
            "timestamp": datetime.now().isoformat()
        }
        logger.error(f"ERROR | {json.dumps(log_data)}")

    @staticmethod
    def log_state_change(state_type: str, old_value: Any, new_value: Any):
        """Log state changes (e.g., order creation, items added)"""
        log_data = {
            "type": "state_change",
            "state_type": state_type,
            "old_value": _redact_log_data(str(old_value)[:200]) if old_value else None,
            "new_value": _redact_log_data(str(new_value)[:200]) if new_value else None,
            "timestamp": datetime.now().isoformat()
        }
        logger.info(f"STATE_CHANGE | {json.dumps(log_data)}")


# Global instance
interaction_logger = InteractionLogger()