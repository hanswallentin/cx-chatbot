from typing import Optional

from pydantic import BaseModel, Field


class Customer(BaseModel):
    customer_id: int
    name: str
    email: str
    created_at: str


class Book(BaseModel):
    book_id: int
    title: str
    author: str
    isbn: str
    price: float
    stock_qty: int


class OrderLineItem(BaseModel):
    id: int
    order_id: int
    customer_id: int
    book_id: int
    title: str
    quantity: int
    status: str
    order_date: str
    tracking_number: Optional[str] = None


class Order(BaseModel):
    order_id: int
    customer_id: int
    # Overall status: the shared status if every line item agrees, else "mixed".
    status: str
    items: list[OrderLineItem]


class ReturnRequest(BaseModel):
    customer_id: int
    item_id: Optional[int] = None
    reason: str = Field(..., min_length=1)


class ErrorResponse(BaseModel):
    detail: str
