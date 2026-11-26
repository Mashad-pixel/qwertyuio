def serialize_order_item(item):
    return {
        "menu_item_id": item.menu_item_id,
        "item_name": item.item_name_snapshot,
        "unit_price_paise": item.unit_price_snapshot_paise,
        "quantity": item.quantity,
        "line_total_paise": item.line_total_paise,
    }


def serialize_order(order, raw_token=None):
    data = {
        "id": order.id,
        "order_number": order.order_number,
        "order_status": order.order_status,
        "payment_status": order.payment_status,
        "subtotal_paise": order.subtotal_paise,
        "discount_paise": order.discount_paise,
        "tax_paise": order.tax_paise,
        "total_paise": order.total_paise,
        "items": [serialize_order_item(item) for item in order.items],
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "instructions": order.instructions,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }

    # The raw token is returned only when the order is first created.
    if raw_token is not None:
        data["tracking_token"] = raw_token

    return data


def serialize_order_for_admin(order, student):
    data = serialize_order(order)
    data["student"] = (
        {"id": student.id, "name": student.name, "email": student.email}
        if student is not None
        else None
    )
    return data


def serialize_tracking(order):
    # Status only. Items, totals, and tokens are not included.
    return {
        "order_number": order.order_number,
        "order_status": order.order_status,
        "payment_status": order.payment_status,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }


def serialize_status_history(rows):
    return [
        {
            "previous_status": row.previous_status,
            "new_status": row.new_status,
            "changed_by": row.changed_by,
            "changed_at": row.changed_at.isoformat(),
            "notes": row.notes,
        }
        for row in rows
    ]
