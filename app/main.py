from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from app.models import Order, OrderItem
from app import inventory as inv

app = FastAPI(title="Order Service")

# In-memory order store
orders: dict[int, Order] = {}
_next_order_id = 1


# ---------- Request schemas ----------

class ItemRequest(BaseModel):
    sku: str
    quantity: int


class CreateOrderRequest(BaseModel):
    customer_id: int
    items: List[ItemRequest]


# ---------- Endpoints ----------

@app.post("/orders", status_code=201)
def create_order(req: CreateOrderRequest):
    global _next_order_id

    # 1. Check inventory availability first so we fail fast on stock issues
    #    before doing heavier field validation work.
    for item in req.items:
        available = inv.get_stock(item.sku)
        if available < item.quantity:
            raise HTTPException(
                status_code=409,
                detail=f"insufficient stock for {item.sku}: have {available}, need {item.quantity}",
            )

    # 2. Validate required fields are present and sensible
    if not req.items:
        raise HTTPException(status_code=400, detail="items list must not be empty")

    for item in req.items:
        if item.quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"quantity for {item.sku} must be positive",
            )

    # 3. Reserve stock and persist order
    for item in req.items:
        inv.reserve_stock(item.sku, item.quantity)

    order_id = _next_order_id
    _next_order_id += 1

    order = Order(
        order_id=order_id,
        customer_id=req.customer_id,
        items=[OrderItem(sku=i.sku, quantity=i.quantity) for i in req.items],
    )
    orders[order_id] = order

    return {"order_id": order.order_id, "status": order.status}


@app.get("/orders/{order_id}")
def get_order(order_id: int):
    order = orders.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "status": order.status,
        "items": [{"sku": i.sku, "quantity": i.quantity} for i in order.items],
    }


@app.get("/inventory/{sku}")
def check_inventory(sku: str):
    stock = inv.get_stock(sku)
    return {"sku": sku, "available": stock}


@app.post("/inventory/{sku}/restock")
def restock(sku: str, quantity: int):
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be positive")
    new_level = inv.restock(sku, quantity)
    return {"sku": sku, "available": new_level}
