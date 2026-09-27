# In-memory inventory store
# SKU -> available quantity
inventory: dict[str, int] = {
    "WIDGET-A": 100,
    "WIDGET-B": 50,
    "GADGET-X": 25,
    "GADGET-Y": 0,
}


def get_stock(sku: str) -> int:
    return inventory.get(sku, 0)


def reserve_stock(sku: str, quantity: int) -> bool:
    """Deduct quantity from stock. Returns False if insufficient stock."""
    available = inventory.get(sku, 0)
    if available < quantity:
        return False
    inventory[sku] -= quantity
    return True


def restock(sku: str, quantity: int) -> int:
    """Add quantity to stock. Returns new stock level."""
    inventory[sku] = inventory.get(sku, 0) + quantity
    return inventory[sku]
