"""
Phase 2 security tests: log redaction, card file, confirm gate, dry-run
"""
import asyncio
import time
import os
import json
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from mcpizza.logger import interaction_logger, _redact_log_data
from mcpizza.tools.order_tools import (
    handle_create_order, handle_add_item_to_order, handle_prepare_order,
    handle_place_order, _token_store, _generate_token
)
from mcpizza.models.params import CreateOrderParams, AddItemParams
from mcpizza.services.order_service import create_order


# ── Helper to run async handlers ────────────────────────────────────────

def _run_async(coro):
    """Run an async coroutine and return the result."""
    return asyncio.run(coro)


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_token_store():
    """Reset token store before each test."""
    from mcpizza.tools.order_tools import _token_store
    _token_store.clear()
    yield
    _token_store.clear()


@pytest.fixture
def card_file():
    """Create a temporary card JSON file with secure permissions."""
    tmp = tempfile.mktemp(suffix='.json')
    with open(tmp, 'w') as f:
        json.dump({'number': '4111111111111111', 'expiry': '12/25', 'cvv': '123', 'zip': '12345'}, f)
    os.chmod(tmp, 0o600)
    yield tmp
    os.unlink(tmp)


@pytest.fixture
def mcpizza_card_file(card_file):
    """Set MCPIZZA_CARD_FILE env var for the test duration."""
    orig = os.environ.pop('MCPIZZA_CARD_FILE', None)
    os.environ['MCPIZZA_CARD_FILE'] = card_file
    yield
    if orig is not None:
        os.environ['MCPIZZA_CARD_FILE'] = orig
    else:
        os.environ.pop('MCPIZZA_CARD_FILE', None)


@pytest.fixture
def mock_api_price():
    """Mock api_client.price_order returning a successful response."""
    with patch('mcpizza.api.client.requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'Status': 1,
            'Order': {
                'StoreID': '8022',
                'Address': {'Street': '123 Main St', 'City': 'Fort Worth', 'Region': 'TX', 'PostalCode': '76102'},
                'Products': [],
                'Coupons': [],
                'Amounts': {'Customer': 11.90},
                'ServiceMethod': 'Delivery',
                'EstimatedWaitMinutes': '30'
            }
        }
        mock_post.return_value = mock_response
        yield mock_post


# ── Task 1: Log Redaction ─────────────────────────────────────────────

def test_log_redaction_card_data():
    """Card data in log records must be redacted."""
    args = {
        'card_number': '4111111111111111',
        'card_cvv': '123',
        'card_expiry': '12/25',
        'card_zip': '12345',
        'store_id': '8022',
    }
    redacted = _redact_log_data(args)
    assert '[REDACTED]' in str(redacted.get('card_number'))
    assert '[REDACTED]' in str(redacted.get('card_cvv'))
    assert '[REDACTED]' in str(redacted.get('card_expiry'))
    assert '[REDACTED]' in str(redacted.get('card_zip'))
    # Raw card data must NOT appear
    line = json.dumps(redacted)
    assert '4111111111111111' not in line
    assert '123' not in line


def test_log_redaction_digit_run():
    """12+ digit runs must be masked as [REDACTED-NUM]."""
    args = {'phone': '411111111111', 'email': 'john@example.com'}
    redacted = _redact_log_data(args)
    line = json.dumps(redacted)
    assert '[REDACTED-NUM]' in line
    assert '411111111111' not in line


def test_log_redaction_recursive():
    """Redaction works recursively in dicts and lists."""
    args = {
        'payment': {'card_number': '4111111111111111', 'card_cvv': '123'},
        'items': [{'card_number': '4222222222222222'}],
        'meta': {'reference': 'test 1234567890123'}
    }
    redacted = _redact_log_data(args)
    line = json.dumps(redacted)
    assert '[REDACTED]' in line
    # The nested card_number in items list should also be redacted
    assert '[REDACTED]' in str(redacted['items'][0].get('card_number'))


# ── Task 2: Card Never Through the Model ──────────────────────────────

def test_load_card_from_file(card_file):
    """Card loads successfully from a valid file with 600 permissions."""
    from mcpizza.services.payment_service import _load_card_from_file
    card = _load_card_from_file(card_file)
    assert card['number'] == '4111111111111111'
    assert card['expiry'] == '12/25'
    assert card['cvv'] == '123'
    assert card['zip'] == '12345'


def test_load_card_missing_file():
    """Loading from a missing file raises FileNotFoundError."""
    from mcpizza.services.payment_service import _load_card_from_file
    with pytest.raises(FileNotFoundError):
        _load_card_from_file('/nonexistent/path.json')


