from dataclasses import dataclass

from app.models.menu import MenuItem
from app.services.errors import OrderError

MAX_ITEMS_PER_ORDER = 20
MAX_QUANTITY_PER_ITEM = 20


@dataclass(frozen=True)
class PricedLine:
    menu_item_id: int
    item_name: str
    unit_price_paise: int
    quantity: int
    line_total_paise: int
    stock_tracked: bool


@dataclass(frozen=True)
class PricedOrder:
    lines: list[PricedLine]
    subtotal_paise: int
    discount_paise: int
    tax_paise: int
    total_paise: int


def normalize_requested_items(raw_items):
    """Validate and combine repeated menu item IDs. Returns [(id, quantity), ...]."""
    if not isinstance(raw_items, list) or not raw_items:
        raise OrderError("INVALID_ITEMS", "Order must contain at least one item.")

    combined = {}
    for item in raw_items:
        if not isinstance(item, dict):
            raise OrderError("INVALID_ITEM", "Each item must be an object.")

        menu_item_id = item.get("menu_item_id")
        quantity = item.get("quantity")

        if isinstance(menu_item_id, bool) or not isinstance(menu_item_id, int) or menu_item_id < 1:
            raise OrderError("INVALID_MENU_ITEM", "menu_item_id must be a positive integer.")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise OrderError("INVALID_QUANTITY", "quantity must be a positive integer.")

        combined[menu_item_id] = combined.get(menu_item_id, 0) + quantity
        if combined[menu_item_id] > MAX_QUANTITY_PER_ITEM:
            raise OrderError(
                "QUANTITY_TOO_LARGE",
                f"Maximum quantity per item is {MAX_QUANTITY_PER_ITEM}.",
            )

    if len(combined) > MAX_ITEMS_PER_ORDER:
        raise OrderError("TOO_MANY_ITEMS", f"Maximum distinct items per order is {MAX_ITEMS_PER_ORDER}.")

    return list(combined.items())


def price_order(requested_items):
    """Fetch trusted prices and calculate a total. Never accepts prices from the client."""
    menu_ids = [menu_id for menu_id, _ in requested_items]
    menu_items = MenuItem.query.filter(MenuItem.id.in_(menu_ids)).all()
    by_id = {item.id: item for item in menu_items}

    if len(by_id) != len(menu_ids):
        raise OrderError("MENU_ITEM_NOT_FOUND", "One or more menu items no longer exist.", 404)

    lines = []
    subtotal = 0

    for menu_item_id, quantity in requested_items:
        item = by_id[menu_item_id]

        if not item.is_available:
            raise OrderError("ITEM_UNAVAILABLE", f"'{item.name}' is currently unavailable.", 409)

        if item.stock_quantity is not None:
            available = item.stock_quantity - item.reserved_quantity
            if available < quantity:
                if available <= 0:
                    raise OrderError("INSUFFICIENT_STOCK", f"'{item.name}' is sold out.", 409)
                raise OrderError(
                    "INSUFFICIENT_STOCK",
                    f"Only {available} of '{item.name}' left.",
                    409,
                )

        line_total = item.price_paise * quantity
        subtotal += line_total
        lines.append(PricedLine(
            menu_item_id=item.id,
            item_name=item.name,
            unit_price_paise=item.price_paise,
            quantity=quantity,
            line_total_paise=line_total,
            stock_tracked=item.stock_quantity is not None,
        ))

    # Keep the first release's pricing deliberately simple. Taxes/discounts can be added centrally.
    discount = 0
    tax = 0
    return PricedOrder(
        lines=lines,
        subtotal_paise=subtotal,
        discount_paise=discount,
        tax_paise=tax,
        total_paise=subtotal - discount + tax,
    )
