"""
Happy-path tests for the Order Service.
Run with: pytest tests/
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app, orders, _next_order_id
import app.inventory as inv


@pytest.fixture(autouse=True)
def reset_state():
    """Reset in-memory state before each test."""
    orders.clear()
    inv.inventory.update({
        "WIDGET-A": 100,
        "WIDGET-B": 50,
        "GADGET-X": 25,
        "GADGET-Y": 0,
    })
    # Reset order ID counter
    import app.main as main_module
    main_module._next_order_id = 1
    yield


client = TestClient(app)


def test_create_order_success():
    response = client.post("/orders", json={
        "customer_id": 1,
        "items": [{"sku": "WIDGET-A", "quantity": 3}],
    })
    assert response.status_code == 201
    data = response.json()
    assert data["order_id"] == 1
    assert data["status"] == "pending"


def test_get_order_success():
    # First create one
    client.post("/orders", json={
        "customer_id": 7,
        "items": [{"sku": "WIDGET-B", "quantity": 2}],
    })
    response = client.get("/orders/1")
    assert response.status_code == 200
    data = response.json()
    assert data["customer_id"] == 7
    assert data["items"][0]["sku"] == "WIDGET-B"
    assert data["items"][0]["quantity"] == 2


def test_get_order_not_found():
    response = client.get("/orders/999")
    assert response.status_code == 404


def test_check_inventory():
    response = client.get("/inventory/WIDGET-A")
    assert response.status_code == 200
    assert response.json()["available"] == 100


def test_inventory_decremented_after_order():
    client.post("/orders", json={
        "customer_id": 5,
        "items": [{"sku": "GADGET-X", "quantity": 10}],
    })
    response = client.get("/inventory/GADGET-X")
    assert response.json()["available"] == 15


def test_restock():
    response = client.post("/inventory/GADGET-Y/restock?quantity=30")
    assert response.status_code == 200
    assert response.json()["available"] == 30


def test_insufficient_stock_returns_409():
    response = client.post("/orders", json={
        "customer_id": 3,
        "items": [{"sku": "GADGET-Y", "quantity": 999}],
    })
    assert response.status_code == 409
