"""Error paths on the order/payment route must not leak card or order data."""
import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from mcpizza.errors import safe_error, safe_status_summary, OrderError
from mcpizza.tools.order_tools import (
    handle_create_order, handle_add_item_to_order, handle_prepare_order, handle_place_order,
)
from mcpizza.models.params import CreateOrderParams, AddItemParams
from mcpizza.services import order_service
from tests.test_phase2 import mock_api_price, card_file, reset_token_store  # noqa: F401  (fixtures)

CARD = '4111111111111111'
SECRET_TEXT = f"POST https://order.dominos.com/power/place-order body={{'Number': '{CARD}', 'SecurityCode': '123'}}"


def _run(coro):
    return asyncio.run(coro)


def _prepare_token():
    _run(handle_create_order(CreateOrderParams(
        store_id='8022', customer_name='John Doe', customer_email='john@example.com',
        customer_phone='5555551234', delivery_address='123 Main St', delivery_city='Fort Worth',
        delivery_state='TX', delivery_zip='76102')))
    _run(handle_add_item_to_order(AddItemParams(item_code='9204', quantity=1)))
    text = _run(handle_prepare_order())[0].text
    line = [l for l in text.split('\n') if 'Confirm Token:' in l][0]
    return line.split(':')[1].strip()


def test_safe_error_categories():
    assert 'timed out' in safe_error(requests.exceptions.Timeout(SECRET_TEXT))
    assert 'connect' in safe_error(requests.exceptions.ConnectionError(SECRET_TEXT))
    resp = MagicMock(status_code=403)
    assert safe_error(requests.exceptions.HTTPError(SECRET_TEXT, response=resp)) == "Domino's returned HTTP 403"
    assert safe_error(OrderError('No active order')) == 'No active order'
    out = safe_error(ValueError(SECRET_TEXT))
    assert CARD not in out and 'ValueError' in out


def test_status_summary_does_not_echo_body():
    body = {'Status': -1, 'Order': {'StatusItems': [{'Code': 'BadAddress'}], 'Address': {'Street': '123 Main St'}}}
    out = safe_status_summary(body)
    assert 'BadAddress' in out and '123 Main St' not in out


def test_place_failure_leaks_nothing_and_clears_card(mock_api_price, monkeypatch, card_file):
    token = _prepare_token()
    monkeypatch.setenv('MCPIZZA_ALLOW_PLACE', '1')
    monkeypatch.setenv('MCPIZZA_CARD_FILE', card_file)
    with patch('mcpizza.services.payment_service.api_client') as client:
        client.price_order.return_value = {'Status': 1, 'Order': {'Amounts': {'Customer': 11.9}}}
        client.place_order.side_effect = requests.exceptions.HTTPError(
            SECRET_TEXT, response=MagicMock(status_code=500))
        text = _run(handle_place_order({'confirm_token': token}))[0].text
    assert CARD not in text and 'SecurityCode' not in text and 'place-order body' not in text
    assert 'HTTP 500' in text
    assert order_service.get_current_order().data['Payments'] == []


def test_price_exception_and_rejection_do_not_echo(mock_api_price, monkeypatch, card_file):
    token = _prepare_token()
    monkeypatch.setenv('MCPIZZA_ALLOW_PLACE', '1')
    monkeypatch.setenv('MCPIZZA_CARD_FILE', card_file)
    with patch('mcpizza.services.payment_service.api_client') as client:
        client.price_order.return_value = {
            'Status': -1, 'Order': {'StatusItems': [{'Code': 'Bad'}], 'Address': {'Street': '123 Main St'}}}
        text = _run(handle_place_order({'confirm_token': token}))[0].text
    assert '123 Main St' not in text and 'Bad' in text
    token = _prepare_token()
    with patch('mcpizza.services.payment_service.api_client') as client:
        client.price_order.side_effect = RuntimeError(SECRET_TEXT)
        text = _run(handle_place_order({'confirm_token': token}))[0].text
    assert CARD not in text and 'RuntimeError' in text


def test_success_also_clears_card(mock_api_price, monkeypatch, card_file):
    token = _prepare_token()
    monkeypatch.setenv('MCPIZZA_ALLOW_PLACE', '1')
    monkeypatch.setenv('MCPIZZA_CARD_FILE', card_file)
    with patch('mcpizza.services.payment_service.api_client') as client:
        client.price_order.return_value = {'Status': 1, 'Order': {'Amounts': {'Customer': 11.9}}}
        client.place_order.return_value = {'Status': 1, 'Order': {'OrderID': 'ORD-1'}}
        text = _run(handle_place_order({'confirm_token': token}))[0].text
    assert 'ORD-1' in text
    assert order_service.get_current_order().data['Payments'] == []
