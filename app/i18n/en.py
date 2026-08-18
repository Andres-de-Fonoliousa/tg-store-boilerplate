# English UI strings — professional store voice.
# Keys mirror ar.py.

MESSAGES = {
    # ── General ───────────────────────────────────────────
    "welcome": "Welcome to the store 🛍️\nChoose from the menu below:",
    "main_menu_catalog": "🛍️ Products",
    "main_menu_balance": "💰 My balance",
    "main_menu_deposit": "💳 Top up",
    "main_menu_admin": "🔐 Admin panel",
    "back": "🔙 Back",
    "cancel": "❌ Cancel",
    "unknown": "Sorry, I didn't get that. Please use the buttons below.",
    "error_generic": "An unexpected error occurred. Try again or contact support.",

    # ── Balance ───────────────────────────────────────────
    "balance_label": "💰 Your balance: {balance} SYP",

    # ── Catalog ───────────────────────────────────────────
    "catalog_title": "🛍️ Choose a category:",
    "no_products": "No products available right now.",
    "product_info": "📦 {name}\n💰 {price} SYP",
    "product_params_hint": "Enter {param}:",
    "product_qty_hint": "Enter quantity:",
    "qty_rule": "Allowed quantities: {rule}",
    "qty_invalid": "⚠️ Please enter a valid number.",
    "qty_not_allowed": "⚠️ That quantity is not allowed. Allowed: {rule}",

    # ── Orders ────────────────────────────────────────────
    "order_summary": "🧾 Order summary:\n\n📦 Product: {name}\n{details}🔢 Quantity: {qty}\n💵 Price: {price} SYP",
    "order_confirm": "✅ Confirm order",
    "order_processing": "⏳ Processing your order...",
    "order_success": "✅ Your order was placed successfully!",
    "order_failed": "❌ Order failed: {reason}",
    "order_waiting": "⏳ Your order was received and will be fulfilled within minutes. We'll notify you when it's done.",
    "order_refunded": "💸 {amount} SYP was returned to your balance.",
    "order_insufficient": "❌ Your balance is not enough for this order.",
    "provider_insufficient": "The store balance is insufficient right now, try later.",
    "provider_rejected": "The order was rejected by the provider.",

    # ── Deposits ──────────────────────────────────────────
    "deposit_amount": "💰 Enter the amount you want to top up (SYP):",
    "deposit_amount_invalid": "⚠️ Please enter a valid amount greater than zero.",
    "deposit_method": "Choose a payment method:",
    "deposit_send_to": "📲 Payment method: {name}\nSend the amount, then attach the receipt.",
    "deposit_no_methods": "No payment methods available right now, contact support.",
    "deposit_receipt": "📎 Send the receipt screenshot after the transfer.",
    "deposit_receipt_invalid": "⚠️ Please send the receipt as a photo (not a file).",
    "deposit_pending": "⏳ Deposit received. Your balance will be credited after review.",
    "deposit_approved": "✅ {amount} SYP was credited.\nYour balance: {balance} SYP",
    "deposit_rejected": "❌ Deposit rejected. Contact support.",

    # ── Admin ─────────────────────────────────────────────
    "admin_menu": "🔐 Admin panel:",
    "admin_stats": "📊 Statistics:",
}
