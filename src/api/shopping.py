"""Per-user shopping list REST (backs the Shopping panel).

The assistant maintains the same list conversationally via the shopping tools;
this router lets the panel add/check/remove items directly.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.auth import get_user_id
from src.models.schema import AddShoppingItemRequest, ShoppingItemOut, UpdateShoppingItemRequest
from src.services.event_broker import get_broker

router = APIRouter(prefix="/shopping", tags=["shopping"])


def _to_out(item) -> ShoppingItemOut:
    return ShoppingItemOut(
        id=item.id,
        name=item.name,
        quantity=item.quantity,
        purchased=item.purchased,
        created_at=item.created_at.isoformat(),
    )


@router.get("", response_model=list[ShoppingItemOut])
async def list_items(request: Request, user_id: str = Depends(get_user_id)):
    items = await request.app.state.shopping_store.list_for_user(user_id)
    return [_to_out(i) for i in items]


@router.post("", response_model=ShoppingItemOut)
async def add_item(
    req: AddShoppingItemRequest, request: Request, user_id: str = Depends(get_user_id)
):
    item = await request.app.state.shopping_store.add(user_id, req.name.strip(), req.quantity)
    get_broker().broadcast({"type": "shopping_updated"}, user_id)
    return _to_out(item)


@router.patch("/{item_id}")
async def update_item(
    item_id: str,
    req: UpdateShoppingItemRequest,
    request: Request,
    user_id: str = Depends(get_user_id),
):
    ok = await request.app.state.shopping_store.set_purchased(item_id, user_id, req.purchased)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
    get_broker().broadcast({"type": "shopping_updated"}, user_id)
    return {"status": "ok"}


@router.delete("/{item_id}")
async def delete_item(item_id: str, request: Request, user_id: str = Depends(get_user_id)):
    ok = await request.app.state.shopping_store.remove(item_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
    get_broker().broadcast({"type": "shopping_updated"}, user_id)
    return {"status": "ok"}
