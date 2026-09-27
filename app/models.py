from typing import List
from dataclasses import dataclass, field


@dataclass
class OrderItem:
    sku: str
    quantity: int


@dataclass
class Order:
    order_id: int
    customer_id: int
    items: List[OrderItem]
    status: str = "pending"
