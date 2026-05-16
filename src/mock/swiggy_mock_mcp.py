"""
Local mock Swiggy Food MCP server for demo and development.

Implements all 14 food tools with realistic Bangalore data.
Speaks the same MCP protocol as mcp.swiggy.com/food — only the URL changes for prod.

Run:
    python src/mock/swiggy_mock_mcp.py

Then set in .env:
    SWIGGY_FOOD_MCP_URL=http://localhost:8001/mcp
"""

import json
import uuid
from copy import deepcopy
from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("swiggy-food-mock")


# ---------------------------------------------------------------------------
# Static demo data
# ---------------------------------------------------------------------------

_RESTAURANTS = [
    {
        "id": "r001",
        "name": "Domino's Pizza",
        "cuisine": "Pizza, Italian",
        "rating": 4.2,
        "delivery_time": "25-35 min",
        "min_order": 199,
        "location": "Koramangala, Bangalore",
        "is_open": True,
    },
    {
        "id": "r002",
        "name": "McDonald's",
        "cuisine": "Burgers, Fast Food",
        "rating": 4.0,
        "delivery_time": "20-30 min",
        "min_order": 149,
        "location": "Koramangala, Bangalore",
        "is_open": True,
    },
    {
        "id": "r003",
        "name": "Behrouz Biryani",
        "cuisine": "Biryani, Mughlai",
        "rating": 4.5,
        "delivery_time": "35-45 min",
        "min_order": 299,
        "location": "Koramangala, Bangalore",
        "is_open": True,
    },
    {
        "id": "r004",
        "name": "Fassos",
        "cuisine": "Wraps, Fast Food",
        "rating": 3.9,
        "delivery_time": "20-30 min",
        "min_order": 149,
        "location": "Koramangala, Bangalore",
        "is_open": True,
    },
]

_MENUS = {
    "r001": {
        "categories": [
            {
                "name": "Pizzas",
                "items": [
                    {"id": "p001", "name": "Margherita", "price": 249, "description": "Classic tomato sauce and mozzarella"},
                    {"id": "p002", "name": "Pepperoni", "price": 349, "description": "Loaded with pepperoni slices"},
                    {"id": "p003", "name": "Veggie Paradise", "price": 299, "description": "Capsicum, onion, olives, mushroom"},
                    {"id": "p004", "name": "Chicken BBQ", "price": 399, "description": "Grilled chicken with smoky BBQ sauce"},
                ],
            },
            {
                "name": "Sides",
                "items": [
                    {"id": "p005", "name": "Garlic Bread", "price": 99, "description": "Toasted with herb butter"},
                    {"id": "p006", "name": "Choco Lava Cake", "price": 89, "description": "Warm chocolate cake with molten centre"},
                ],
            },
            {
                "name": "Beverages",
                "items": [
                    {"id": "p007", "name": "Coke 250ml", "price": 59},
                    {"id": "p008", "name": "Sprite 250ml", "price": 59},
                ],
            },
        ]
    },
    "r002": {
        "categories": [
            {
                "name": "Burgers",
                "items": [
                    {"id": "m001", "name": "McAloo Tikki", "price": 89, "description": "Crispy aloo tikki patty"},
                    {"id": "m002", "name": "McChicken", "price": 169, "description": "Crispy chicken patty with mayo"},
                    {"id": "m003", "name": "Big Mac", "price": 219, "description": "Double beef patty, special sauce"},
                ],
            },
            {
                "name": "Combos",
                "items": [
                    {"id": "m004", "name": "McAloo Tikki Combo", "price": 179, "description": "Burger + Fries + Drink"},
                    {"id": "m005", "name": "McChicken Combo", "price": 259, "description": "Burger + Fries + Drink"},
                ],
            },
            {
                "name": "Sides & Desserts",
                "items": [
                    {"id": "m006", "name": "Fries (Medium)", "price": 89},
                    {"id": "m007", "name": "McFlurry Oreo", "price": 119},
                ],
            },
        ]
    },
    "r003": {
        "categories": [
            {
                "name": "Biryani",
                "items": [
                    {"id": "b001", "name": "Chicken Biryani (Regular)", "price": 349, "description": "Slow-cooked dum biryani"},
                    {"id": "b002", "name": "Chicken Biryani (Large)", "price": 499, "description": "Serves 2"},
                    {"id": "b003", "name": "Mutton Biryani (Regular)", "price": 449, "description": "Tender mutton pieces"},
                    {"id": "b004", "name": "Veg Dum Biryani", "price": 299, "description": "Mixed vegetables in saffron rice"},
                ],
            },
            {
                "name": "Extras",
                "items": [
                    {"id": "b005", "name": "Raita", "price": 69},
                    {"id": "b006", "name": "Mirchi Salan", "price": 89},
                    {"id": "b007", "name": "Shorba Soup", "price": 79},
                ],
            },
        ]
    },
    "r004": {
        "categories": [
            {
                "name": "Wraps",
                "items": [
                    {"id": "f001", "name": "Chicken Tikka Wrap", "price": 189, "description": "Grilled chicken tikka in a soft wrap"},
                    {"id": "f002", "name": "Paneer Wrap", "price": 159, "description": "Spiced paneer with mint chutney"},
                    {"id": "f003", "name": "Egg Wrap", "price": 149, "description": "Egg bhurji with veggies"},
                ],
            },
            {
                "name": "Sides",
                "items": [
                    {"id": "f004", "name": "Piri Piri Fries", "price": 99},
                    {"id": "f005", "name": "Coleslaw", "price": 59},
                ],
            },
        ]
    },
}

