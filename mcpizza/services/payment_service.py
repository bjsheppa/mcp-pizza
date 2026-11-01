"""
Payment processing and order placement services
"""
import os
import json
import re
import stat
from typing import Dict, Any

from mcpizza.api.client import api_client
from mcpizza.errors import safe_error, safe_status_summary
from mcpizza.services.order_service import get_current_order


def _detect_card_type(card_number: str) -> str:
    """Detect card type from the card number prefix.

    Args:
        card_number: Credit card number as a string.

    Returns:
        Card type string: 'Visa', 'Mastercard', 'Amex', 'Discover', or 'Unknown'.
    """
    number = card_number.strip()
    if number.startswith('4'):
        return 'Visa'
    if number.startswith('34') or number.startswith('37'):
        return 'Amex'
    if re.match(r'^5[1-5]', number) or re.match(r'^22[2-9]\d|^2[7-9]\d|^27[0-2]', number):
        return 'Mastercard'
    if number.startswith('6011') or re.match(r'^65', number):
        return 'Discover'
    return 'Unknown'


def _load_card_from_file(card_file_path: str) -> Dict[str, Any]:
    """Load card data from a JSON file.

    The file must contain keys: number, expiry, cvv, zip.
    Requires file permissions to be 600 or 400 (owner-only read/write).
    Raises ValueError if permissions are too permissive.

    Args:
        card_file_path: Path to the JSON card file.

    Returns:
        Dictionary with card data (number, expiry, cvv, zip).

    Raises:
        ValueError: If the file permissions allow group/other access.
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    path = os.path.normpath(card_file_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Card file not found: {path}")

    # Check permissions: require mode 600 or 400
    file_stat = os.stat(path)
    mode = file_stat.st_mode & 0o777
    # Allow only 600 (rw-------) or 400 (r-------)
    if mode & 0o077:  # group or other has any permission
        raise ValueError(
            f"Card file has insecure permissions: {oct(mode)}. "
            "Require mode 600 or 400 (owner-only read/write)."
        )

    with open(path, 'r') as f:
        card_data = json.load(f)

    # Validate required keys
    required = ['number', 'expiry', 'cvv', 'zip']
    missing = [k for k in required if k not in card_data]
    if missing:
        raise ValueError(f"Card file is missing required keys: {', '.join(missing)}")

    return card_data


def place_order(payment_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Place a real order with payment.

    ⚠️ WARNING: This charges a real credit card!

    Args:
        payment_info: Dictionary with card_file_path key pointing to
                      a JSON file containing card data (number, expiry, cvv, zip).

    Returns:
        Order placement result with status and details

    Raises:
        ValueError: If card file is missing, unreadable, or has bad permissions.
    """
    current_order = get_current_order()

    if current_order is None:
        return {
            'success': False,
            'error': 'No active order. Create an order first.'
        }

    result = {'success': False, 'steps': []}

    # Step 1: Load card data from file
    card_file_path = payment_info.get('card_file_path')
    if not card_file_path:
        return {
            'success': False,
            'error': 'No card file path provided. Set MCPIZZA_CARD_FILE env var or '
                     'pass card_file_path in payment_info.'
        }

    try:
        card_data = _load_card_from_file(card_file_path)
    except (FileNotFoundError, ValueError) as e:
        # Never include card data in the error message
        return {
            'success': False,
            'error': str(e)
        }

    # Step 2: Price the order (validate and get totals)
    try:
        result['steps'].append('Validating and pricing order...')

        # Update order data with customer info
        current_order.data.update(
            StoreID=current_order.store.id,
            Email=current_order.customer.email,
            FirstName=current_order.customer.first_name,
            LastName=current_order.customer.last_name,
            Phone=current_order.customer.phone
        )

        # Call pricing API
        price_data = api_client.price_order(current_order.data)

        if price_data.get('Status') == -1:
            result['error'] = f"Pricing failed: {safe_status_summary(price_data)}"
            return result

        # Update order with pricing info
        for key, value in price_data.get('Order', {}).items():
            if value or not isinstance(value, list):
                current_order.data[key] = value

        amounts = current_order.data.get('Amounts', {})
        result['steps'].append(f"Order validated - Subtotal: ${amounts.get('Customer', 0):.2f}")
        result['pricing'] = amounts

    except Exception as price_error:
        result['error'] = f"Pricing failed: {safe_error(price_error)}"
        return result

    # Step 3: Add payment information
    result['steps'].append('Adding payment information...')

    current_order.data['Payments'] = [{
        'Type': 'CreditCard',
        'Number': card_data.get('number'),
        'Expiration': card_data.get('expiry'),
        'Amount': current_order.data['Amounts'].get('Customer', 0),
        'CardType': _detect_card_type(card_data.get('number', '')),
        'SecurityCode': card_data.get('cvv'),
        'PostalCode': card_data.get('zip')
    }]

    result['steps'].append('Payment added')

    # Step 4: Place the order
    try:  # card is removed from the order object in the finally block below
        result['steps'].append('Submitting order to Domino\'s...')

        response = api_client.place_order(current_order.data)

        # Check if order was actually successful
        if response.get('Status') == -1:
            result['success'] = False
            result['rejected'] = True
            result['status'] = response.get('Status')
            result['status_items'] = response.get('Order', {}).get('StatusItems', [])
            result['error'] = 'ORDER REJECTED BY DOMINO\'S'
        else:
            result['success'] = True
            result['order_id'] = response.get('Order', {}).get('OrderID')
            result['status'] = response.get('Status')
            result['estimated_wait_minutes'] = response.get('Order', {}).get('EstimatedWaitMinutes')
            result['steps'].append('ORDER PLACED SUCCESSFULLY!')

    except Exception as place_error:
        result['error'] = f"ORDER FAILED: {safe_error(place_error)}"
        result['possible_causes'] = [
            'Invalid payment information',
            'Store not accepting online orders',
            'Invalid items in order',
            'API limitations',
            'CAPTCHA verification required'
        ]
    finally:
        # Never leave card data on the in-memory order after a placement attempt
        current_order.data['Payments'] = []

    return result