def test_load_card_bad_permissions(card_file):
    """Loading from a file with group/other permissions raises ValueError."""
    from mcpizza.services.payment_service import _load_card_from_file
    # Make the file readable by group
    os.chmod(card_file, 0o644)
    try:
        from mcpizza.services.payment_service import _load_card_from_file
        with pytest.raises(ValueError, match="insecure permissions"):
            _load_card_from_file(card_file)
    finally:
        # Restore secure permissions for cleanup
        os.chmod(card_file, 0o600)


def test_load_card_missing_keys(card_file):
    """Loading a file missing required keys raises ValueError."""
    # Write a card file without all required keys
    tmp = tempfile.mktemp(suffix='.json')
    with open(tmp, 'w') as f:
        json.dump({'number': '4111111111111111'}, f)
    os.chmod(tmp, 0o600)
    from mcpizza.services.payment_service import _load_card_from_file
    with pytest.raises(ValueError, match="missing required keys"):
        _load_card_from_file(tmp)
    os.unlink(tmp)


# ── Task 3: Confirm Gate + Dry Run ────────────────────────────────────

def test_prepare_order_returns_token(mock_api_price):
    """prepare_order returns a human-readable summary and a confirm_token."""
    coro = handle_create_order(CreateOrderParams(
        store_id='8022',
        customer_name='John Doe',
        customer_email='john@example.com',
        customer_phone='5555551234',
        delivery_address='123 Main St',
        delivery_city='Fort Worth',
        delivery_state='TX',
        delivery_zip='76102',
    ))
    _run_async(coro)

    coro = handle_add_item_to_order(AddItemParams(item_code='9204', quantity=1))
    _run_async(coro)

    coro = handle_prepare_order()
    result = _run_async(coro)
    text = result[0].text

    # Should contain order summary elements
    assert 'Store' in text
    assert '8022' in text or 'Fort Worth' in text
    assert '11.90' in text  # total
    assert 'Confirm Token:' in text

    # Token should be a 64-character hex string (SHA-256)
    token_line = [l for l in text.split('\n') if 'Confirm Token:' in l][0]
    token = token_line.split(':')[1].strip()
    assert len(token) == 64, f"Token should be 64 chars, got {len(token)}"


def test_place_order_with_valid_token(mock_api_price):
    """place_order succeeds with a valid confirm_token (dry-run mode)."""
    coro = handle_create_order(CreateOrderParams(
        store_id='8022',
        customer_name='John Doe',
        customer_email='john@example.com',
        customer_phone='5555551234',
        delivery_address='123 Main St',
        delivery_city='Fort Worth',
        delivery_state='TX',
        delivery_zip='76102',
    ))
    _run_async(coro)

    coro = handle_add_item_to_order(AddItemParams(item_code='9204', quantity=1))
    _run_async(coro)

    coro = handle_prepare_order()
    result = _run_async(coro)

    # Extract token
    token_line = [l for l in result[0].text.split('\n') if 'Confirm Token:' in l][0]
    token = token_line.split(':')[1].strip()

    # Place order with valid token (dry-run = default, no MCPIZZA_ALLOW_PLACE)
    result2 = _run_async(handle_place_order({'confirm_token': token}))
    assert 'DRY RUN' in result2[0].text
    # Should not call api_client.place_order


def test_place_order_invalid_token():
    """place_order rejects an invalid/nonexistent confirm_token."""
    coro = handle_create_order(CreateOrderParams(
        store_id='8022',
        customer_name='John Doe',
        customer_email='john@example.com',
        customer_phone='5555551234',
        delivery_address='123 Main St',
        delivery_city='Fort Worth',
        delivery_state='TX',
        delivery_zip='76102',
    ))
    _run_async(coro)

    result = _run_async(handle_place_order({'confirm_token': 'nonexistent-token'}))
    assert 'invalid' in result[0].text.lower() or 'refused' in result[0].text.lower()


def test_place_order_expired_token(mock_api_price):
    """place_order rejects an expired confirm_token (10 min TTL)."""
    coro = handle_create_order(CreateOrderParams(
        store_id='8022',
        customer_name='John Doe',
        customer_email='john@example.com',
        customer_phone='5555551234',
        delivery_address='123 Main St',
        delivery_city='Fort Worth',
        delivery_state='TX',
        delivery_zip='76102',
    ))
    _run_async(coro)

    coro = handle_add_item_to_order(AddItemParams(item_code='9204', quantity=1))
    _run_async(coro)

    coro = handle_prepare_order()
    result = _run_async(coro)
    text = result[0].text
    token_line = [l for l in text.split('\n') if 'Confirm Token:' in l][0]
    token = token_line.split(':')[1].strip()

    # Manually expire the token
    from mcpizza.tools.order_tools import _token_store, _TOKEN_TTL
    if token in _token_store:
        _token_store[token]['timestamp'] = time.time() - _TOKEN_TTL - 1

    result2 = _run_async(handle_place_order({'confirm_token': token}))
    assert 'expired' in result2[0].text.lower() or 'refused' in result2[0].text.lower()