_ADDRESSES = [
    {
        "id": "addr001",
        "label": "Home",
        "address": "123, 5th Cross, Koramangala 4th Block, Bangalore - 560034",
    },
    {
        "id": "addr002",
        "label": "Work",
        "address": "WeWork, Embassy Golf Links, Domlur, Bangalore - 560071",
    },
]

_COUPONS = [
    {"code": "SWIGGY50", "description": "50% off up to ₹100 on orders above ₹299"},
    {"code": "WELCOME100", "description": "₹100 off on first order above ₹499"},
    {"code": "FREESHIP", "description": "Free delivery on orders above ₹199"},
]

# ---------------------------------------------------------------------------
# Mutable in-process state (fine for a single-server demo)
# ---------------------------------------------------------------------------

_cart: dict = {"items": [], "restaurant_id": None, "applied_coupon": None}
_orders: dict = {}


def _cart_total() -> float:
    return sum(i["price"] * i["quantity"] for i in _cart["items"])


def _apply_discount(total: float) -> float:
    code = _cart.get("applied_coupon")
    if code == "SWIGGY50" and total >= 299:
        return min(100.0, total * 0.5)
    if code == "WELCOME100" and total >= 499:
        return 100.0
    return 0.0


def _find_item(restaurant_id: str, item_id: str) -> dict | None:
    for cat in _MENUS.get(restaurant_id, {}).get("categories", []):
        for item in cat["items"]:
            if item["id"] == item_id:
                return item
    return None


# ---------------------------------------------------------------------------
# Tools — Discover
# ---------------------------------------------------------------------------

@mcp.tool()
def get_addresses() -> str:
    """Get all saved delivery addresses for the authenticated Swiggy user."""
    return json.dumps({"addresses": _ADDRESSES})


@mcp.tool()
def search_restaurants(query: str = "", location: str = "Koramangala, Bangalore") -> str:
    """Find restaurants and enable food ordering for delivery.

    Args:
        query: Cuisine type, dish name, or restaurant name to filter by.
        location: Delivery location (area, city).
    """
    q = query.lower()
    results = [
        r for r in _RESTAURANTS
        if not q or q in r["name"].lower() or q in r["cuisine"].lower()
    ]
    return json.dumps({"restaurants": results, "location": location, "count": len(results)})


@mcp.tool()
def search_menu(query: str, restaurant_id: str = "") -> str:
    """Locate specific dishes and menu items for food delivery orders.

    Args:
        query: Dish name or keyword to search for.
        restaurant_id: Restrict search to one restaurant (optional).
    """
    q = query.lower()
    results = []
    scope = {restaurant_id: _MENUS[restaurant_id]} if restaurant_id in _MENUS else _MENUS
    for rid, menu in scope.items():
        rest = next((r for r in _RESTAURANTS if r["id"] == rid), {})
        for cat in menu.get("categories", []):
            for item in cat.get("items", []):
                if q in item["name"].lower() or q in item.get("description", "").lower():
                    results.append({
                        **item,
                        "restaurant_id": rid,
                        "restaurant_name": rest.get("name"),
                    })
    return json.dumps({"results": results, "count": len(results)})


