# Order Service

A small FastAPI service simulating an e-commerce order backend. It is used as a realistic incident demo for the **Incident Commander** workshop.

## Running the app

```bash
pip install fastapi uvicorn httpx pytest
uvicorn app.main:app --reload
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/orders` | Create a new order |
| `GET` | `/orders/{order_id}` | Fetch an order by ID |
| `GET` | `/inventory/{sku}` | Check stock for a SKU |
| `POST` | `/inventory/{sku}/restock?quantity=N` | Add stock for a SKU |

### Create order — example request

```json
{
  "customer_id": 42,
  "items": [
    {"sku": "WIDGET-A", "quantity": 2}
  ]
}
```

## Running tests

```bash
pytest tests/ -v
```

## The seeded incident

The repository contains a latent bug that surfaces when `POST /orders` is called with an **empty `items` list** and a `priority` field:

```bash
curl -X POST http://localhost:8000/orders \
     -H "Content-Type: application/json" \
     -d '{"customer_id": 42, "items": [], "priority": "high"}'
# → HTTP 500  IndexError: list index out of range
```

### Root cause

Two commits interact badly:

1. **"Refactor: check inventory before field validation"** — moved the inventory stock check *above* the empty-items guard.
2. **"Add priority field to orders"** — added priority-tagging logic that dereferences `items[0]`, assuming (correctly under the original ordering) that the non-empty check already ran.

Neither commit is buggy in isolation. The regression only appears when both are present.

The captured incident is recorded in [`incident/incident_log.json`](incident/incident_log.json).