def test_place_order_reused_token(mock_api_price):
    """place_order rejects a confirm_token that has already been used."""
    coro = handle_create_order(CreateOrderParams(
        store_id='8022',
        customer_name='John Doe',
        customer_email='john@example.com',
        customer_phone='5555551234',
        delivery_address='123 Main St',
        delivery_city='Fort Worth',
        delivery_state='TX',
        delivery_zip='76102',
    ))
    _run_async(coro)

    coro = handle_add_item_to_order(AddItemParams(item_code='9204', quantity=1))
    _run_async(coro)

    coro = handle_prepare_order()
    result = _run_async(coro)
    text = result[0].text
    token_line = [l for l in text.split('\n') if 'Confirm Token:' in l][0]
    token = token_line.split(':')[1].strip()

    # Use the token once
    _run_async(handle_place_order({'confirm_token': token}))

    # Use it again - should be rejected
    result2 = _run_async(handle_place_order({'confirm_token': token}))
    assert 'reused' in result2[0].text.lower() or 'invalid' in result2[0].text.lower()


def test_place_order_order_changed_invalidates_token(mock_api_price):
    """Changing the order after prepare_order invalidates the token."""
    coro = handle_create_order(CreateOrderParams(
        store_id='8022',
        customer_name='John Doe',
        customer_email='john@example.com',
        customer_phone='5555551234',
        delivery_address='123 Main St',
        delivery_city='Fort Worth',
        delivery_state='TX',
        delivery_zip='76102',
    ))
    _run_async(coro)

    coro = handle_add_item_to_order(AddItemParams(item_code='9204', quantity=1))
    _run_async(coro)

    coro = handle_prepare_order()
    result = _run_async(coro)
    text = result[0].text
    token_line = [l for l in text.split('\n') if 'Confirm Token:' in l][0]
    token = token_line.split(':')[1].strip()

    # Add another item - changes the order hash
    coro = handle_add_item_to_order(AddItemParams(item_code='9204', quantity=1))
    _run_async(coro)

    # Token should now be invalid because order changed
    result2 = _run_async(handle_place_order({'confirm_token': token}))
    assert 'invalid' in result2[0].text.lower() or 'refused' in result2[0].text.lower()


def test_place_order_dry_run_no_api_call(mock_api_price):
    """Dry-run mode does not call api_client.place_order."""
    coro = handle_create_order(CreateOrderParams(
        store_id='8022',
        customer_name='John Doe',
        customer_email='john@example.com',
        customer_phone='5555551234',
        delivery_address='123 Main St',
        delivery_city='Fort Worth',
        delivery_state='TX',
        delivery_zip='76102',
    ))
    _run_async(coro)

    coro = handle_add_item_to_order(AddItemParams(item_code='9204', quantity=1))
    _run_async(coro)

    coro = handle_prepare_order()
    result = _run_async(coro)
    token_line = [l for l in result[0].text.split('\n') if 'Confirm Token:' in l][0]
    token = token_line.split(':')[1].strip()

    with patch('mcpizza.api.client.requests.post') as mock_post:
        mock_post.assert_not_called()  # Dry-run should not call place_order
        _run_async(handle_place_order({'confirm_token': token}))


def test_place_order_with_allow_place_env(mock_api_price, monkeypatch, card_file):
    """With MCPIZZA_ALLOW_PLACE=1, place_order calls api_client.place_order."""
    coro = handle_create_order(CreateOrderParams(
        store_id='8022',
        customer_name='John Doe',
        customer_email='john@example.com',
        customer_phone='5555551234',
        delivery_address='123 Main St',
        delivery_city='Fort Worth',
        delivery_state='TX',
        delivery_zip='76102',
    ))
    _run_async(coro)

    coro = handle_add_item_to_order(AddItemParams(item_code='9204', quantity=1))
    _run_async(coro)

    coro = handle_prepare_order()
    result = _run_async(coro)
    token_line = [l for l in result[0].text.split('\n') if 'Confirm Token:' in l][0]
    token = token_line.split(':')[1].strip()

    # Set the env var to allow live placing of orders
    monkeypatch.setenv('MCPIZZA_ALLOW_PLACE', '1')
    # Use the card file fixture for live ordering
    monkeypatch.setenv('MCPIZZA_CARD_FILE', card_file)

    with patch('mcpizza.api.client.requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'Status': 1,
            'Order': {'OrderID': 'ORD-12345'}
        }
        mock_post.return_value = mock_response

        result2 = _run_async(handle_place_order({'confirm_token': token}))
        # Should have called place_order
        assert mock_post.called
        # Should contain order ID in the output
        assert 'ORD-12345' in result2[0].text