@mcp.tool()
def get_restaurant_menu(restaurant_id: str) -> str:
    """Access the complete menu for a restaurant, organized by category.

    Args:
        restaurant_id: The restaurant ID from search_restaurants.
    """
    rest = next((r for r in _RESTAURANTS if r["id"] == restaurant_id), None)
    if not rest:
        return json.dumps({"error": f"Restaurant '{restaurant_id}' not found"})
    return json.dumps({"restaurant": rest, "menu": _MENUS.get(restaurant_id, {"categories": []})})


# ---------------------------------------------------------------------------
# Tools — Cart
# ---------------------------------------------------------------------------

@mcp.tool()
def get_food_cart() -> str:
    """Display current cart contents and total."""
    subtotal = _cart_total()
    discount = _apply_discount(subtotal)
    return json.dumps({
        "items": _cart["items"],
        "restaurant_id": _cart["restaurant_id"],
        "item_count": len(_cart["items"]),
        "subtotal": subtotal,
        "discount": discount,
        "total": subtotal - discount,
        "applied_coupon": _cart["applied_coupon"],
    })


@mcp.tool()
def update_food_cart(restaurant_id: str, item_id: str, quantity: int) -> str:
    """Add an item or modify its quantity in the cart. Set quantity=0 to remove.

    Args:
        restaurant_id: ID of the restaurant the item belongs to.
        item_id: ID of the menu item.
        quantity: New quantity (0 removes the item).
    """
    if _cart["restaurant_id"] and _cart["restaurant_id"] != restaurant_id and _cart["items"]:
        rest_name = next((r["name"] for r in _RESTAURANTS if r["id"] == _cart["restaurant_id"]), _cart["restaurant_id"])
        return json.dumps({
            "success": False,
            "error": f"Cart already has items from {rest_name}. Clear it first with flush_food_cart.",
        })

    item = _find_item(restaurant_id, item_id)
    if not item:
        return json.dumps({"success": False, "error": f"Item '{item_id}' not found in restaurant '{restaurant_id}'"})

    _cart["restaurant_id"] = restaurant_id
    existing = next((i for i in _cart["items"] if i["id"] == item_id), None)

    if existing:
        if quantity == 0:
            _cart["items"] = [i for i in _cart["items"] if i["id"] != item_id]
        else:
            existing["quantity"] = quantity
    elif quantity > 0:
        _cart["items"].append({**item, "quantity": quantity})

    if not _cart["items"]:
        _cart["restaurant_id"] = None

    return json.dumps({
        "success": True,
        "item": item["name"],
        "quantity": quantity,
        "cart_item_count": len(_cart["items"]),
        "subtotal": _cart_total(),
    })


@mcp.tool()
def flush_food_cart() -> str:
    """Remove all items from the cart and reset coupon."""
    _cart["items"].clear()
    _cart["restaurant_id"] = None
    _cart["applied_coupon"] = None
    return json.dumps({"success": True, "message": "Cart cleared"})


@mcp.tool()
def fetch_food_coupons() -> str:
    """Retrieve available discount coupons for the current cart."""
    return json.dumps({"coupons": _COUPONS})


@mcp.tool()
def apply_food_coupon(code: str) -> str:
    """Apply a discount coupon code to the cart.

    Args:
        code: The coupon code string (e.g. 'SWIGGY50').
    """
    matched = next((c for c in _COUPONS if c["code"] == code.upper()), None)
    if not matched:
        return json.dumps({"success": False, "error": f"Coupon '{code}' is invalid or expired"})
    _cart["applied_coupon"] = matched["code"]
    discount = _apply_discount(_cart_total())
    return json.dumps({
        "success": True,
        "coupon": matched,
        "discount_applied": discount,
        "new_total": _cart_total() - discount,
    })


# ---------------------------------------------------------------------------
# Tools — Order
# ---------------------------------------------------------------------------

