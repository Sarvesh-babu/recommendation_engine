from typing import Optional
from pydantic import BaseModel


class TransactionRow(BaseModel):
    transaction_id: str
    customer_id: str
    product_id: str
    quantity: float
    price: float
    timestamp: str


class CustomerRow(BaseModel):
    customer_id: str
    segment: Optional[str] = None
    signup_date: Optional[str] = None


class ProductRow(BaseModel):
    product_id: str
    category: Optional[str] = None
    brand: Optional[str] = None
    price: Optional[float] = None


UNIVERSAL_REQUIRED_COLUMNS = {
    "transactions": ["transaction_id", "customer_id", "product_id", "quantity", "price", "timestamp"],
    "customers": ["customer_id"],
    "products": ["product_id"],
}

OPTIONAL_COLUMNS = {
    "sessions": ["session_id", "customer_id", "product_id", "timestamp"],
    "returns": ["transaction_id", "product_id", "customer_id", "return_date"],
    "search_logs": ["customer_id", "query", "timestamp"],
    "promotions": ["product_id", "discount_pct", "start_date", "end_date"],
}


class TrainRequest(BaseModel):
    personalized: Optional[str] = None
    fbt: Optional[str] = None
    popular: Optional[str] = None


class CartRequest(BaseModel):
    product_ids: list[str]
    customer_label: Optional[str] = None
