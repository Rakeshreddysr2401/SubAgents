from langchain_core.tools import tool
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

@tool
def get_current_location() -> str:
    """Get the user's current GPS location/address for food delivery."""
    # Placeholder for MCP / System call
    return "123 Tech Park, Bangalore, Karnataka"

@tool
def search_restaurants(cuisine: str = None, rating: float = 4.0) -> str:
    """Search for restaurants nearby based on cuisine or rating."""
    logger.info("Searching for %s restaurants", cuisine or "any")
    return "Found: 1. Truffles (American, 4.5*), 2. Meghana Foods (Biryani, 4.4*), 3. Empire Restaurant (North Indian, 4.1*)"

@tool
def search_food(restaurant_id: str, query: str) -> str:
    """Search for specific food items within a chosen restaurant's menu."""
    return f"Results for '{query}' at {restaurant_id}: 1. Classic Veg Burger, 2. Peri Peri Chicken Burger, 3. Cheese Fries"

@tool
def add_to_cart(item_id: str, quantity: int = 1) -> str:
    """Add a specific food item to the Swiggy cart."""
    return f"Success: Added {quantity}x {item_id} to your cart."

@tool
def go_to_checkout() -> str:
    """Proceed to the checkout screen to review the order and select payment."""
    return "Checkout Summary: Total: ₹540. Delivery to '123 Tech Park'. Please confirm payment method."

@tool
def select_payment_method(method: str = "COD") -> str:
    """Select the payment method. Supported: 'COD' (Cash on Delivery), 'UPI', 'CARD'."""
    return f"Payment method set to {method}. Order is ready to be placed."

SWIGGY_TOOLS = [
    get_current_location,
    search_restaurants,
    search_food,
    add_to_cart,
    go_to_checkout,
    select_payment_method
]