@mcp.tool()
def place_food_order(address_id: str, payment_method: str = "UPI") -> str:
    """Confirm and finalise the food delivery order.

    Args:
        address_id: ID of the delivery address from get_addresses.
        payment_method: Payment method — 'UPI', 'Card', or 'COD'.
    """
    if not _cart["items"]:
        return json.dumps({"success": False, "error": "Cart is empty. Add items before placing an order."})

    address = next((a for a in _ADDRESSES if a["id"] == address_id), None)
    if not address:
        return json.dumps({"success": False, "error": f"Address '{address_id}' not found. Use get_addresses to list saved addresses."})

    subtotal = _cart_total()
    discount = _apply_discount(subtotal)
    total = subtotal - discount
    order_id = f"SWG{uuid.uuid4().hex[:8].upper()}"
    est_delivery = (datetime.now() + timedelta(minutes=35)).strftime("%H:%M")

    _orders[order_id] = {
        "order_id": order_id,
        "items": deepcopy(_cart["items"]),
        "restaurant_id": _cart["restaurant_id"],
        "address": address,
        "payment_method": payment_method,
        "subtotal": subtotal,
        "discount": discount,
        "total": total,
        "applied_coupon": _cart["applied_coupon"],
        "status": "confirmed",
        "placed_at": datetime.now().isoformat(),
        "estimated_delivery": est_delivery,
    }

    _cart["items"].clear()
    _cart["restaurant_id"] = None
    _cart["applied_coupon"] = None

    return json.dumps({
        "success": True,
        "order_id": order_id,
        "total": total,
        "estimated_delivery": est_delivery,
        "payment_method": payment_method,
        "message": f"Order placed! Estimated delivery by {est_delivery}.",
    })


# ---------------------------------------------------------------------------
# Tools — Track
# ---------------------------------------------------------------------------

@mcp.tool()
def get_food_orders() -> str:
    """Show all active orders and their statuses."""
    return json.dumps({"orders": list(_orders.values()), "count": len(_orders)})


@mcp.tool()
def get_food_order_details(order_id: str) -> str:
    """Get comprehensive information about a specific order.

    Args:
        order_id: The order ID returned by place_food_order.
    """
    order = _orders.get(order_id)
    if not order:
        return json.dumps({"error": f"Order '{order_id}' not found"})
    return json.dumps(order)


@mcp.tool()
def track_food_order(order_id: str) -> str:
    """Monitor live order status and delivery progress.

    Args:
        order_id: The order ID returned by place_food_order.
    """
    order = _orders.get(order_id)
    if not order:
        return json.dumps({"error": f"Order '{order_id}' not found"})

    elapsed = int((datetime.now() - datetime.fromisoformat(order["placed_at"])).total_seconds() // 60)

    if elapsed < 3:
        stage, pct, rider = "Order confirmed by restaurant", 10, None
    elif elapsed < 12:
        stage, pct, rider = "Your food is being prepared", 35, None
    elif elapsed < 25:
        stage, pct, rider = "Rider picked up your order", 65, {"name": "Ravi Kumar", "rating": 4.8, "phone": "98765XXXXX"}
    else:
        stage, pct, rider = "Almost there — arriving soon!", 90, {"name": "Ravi Kumar", "rating": 4.8, "phone": "98765XXXXX"}

    return json.dumps({
        "order_id": order_id,
        "status": stage,
        "progress_pct": pct,
        "elapsed_minutes": elapsed,
        "estimated_delivery": order["estimated_delivery"],
        "rider": rider,
    })


# ---------------------------------------------------------------------------
# Tools — Support
# ---------------------------------------------------------------------------

@mcp.tool()
def report_error(error_description: str, tool_name: str = "") -> str:
    """Generate an error report for the development team.

    Args:
        error_description: What went wrong.
        tool_name: Which tool triggered the error (optional).
    """
    ticket = f"ERR{uuid.uuid4().hex[:6].upper()}"
    return json.dumps({"reported": True, "ticket_id": ticket, "message": f"Ticket {ticket} created. Team notified."})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Starting Swiggy Food Mock MCP server on http://localhost:8001/mcp")
    print("Set in .env:  SWIGGY_FOOD_MCP_URL=http://localhost:8001/mcp")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8001)
