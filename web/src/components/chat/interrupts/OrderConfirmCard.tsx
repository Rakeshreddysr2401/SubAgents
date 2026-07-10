import type { InterruptItemProps } from "./types";

/** confirm_order (Swiggy food / instamart order placement): a purchase
 * summary with the final amount front and center. The MCP servers own the
 * exact args schema, so extraction is tolerant — recognized fields render
 * rich, everything is still inspectable under "details". */

const TOTAL_KEYS = ["final_amount", "total_amount", "grand_total", "total", "amount", "cart_total", "bill_total"];
const ITEMS_KEYS = ["items", "cart_items", "order_items"];
const ADDRESS_KEYS = ["address", "delivery_address", "address_label", "address_id"];

function findFirst(args: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    if (args[key] != null && args[key] !== "") return args[key];
  }
  return null;
}

function asItems(value: unknown): { label: string; qty: string }[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 8).map((item) => {
    if (typeof item === "string") return { label: item, qty: "" };
    const o = (item ?? {}) as Record<string, unknown>;
    const label = String(o.name ?? o.item_name ?? o.title ?? JSON.stringify(item));
    const qty = o.quantity != null ? `× ${o.quantity}` : "";
    return { label, qty };
  });
}

export function OrderConfirmCard({ request, decided, disabled, onDecide }: InterruptItemProps) {
  const total = findFirst(request.args, TOTAL_KEYS);
  const items = asItems(findFirst(request.args, ITEMS_KEYS));
  const address = findFirst(request.args, ADDRESS_KEYS);

  return (
    <div className="interrupt-item order-confirm">
      <div className="order-confirm-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="9" cy="21" r="1" /><circle cx="20" cy="21" r="1" />
          <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
        </svg>
        Place this order?
      </div>
      {items.length > 0 && (
        <ul className="order-items">
          {items.map((item, i) => (
            <li key={i}><span>{item.label}</span><span className="order-item-qty">{item.qty}</span></li>
          ))}
        </ul>
      )}
      {address != null && <div className="order-address">Deliver to: {String(address)}</div>}
      {total != null && (
        <div className="order-total">
          <span>Total</span>
          <strong>₹{String(total)}</strong>
        </div>
      )}
      <details className="order-raw">
        <summary>details</summary>
        <pre className="interrupt-args">{JSON.stringify(request.args, null, 2)}</pre>
      </details>
      {decided ? (
        <div className="interrupt-decided">Resolved: <strong>{decided.type}</strong></div>
      ) : (
        <div className="interrupt-actions">
          <button
            className="interrupt-btn approve"
            onClick={() => onDecide({ type: "approve" })}
            disabled={disabled}
            type="button"
          >
            Approve
          </button>
          <button
            className="interrupt-btn reject"
            onClick={() => onDecide({ type: "reject" })}
            disabled={disabled}
            type="button"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}
