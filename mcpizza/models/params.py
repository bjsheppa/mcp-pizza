"""
Pydantic models for MCP Pizza tools
"""
import re
from typing import Optional
from pydantic import BaseModel, Field
from pydantic import field_validator


def _validate_store_id(v):
    """Store ID must be 3-6 digits."""
    if not re.match(r'^\d{3,6}$', v):
        raise ValueError("store_id must be 3-6 digits")
    return v


def _validate_state(v):
    """State must be exactly 2 letters."""
    if not re.match(r'^[A-Za-z]{2}$', v):
        raise ValueError("state must be 2 letters")
    return v


def _validate_zip(v):
    """ZIP code must be 5 digits or 5+4 format."""
    if not re.match(r'^\d{5}(-\d{4})?$', v):
        raise ValueError("zip must be in format 12345 or 12345-1234")
    return v


def _validate_phone(v):
    """Phone must be exactly 10 digits."""
    if not re.match(r'^\d{10}$', v):
        raise ValueError("phone must be 10 digits")
    return v


def _validate_email(v):
    """Email must have basic format (local@domain.tld)."""
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', v):
        raise ValueError("email must have basic format local@domain.tld")
    return v


def _validate_quantity(v):
    """Quantity must be between 1 and 20."""
    if not (1 <= v <= 20):
        raise ValueError("quantity must be between 1 and 20")
    return v


def _validate_order_type(v):
    """Order type must be 'Delivery' or 'Carryout'."""
    if v not in ('Delivery', 'Carryout'):
        raise ValueError("order_type must be 'Delivery' or 'Carryout'")
    return v


def _validate_code(v, pattern):
    """Generic code validator: 1-24 alphanumeric or underscore characters."""
    if not re.match(r'^[A-Za-z0-9_]{1,24}$', v):
        raise ValueError("code must be 1-24 alphanumeric or underscore characters")
    return v


class StoreSearchParams(BaseModel):
    """Parameters for finding stores"""
    query: str = Field(description="Address or zip code to search for stores")


class StoreInfoParams(BaseModel):
    """Parameters for getting store information"""
    store_id: str = Field(description="Store ID to get information for")

    @field_validator('store_id')
    def validate_store_id(cls, v):
        return _validate_store_id(v)


class MenuSearchParams(BaseModel):
    """Parameters for searching menu items"""
    store_id: str = Field(description="Store ID to search menu for")
    query: Optional[str] = Field(default=None, description="Search query (optional)")
    category: Optional[str] = Field(default=None, description="Category filter (e.g., 'Pizza', 'Wings', 'Sides')")


class CreateOrderParams(BaseModel):
    """Parameters for creating an order"""
    store_id: str = Field(description="Store ID to order from")
    customer_name: str = Field(description="Customer first and last name")
    customer_email: str = Field(description="Customer email address")
    customer_phone: str = Field(description="Customer phone number")
    delivery_address: str = Field(description="Delivery street address")
    delivery_city: str = Field(description="Delivery city")
    delivery_state: str = Field(description="Delivery state (2-letter code)")
    delivery_zip: str = Field(description="Delivery zip code")
    order_type: str = Field(default="Delivery", description="Order type: 'Delivery' or 'Carryout'")

    @field_validator('store_id')
    def validate_store_id(cls, v):
        return _validate_store_id(v)

    @field_validator('delivery_state')
    def validate_state(cls, v):
        return _validate_state(v)

    @field_validator('delivery_zip')
    def validate_zip(cls, v):
        return _validate_zip(v)

    @field_validator('customer_email')
    def validate_email(cls, v):
        return _validate_email(v)

    @field_validator('customer_phone')
    def validate_phone(cls, v):
        return _validate_phone(v)

    @field_validator('order_type')
    def validate_order_type(cls, v):
        return _validate_order_type(v)


class AddItemParams(BaseModel):
    """Parameters for adding an item to order"""
    item_code: str = Field(description="Menu item code")
    quantity: int = Field(default=1, description="Quantity to add")
    options: Optional[dict] = Field(default=None, description="Item customization options")

    @field_validator('item_code')
    def validate_item_code(cls, v):
        return _validate_code(v, r'^[A-Za-z0-9_]{1,24}$')

    @field_validator('quantity')
    def validate_quantity(cls, v):
        return _validate_quantity(v)


class AddPizzaParams(BaseModel):
    """Parameters for adding a customized pizza"""
    coupon_code: str = Field(description="Coupon code (e.g., '9204')")
    size: str = Field(default="12", description="Pizza size: 10, 12, 14, 16")
    crust: str = Field(default="NPAN", description="Crust type: NPAN (pan), HAND (hand tossed), THIN, etc.")
    toppings: list[str] = Field(description="List of topping codes (e.g., ['P', 'S'] for pepperoni and sausage)")

    @field_validator('coupon_code')
    def validate_coupon_code(cls, v):
        return _validate_code(v, r'^[A-Za-z0-9_]{1,24}$')