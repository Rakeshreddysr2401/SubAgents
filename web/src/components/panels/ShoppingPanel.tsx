import { useCallback, useEffect, useState } from "react";
import { authFetch } from "../../api/client";
import { useEventsStore } from "../../state/eventsStore";
import "./Panels.css";

interface ShoppingItem {
  id: string;
  name: string;
  quantity: string | null;
  purchased: boolean;
}

export function ShoppingPanel() {
  const [items, setItems] = useState<ShoppingItem[]>([]);
  const [newItem, setNewItem] = useState("");
  const shoppingBump = useEventsStore((s) => s.shoppingBump);

  const refresh = useCallback(async () => {
    try {
      const res = await authFetch("/shopping");
      if (res.ok) setItems(await res.json());
    } catch {
      // transient — the next bump/refetch will recover
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh, shoppingBump]);

  const togglePurchased = useCallback(async (item: ShoppingItem) => {
    // Optimistic toggle; revert on failure.
    setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, purchased: !i.purchased } : i)));
    try {
      const res = await authFetch(`/shopping/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ purchased: !item.purchased }),
      });
      if (!res.ok) throw new Error();
    } catch {
      setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, purchased: item.purchased } : i)));
    }
  }, []);

  const remove = useCallback(async (id: string) => {
    await authFetch(`/shopping/${id}`, { method: "DELETE" }).catch(() => {});
    refresh();
  }, [refresh]);

  const add = useCallback(async () => {
    const name = newItem.trim();
    if (!name) return;
    setNewItem("");
    await authFetch("/shopping", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }).catch(() => {});
    refresh();
  }, [newItem, refresh]);

  return (
    <div className="tools-card panel-card">
      <div className="tools-card-header">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="9" cy="21" r="1" />
          <circle cx="20" cy="21" r="1" />
          <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
        </svg>
        Shopping list
      </div>
      <div className="panel-body">
        {items.length === 0 && (
          <div className="panel-empty">Empty — try “remember we need to buy soap”.</div>
        )}
        {items.map((item) => (
          <div key={item.id} className={`panel-row${item.purchased ? " muted" : ""}`}>
            <label className="panel-check">
              <input
                type="checkbox"
                checked={item.purchased}
                onChange={() => togglePurchased(item)}
              />
              <span className={`panel-row-title${item.purchased ? " struck" : ""}`}>
                {item.name}
                {item.quantity ? <span className="panel-row-sub"> · {item.quantity}</span> : null}
              </span>
            </label>
            <button className="panel-row-action" onClick={() => remove(item.id)} title="Remove item" type="button">
              ×
            </button>
          </div>
        ))}
        <div className="panel-add">
          <input
            value={newItem}
            onChange={(e) => setNewItem(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="Add item…"
          />
          <button onClick={add} disabled={!newItem.trim()} type="button">+</button>
        </div>
      </div>
    </div>
  );
}
