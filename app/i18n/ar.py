# Arabic UI strings — professional store voice.
# Keys are stable identifiers; values are user-facing copy.

MESSAGES = {
    # ── عام ──────────────────────────────────────────────
    "welcome": "أهلاً بك في المتجر 🛍️\nاختر من القائمة أدناه:",
    "main_menu_catalog": "🛍️ المنتجات",
    "main_menu_balance": "💰 رصيدي",
    "main_menu_deposit": "💳 شحن الرصيد",
    "main_menu_admin": "🔐 لوحة التحكم",
    "back": "🔙 رجوع",
    "cancel": "❌ إلغاء",
    "unknown": "لم أفهم ذلك، يرجى استخدام الأزرار أدناه.",
    "error_generic": "حدث خطأ غير متوقع. حاول مجدداً أو تواصل مع الدعم.",

    # ── الرصيد ────────────────────────────────────────────
    "balance_label": "💰 رصيدك الحالي: {balance} ل.س",

    # ── المنتجات ──────────────────────────────────────────
    "catalog_title": "🛍️ اختر القسم:",
    "no_products": "لا توجد منتجات متاحة حالياً.",
    "product_info": "📦 {name}\n💰 {price} ل.س",
    "product_params_hint": "أدخل {param}:",
    "product_qty_hint": "أدخل الكمية:",
    "qty_rule": "الكمية المسموحة: {rule}",
    "qty_invalid": "⚠️ أدخل رقماً صحيحاً.",
    "qty_not_allowed": "⚠️ هذه الكمية غير مسموحة. المسموح: {rule}",

    # ── الطلبات ───────────────────────────────────────────
    "order_summary": "🧾 ملخص الطلب:\n\n📦 المنتج: {name}\n{details}🔢 الكمية: {qty}\n💵 السعر: {price} ل.س",
    "order_confirm": "✅ تأكيد الطلب",
    "order_processing": "⏳ جارٍ معالجة طلبك...",
    "order_success": "✅ تم تأكيد طلبك بنجاح!",
    "order_failed": "❌ تعذّر تنفيذ الطلب: {reason}",
    "order_waiting": "⏳ تم استلام طلبك، سيتم تنفيذه خلال دقائق. سنخبرك فور اكتماله.",
    "order_refunded": "💸 تم إرجاع {amount} ل.س إلى رصيدك.",
    "order_insufficient": "❌ رصيدك غير كافٍ لهذا الطلب.",
    "provider_insufficient": "رصيد المتجر غير كافٍ حالياً، حاول لاحقاً.",
    "provider_rejected": "تم رفض الطلب من المزوّد.",

    # ── الشحن ─────────────────────────────────────────────
    "deposit_amount": "💰 أدخل المبلغ الذي تريد شحنه بالليرات السورية:",
    "deposit_amount_invalid": "⚠️ أدخل مبلغاً صحيحاً أكبر من صفر.",
    "deposit_method": "اختر طريقة الدفع:",
    "deposit_send_to": "📲 طريقة الدفع: {name}\nأرسل المبلغ ثم أرفق الإيصال.",
    "deposit_no_methods": "طرق الدفع غير متوفرة حالياً، تواصل مع الدعم.",
    "deposit_receipt": "📎 أرسل صورة الإيصال بعد التحويل.",
    "deposit_receipt_invalid": "⚠️ يجب إرسال صورة الإيصال كصورة (ليس ملفاً).",
    "deposit_pending": "⏳ تم استلام طلب الشحن. سيُفعّل رصيدك بعد المراجعة.",
    "deposit_approved": "✅ تم تفعيل شحن {amount} ل.س.\nرصيدك الحالي: {balance} ل.س",
    "deposit_rejected": "❌ تم رفض طلب الشحن. تواصل مع الدعم.",

    # ── الأدمن ────────────────────────────────────────────
    "admin_menu": "🔐 لوحة التحكم:",
    "admin_stats": "📊 الإحصائيات:",
}
