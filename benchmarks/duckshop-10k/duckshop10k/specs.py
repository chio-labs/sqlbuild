"""Source table archetypes for every source system, and how each platform lays them out.

An archetype lists a table's logical fields by role. A platform generation decides the physical
layout of each field in the raw table (column name, unit, time zone handling, or a JSON path) and
the staging name it is published under:

- `classic`: legacy names (`_ref`, `_ts`, `_amt`, `_flag`, `status_cd`), local `TIMESTAMP_NTZ`,
  major-unit amounts, and JSON kept as text in `extra_json`;
- `nest`: conventional columns, `TIMESTAMP_TZ`, minor-unit amounts, JSON in `attributes`;
- `flock`: a key plus one `doc` document holding every other field, with epoch-millisecond times.
"""

from __future__ import annotations

from dataclasses import dataclass

# Roles whose raw value is semi-structured; they always live in the JSON payload.
SEMI_ROLES = frozenset({"array", "object"})


@dataclass(frozen=True)
class Field:
    stem: str
    role: str
    in_payload: bool = False


@dataclass(frozen=True)
class Child:
    """An array inside a parent row, published as its own staging model by LATERAL FLATTEN."""

    name: str
    array: str
    fields: tuple[Field, ...]
    description: str


@dataclass(frozen=True)
class Archetype:
    table: str
    key: str
    fields: tuple[Field, ...]
    description: str
    append: bool = False
    children: tuple[Child, ...] = ()
    history: bool = False


def f(stem: str, role: str, payload: bool = False) -> Field:
    return Field(stem, role, payload or role in SEMI_ROLES)


# Output names and types in staging. Times and amounts keep their source unit in staging, so the
# name says which one it is; the intermediate conformed models convert them.
def staging_name(field: Field, platform: str) -> str:
    if field.role == "ts":
        if field.in_payload and platform != "flock":
            return f"{field.stem}_at"
        return {
            "classic": f"{field.stem}_at_local",
            "nest": f"{field.stem}_at",
            "flock": f"{field.stem}_at_utc",
        }[platform]
    if field.role == "amount":
        if platform == "classic" and not field.in_payload:
            return f"{field.stem}_amount"
        return f"{field.stem}_amount_minor"
    if field.role == "status":
        return "status_code" if platform == "classic" else "status"
    if field.role == "date":
        return f"{field.stem}_date"
    if field.role == "bool":
        return f"is_{field.stem}"
    if field.role == "url":
        return f"{field.stem}_path"
    return field.stem


def staging_type(field: Field, platform: str) -> str:
    role = field.role
    if role == "ts":
        if field.in_payload and platform != "flock":
            return "TIMESTAMP_TZ"
        return {"classic": "TIMESTAMP_NTZ", "nest": "TIMESTAMP_TZ", "flock": "TIMESTAMP_NTZ"}[
            platform
        ]
    if role == "amount":
        if platform == "classic" and not field.in_payload:
            return "NUMBER(18, 2)"
        return "NUMBER(38, 0)"
    if role == "status":
        return "INT" if platform == "classic" else "VARCHAR"
    return {
        "qty": "INT",
        "int": "INT",
        "rate": "NUMBER(18, 6)",
        "date": "DATE",
        "bool": "BOOLEAN",
        "array": "ARRAY",
        "object": "OBJECT",
    }.get(role, "VARCHAR")


def payload_column(platform: str) -> str:
    return {"classic": "extra", "nest": "attributes", "flock": "doc"}[platform]


def lives_in_payload(field: Field, platform: str) -> bool:
    return platform == "flock" or field.in_payload


def physical_name(field: Field, platform: str) -> str:
    """Raw column name of a field that is not in the payload."""
    stem, role = field.stem, field.role
    if platform == "classic":
        if role in ("id", "key") and stem.endswith("_id"):
            return stem[: -len("_id")] + "_ref"
        if role == "ts":
            return f"{stem}_ts"
        if role == "amount":
            return f"{stem}_amt"
        if role == "bool":
            return f"{stem}_flag"
        if role == "status":
            return "status_cd"
        if role == "date":
            return f"{stem}_dt"
        return stem
    if role == "ts":
        return f"{stem}_at"
    if role == "amount":
        return f"{stem}_amount_minor"
    if role == "bool":
        return f"is_{stem}"
    if role == "date":
        return f"{stem}_date"
    return stem


def physical_type(field: Field, platform: str) -> str:
    role = field.role
    if platform == "classic":
        return {
            "ts": "TIMESTAMP_NTZ",
            "amount": "NUMBER(18,2)",
            "bool": "VARCHAR",
            "status": "NUMBER(38,0)",
            "qty": "NUMBER(38,0)",
            "int": "NUMBER(38,0)",
            "rate": "NUMBER(18,6)",
            "date": "DATE",
        }.get(role, "VARCHAR")
    return {
        "ts": "TIMESTAMP_TZ",
        "amount": "NUMBER(38,0)",
        "bool": "BOOLEAN",
        "qty": "NUMBER(38,0)",
        "int": "NUMBER(38,0)",
        "rate": "NUMBER(18,6)",
        "date": "DATE",
    }.get(role, "VARCHAR")


def json_path(field: Field, platform: str) -> str:
    """Path of a payload field inside the platform's JSON document."""
    if platform == "flock":
        if field.role == "ts":
            return f"{field.stem}_ms"
        if field.role == "amount":
            return f"amounts.{field.stem}"
    return field.stem


# --- Archetypes -------------------------------------------------------------------------------

_STOREFRONT: tuple[Archetype, ...] = (
    Archetype(
        "customers",
        "customer_id",
        (
            f("email", "email"),
            f("phone", "phone"),
            f("full_name", "name"),
            f("country_code", "country"),
            f("created", "ts"),
            f("marketing_opt_in", "bool", True),
            f("preferred_language", "code", True),
            f("birth_year", "int", True),
            f("loyalty_tier", "code", True),
            f("consents", "array"),
        ),
        "customer accounts",
        children=(Child("consents", "consents", (f("consent_type", "code"),), "consent grants"),),
        history=True,
    ),
    Archetype(
        "customer_addresses",
        "address_id",
        (
            f("customer_id", "id"),
            f("line1", "text"),
            f("city", "name"),
            f("postcode", "postcode"),
            f("country_code", "country"),
            f("default", "bool"),
            f("valid_from", "ts"),
        ),
        "customer address book entries",
        history=True,
    ),
    Archetype(
        "orders",
        "order_id",
        (
            f("customer_id", "id"),
            f("currency_code", "currency"),
            f("placed", "ts"),
            f("status", "status"),
            f("gross", "amount"),
            f("discount", "amount"),
            f("tax", "amount"),
            f("shipping", "amount"),
            f("channel", "code", True),
            f("utm_source", "code", True),
            f("utm_campaign", "code", True),
            f("device_type", "code", True),
            f("gift", "bool", True),
            f("line_skus", "array"),
        ),
        "orders",
        history=True,
    ),
    Archetype(
        "order_lines",
        "order_line_id",
        (
            f("order_id", "id"),
            f("sku", "sku"),
            f("quantity", "qty"),
            f("unit_price", "amount"),
            f("discounts", "array"),
        ),
        "order lines",
        children=(
            Child(
                "discounts",
                "discounts",
                (f("promo_code", "code"), f("discount", "amount", True), f("kind", "code")),
                "discounts applied to order lines",
            ),
        ),
    ),
    Archetype(
        "payments",
        "payment_id",
        (
            f("order_id", "id"),
            f("method", "code"),
            f("captured", "amount"),
            f("currency_code", "currency"),
            f("authorised", "ts"),
            f("gateway_status", "code", True),
            f("risk_score", "rate", True),
            f("three_ds", "code", True),
            f("attempts", "array"),
        ),
        "payments",
        children=(
            Child(
                "attempts",
                "attempts",
                (f("attempt_number", "int"), f("result", "code"), f("error_code", "code")),
                "payment authorisation attempts",
            ),
        ),
    ),
    Archetype(
        "refunds",
        "refund_id",
        (
            f("payment_id", "id"),
            f("refunded", "amount"),
            f("reason_text", "text"),
            f("issued", "ts"),
            f("initiated_by", "code", True),
        ),
        "refunds",
    ),
    Archetype(
        "carts",
        "cart_id",
        (
            f("customer_id", "id"),
            f("anonymous_id", "id"),
            f("opened", "ts"),
            f("last_activity", "ts"),
            f("items", "array"),
        ),
        "shopping carts",
        children=(
            Child(
                "items",
                "items",
                (f("sku", "sku"), f("quantity", "qty"), f("unit_price", "amount", True)),
                "cart items",
            ),
        ),
    ),
    Archetype(
        "wishlists",
        "wishlist_item_id",
        (f("customer_id", "id"), f("sku", "sku"), f("added", "ts"), f("priority", "int", True)),
        "wishlist items",
    ),
    Archetype(
        "reviews",
        "review_id",
        (
            f("sku", "sku"),
            f("customer_id", "id"),
            f("rating", "int"),
            f("title", "text"),
            f("submitted", "ts"),
            f("body_length", "int", True),
            f("moderation", "code", True),
        ),
        "product reviews",
    ),
    Archetype(
        "subscriptions",
        "subscription_id",
        (
            f("customer_id", "id"),
            f("plan_code", "code"),
            f("started", "ts"),
            f("status", "status"),
            f("price", "amount"),
            f("currency_code", "currency"),
            f("billing_interval", "code", True),
        ),
        "subscription boxes",
        history=True,
    ),
    Archetype(
        "loyalty_events",
        "loyalty_event_id",
        (
            f("customer_id", "id"),
            f("event_type", "code"),
            f("points", "int"),
            f("occurred", "ts"),
            f("tier_after", "code", True),
        ),
        "loyalty point events",
    ),
    Archetype(
        "gift_card_redemptions",
        "redemption_id",
        (
            f("gift_card_id", "id"),
            f("order_id", "id"),
            f("redeemed", "amount"),
            f("currency_code", "currency"),
            f("used", "ts"),
        ),
        "gift card redemptions",
    ),
    Archetype(
        "consent_events",
        "consent_event_id",
        (
            f("customer_id", "id"),
            f("consent_type", "code"),
            f("granted", "bool"),
            f("occurred", "ts"),
            f("source_channel", "code", True),
        ),
        "consent changes",
    ),
    Archetype(
        "promotion_redemptions",
        "promotion_redemption_id",
        (
            f("promo_code", "code"),
            f("order_id", "id"),
            f("customer_id", "id"),
            f("discount", "amount"),
            f("redeemed", "ts"),
            f("tiers", "array"),
        ),
        "promotion redemptions",
        children=(
            Child(
                "tiers",
                "tiers",
                (f("threshold", "amount", True), f("discount_rate", "rate")),
                "promotion tiers reached",
            ),
        ),
    ),
    Archetype(
        "tax_lines",
        "tax_line_id",
        (
            f("order_id", "id"),
            f("jurisdiction", "code"),
            f("tax_rate", "rate"),
            f("tax", "amount"),
        ),
        "order tax lines",
    ),
    Archetype(
        "store_credit",
        "credit_txn_id",
        (
            f("customer_id", "id"),
            f("credit", "amount"),
            f("currency_code", "currency"),
            f("reason", "code"),
            f("occurred", "ts"),
        ),
        "store credit transactions",
    ),
    Archetype(
        "order_notes",
        "note_id",
        (f("order_id", "id"), f("author_type", "code"), f("body", "text"), f("written", "ts")),
        "order notes",
    ),
    Archetype(
        "newsletter_signups",
        "signup_id",
        (
            f("email", "email"),
            f("country_code", "country"),
            f("signed_up", "ts"),
            f("source_page", "url", True),
            f("double_opt_in", "bool", True),
        ),
        "newsletter sign-ups",
    ),
)

_MARKETPLACE: tuple[Archetype, ...] = (
    Archetype(
        "listings",
        "listing_id",
        (
            f("sku", "sku"),
            f("title", "text"),
            f("listing_status", "code"),
            f("price", "amount"),
            f("currency_code", "currency"),
            f("updated", "ts"),
            f("images", "array"),
            f("attributes_bag", "object"),
        ),
        "partner listings",
        children=(
            Child("images", "images", (f("image_url", "url"), f("position", "int")), "images"),
        ),
        history=True,
    ),
    Archetype(
        "orders",
        "partner_order_id",
        (
            f("buyer_ref", "id"),
            f("placed", "ts"),
            f("currency_code", "currency"),
            f("total", "amount"),
            f("status", "status"),
            f("ship_country", "country"),
        ),
        "partner orders",
        history=True,
    ),
    Archetype(
        "order_items",
        "partner_order_item_id",
        (
            f("partner_order_id", "id"),
            f("sku", "sku"),
            f("quantity", "qty"),
            f("item_price", "amount"),
            f("fees", "array"),
        ),
        "partner order items",
        children=(
            Child("fees", "fees", (f("fee_type", "code"), f("fee", "amount", True)), "item fees"),
        ),
    ),
    Archetype(
        "returns",
        "partner_return_id",
        (
            f("partner_order_id", "id"),
            f("sku", "sku"),
            f("quantity", "qty"),
            f("reason_text", "text"),
            f("received", "ts"),
        ),
        "partner returns",
    ),
    Archetype(
        "payouts",
        "payout_id",
        (
            f("period_start", "date"),
            f("period_end", "date"),
            f("payout", "amount"),
            f("currency_code", "currency"),
            f("paid", "ts"),
        ),
        "partner payouts",
    ),
    Archetype(
        "fees",
        "fee_id",
        (
            f("partner_order_id", "id"),
            f("fee_type", "code"),
            f("fee", "amount"),
            f("currency_code", "currency"),
            f("charged", "ts"),
        ),
        "partner fees",
    ),
    Archetype(
        "inventory_snapshots",
        "inventory_snapshot_id",
        (f("sku", "sku"), f("available", "qty"), f("reserved", "qty"), f("captured", "ts")),
        "partner stock snapshots",
        append=True,
    ),
    Archetype(
        "messages",
        "message_id",
        (
            f("partner_order_id", "id"),
            f("direction", "code"),
            f("body", "text"),
            f("sent", "ts"),
        ),
        "buyer messages",
        append=True,
    ),
    Archetype(
        "shipments",
        "partner_shipment_id",
        (
            f("partner_order_id", "id"),
            f("carrier_code", "code"),
            f("tracking_number", "id"),
            f("shipped", "ts"),
            f("delivered", "ts"),
        ),
        "partner-fulfilled shipments",
    ),
    Archetype(
        "reviews",
        "partner_review_id",
        (
            f("sku", "sku"),
            f("rating", "int"),
            f("title", "text"),
            f("submitted", "ts"),
            f("verified", "bool", True),
        ),
        "partner product reviews",
    ),
    Archetype(
        "promotions",
        "partner_promotion_id",
        (
            f("sku", "sku"),
            f("promotion_type", "code"),
            f("starts", "ts"),
            f("ends", "ts"),
            f("deal_price", "amount"),
        ),
        "partner promotions",
    ),
    Archetype(
        "disputes",
        "partner_dispute_id",
        (
            f("partner_order_id", "id"),
            f("dispute_type", "code"),
            f("opened", "ts"),
            f("claimed", "amount"),
            f("status", "status"),
        ),
        "buyer disputes",
    ),
)

_CARRIER: tuple[Archetype, ...] = (
    Archetype(
        "shipments",
        "shipment_id",
        (
            f("order_id", "id"),
            f("warehouse_code", "code"),
            f("service_level", "code"),
            f("shipped", "ts"),
            f("weight_grams", "int"),
            f("tracking", "array"),
        ),
        "shipments",
        children=(
            Child(
                "tracking",
                "tracking",
                (f("event_code", "code"), f("location", "name"), f("sequence", "int")),
                "embedded tracking events",
            ),
        ),
    ),
    Archetype(
        "tracking_events",
        "tracking_event_id",
        (
            f("shipment_id", "id"),
            f("status_code_text", "code"),
            f("occurred", "ts"),
            f("location", "name"),
        ),
        "tracking feed events",
        append=True,
    ),
    Archetype(
        "invoices",
        "invoice_line_id",
        (
            f("shipment_id", "id"),
            f("charge_type", "code"),
            f("charge", "amount"),
            f("currency_code", "currency"),
            f("invoiced", "ts"),
        ),
        "carrier invoice lines",
    ),
    Archetype(
        "rate_cards",
        "rate_card_id",
        (
            f("service_level", "code"),
            f("zone", "code"),
            f("weight_band", "int"),
            f("rate", "amount"),
            f("currency_code", "currency"),
            f("valid_from", "ts"),
        ),
        "carrier rate cards",
        history=True,
    ),
)

_WAREHOUSE: tuple[Archetype, ...] = (
    Archetype(
        "receipts",
        "receipt_id",
        (f("po_id", "id"), f("sku", "sku"), f("quantity", "qty"), f("received", "ts")),
        "goods receipts",
    ),
    Archetype(
        "picks",
        "pick_id",
        (
            f("order_id", "id"),
            f("sku", "sku"),
            f("quantity", "qty"),
            f("picked", "ts"),
            f("picker_ref", "id"),
        ),
        "pick tasks",
    ),
    Archetype(
        "packs",
        "pack_id",
        (
            f("order_id", "id"),
            f("package_count", "int"),
            f("packed", "ts"),
            f("dimensions", "object"),
        ),
        "packed orders",
    ),
    Archetype(
        "stock_counts",
        "count_id",
        (f("sku", "sku"), f("counted_qty", "qty"), f("counted", "ts")),
        "stock counts",
    ),
    Archetype(
        "adjustments",
        "adjustment_id",
        (f("sku", "sku"), f("qty_delta", "int"), f("reason_code", "code"), f("adjusted", "ts")),
        "stock adjustments",
    ),
    Archetype(
        "labour_shifts",
        "shift_id",
        (
            f("team_code", "code"),
            f("started", "ts"),
            f("ended", "ts"),
            f("headcount", "int"),
        ),
        "labour shifts",
    ),
    Archetype(
        "dock_appointments",
        "appointment_id",
        (
            f("carrier_code", "code"),
            f("scheduled", "ts"),
            f("arrived", "ts"),
            f("door", "code"),
        ),
        "dock appointments",
    ),
    Archetype(
        "stock_movements",
        "movement_id",
        (f("sku", "sku"), f("qty_delta", "int"), f("reason_code", "code"), f("moved", "ts")),
        "stock movements",
        append=True,
    ),
    Archetype(
        "putaways",
        "putaway_id",
        (
            f("receipt_id", "id"),
            f("sku", "sku"),
            f("bin_code", "code"),
            f("quantity", "qty"),
            f("completed", "ts"),
        ),
        "put-away tasks",
    ),
    Archetype(
        "replenishments",
        "replenishment_id",
        (
            f("sku", "sku"),
            f("from_bin", "code"),
            f("to_bin", "code"),
            f("quantity", "qty"),
            f("requested", "ts"),
            f("completed", "ts"),
        ),
        "pick-face replenishments",
    ),
    Archetype(
        "cycle_counts",
        "cycle_count_id",
        (
            f("bin_code", "code"),
            f("sku", "sku"),
            f("expected_qty", "qty"),
            f("counted_qty", "qty"),
            f("counted", "ts"),
        ),
        "cycle counts",
    ),
    Archetype(
        "damages",
        "damage_id",
        (
            f("sku", "sku"),
            f("quantity", "qty"),
            f("damage_type", "code"),
            f("recorded", "ts"),
            f("photos", "array"),
        ),
        "damaged stock records",
    ),
    Archetype(
        "returns_received",
        "returned_parcel_id",
        (
            f("order_id", "id"),
            f("sku", "sku"),
            f("quantity", "qty"),
            f("condition_code", "code"),
            f("received", "ts"),
        ),
        "customer returns received",
    ),
    Archetype(
        "slotting",
        "slot_id",
        (
            f("bin_code", "code"),
            f("sku", "sku"),
            f("zone", "code"),
            f("assigned", "ts"),
        ),
        "bin slotting assignments",
        history=True,
    ),
)

_STORE: tuple[Archetype, ...] = (
    Archetype(
        "transactions",
        "txn_id",
        (
            f("register_id", "code"),
            f("opened", "ts"),
            f("closed", "ts"),
            f("total", "amount"),
            f("currency_code", "currency"),
            f("status", "status"),
        ),
        "till transactions",
    ),
    Archetype(
        "transaction_lines",
        "txn_line_id",
        (
            f("txn_id", "id"),
            f("sku", "sku"),
            f("quantity", "qty"),
            f("unit_price", "amount"),
            f("discounts", "array"),
        ),
        "till transaction lines",
        children=(
            Child(
                "discounts",
                "discounts",
                (f("promo_code", "code"), f("discount", "amount", True)),
                "till line discounts",
            ),
        ),
    ),
    Archetype(
        "tenders",
        "tender_id",
        (
            f("txn_id", "id"),
            f("tender_type", "code"),
            f("tendered", "amount"),
            f("card_bin", "code"),
        ),
        "transaction tenders",
    ),
    Archetype(
        "shifts",
        "till_shift_id",
        (
            f("register_id", "code"),
            f("opened", "ts"),
            f("closed", "ts"),
            f("float", "amount"),
        ),
        "till shifts",
    ),
    Archetype(
        "footfall",
        "footfall_id",
        (f("counted", "ts"), f("visitors", "int"), f("sensor", "code")),
        "door counter readings",
        append=True,
    ),
    Archetype(
        "returns",
        "store_return_id",
        (
            f("txn_id", "id"),
            f("sku", "sku"),
            f("quantity", "qty"),
            f("refunded", "amount"),
            f("reason_code", "code"),
            f("processed", "ts"),
        ),
        "in-store returns",
    ),
    Archetype(
        "gift_cards",
        "store_gift_card_id",
        (
            f("txn_id", "id"),
            f("loaded", "amount"),
            f("card_suffix", "code"),
            f("issued", "ts"),
        ),
        "gift cards sold in store",
    ),
    Archetype(
        "cash_drops",
        "cash_drop_id",
        (
            f("register_id", "code"),
            f("dropped", "amount"),
            f("dropped_at_shift", "id"),
            f("recorded", "ts"),
        ),
        "till cash drops",
    ),
    Archetype(
        "price_overrides",
        "price_override_id",
        (
            f("txn_line_id", "id"),
            f("original_price", "amount"),
            f("override_price", "amount"),
            f("reason_code", "code"),
            f("approved", "ts"),
        ),
        "manual price overrides",
    ),
    Archetype(
        "loyalty_scans",
        "loyalty_scan_id",
        (
            f("txn_id", "id"),
            f("member_ref", "id"),
            f("scanned", "ts"),
            f("points_earned", "int"),
        ),
        "loyalty card scans at the till",
        append=True,
    ),
    Archetype(
        "staff_discounts",
        "staff_discount_id",
        (
            f("txn_id", "id"),
            f("discount", "amount"),
            f("approved_by_ref", "id"),
            f("granted", "ts"),
        ),
        "staff discounts",
    ),
)

_SUPPLIER: tuple[Archetype, ...] = (
    Archetype(
        "purchase_orders",
        "po_id",
        (
            f("warehouse_code", "code"),
            f("ordered", "ts"),
            f("expected", "ts"),
            f("currency_code", "currency"),
            f("lines", "array"),
        ),
        "purchase orders",
        children=(
            Child(
                "lines",
                "lines",
                (f("sku", "sku"), f("quantity", "qty"), f("unit_cost", "amount", True)),
                "purchase order lines",
            ),
        ),
    ),
    Archetype(
        "asn",
        "asn_id",
        (f("po_id", "id"), f("dispatched", "ts"), f("eta", "ts"), f("cartons", "array")),
        "advance shipping notices",
        children=(
            Child(
                "cartons",
                "cartons",
                (f("carton_ref", "id"), f("sku", "sku"), f("quantity", "qty")),
                "cartons on a shipping notice",
            ),
        ),
    ),
    Archetype(
        "invoices",
        "supplier_invoice_id",
        (
            f("po_id", "id"),
            f("invoiced_total", "amount"),
            f("currency_code", "currency"),
            f("invoiced", "ts"),
            f("due", "date"),
        ),
        "supplier invoices",
    ),
    Archetype(
        "catalogue_items",
        "supplier_sku_id",
        (
            f("sku", "sku"),
            f("unit_cost", "amount"),
            f("currency_code", "currency"),
            f("lead_time_days", "int"),
            f("valid_from", "ts"),
        ),
        "supplier catalogue items",
        history=True,
    ),
)

_GATEWAY: tuple[Archetype, ...] = (
    Archetype(
        "charges",
        "charge_id",
        (
            f("order_id", "id"),
            f("charged", "amount"),
            f("currency_code", "currency"),
            f("created", "ts"),
            f("status", "status"),
            f("card_bin", "code", True),
            f("risk", "object"),
        ),
        "gateway charges",
    ),
    Archetype(
        "refunds",
        "gateway_refund_id",
        (f("charge_id", "id"), f("refunded", "amount"), f("created", "ts"), f("reason", "code")),
        "gateway refunds",
    ),
    Archetype(
        "disputes",
        "dispute_id",
        (
            f("charge_id", "id"),
            f("disputed", "amount"),
            f("opened", "ts"),
            f("reason_code", "code"),
            f("evidence", "array"),
        ),
        "card disputes",
        children=(
            Child(
                "evidence",
                "evidence",
                (f("document_type", "code"), f("page_count", "int")),
                "dispute evidence documents",
            ),
        ),
    ),
    Archetype(
        "payouts",
        "gateway_payout_id",
        (f("payout", "amount"), f("currency_code", "currency"), f("arrival", "date")),
        "gateway payouts",
    ),
    Archetype(
        "fees",
        "gateway_fee_id",
        (f("charge_id", "id"), f("fee_type", "code"), f("fee", "amount")),
        "gateway fees",
    ),
)

_AD_NETWORK: tuple[Archetype, ...] = (
    Archetype(
        "campaigns",
        "campaign_id",
        (
            f("campaign_name", "text"),
            f("objective", "code"),
            f("started", "ts"),
            f("ended", "ts"),
            f("budget", "amount"),
            f("currency_code", "currency"),
        ),
        "ad campaigns",
    ),
    Archetype(
        "ad_groups",
        "ad_group_id",
        (f("campaign_id", "id"), f("ad_group_name", "text"), f("bid_strategy", "code")),
        "ad groups",
    ),
    Archetype(
        "daily_spend",
        "spend_id",
        (
            f("campaign_id", "id"),
            f("spend", "date"),
            f("spent", "amount"),
            f("currency_code", "currency"),
            f("metrics", "array"),
        ),
        "daily spend reports",
        append=True,
        children=(
            Child(
                "metrics",
                "metrics",
                (f("metric", "code"), f("metric_value", "rate")),
                "reported delivery metrics",
            ),
        ),
    ),
    Archetype(
        "conversions",
        "conversion_id",
        (
            f("campaign_id", "id"),
            f("click_id", "id"),
            f("order_id", "id"),
            f("converted", "ts"),
            f("conversion", "amount"),
            f("currency_code", "currency"),
        ),
        "reported conversions",
        append=True,
    ),
    Archetype(
        "audiences",
        "audience_id",
        (f("audience_name", "text"), f("audience_size", "int"), f("refreshed", "ts")),
        "audience lists",
    ),
)

_MESSAGING: tuple[Archetype, ...] = (
    Archetype(
        "sends",
        "send_id",
        (f("campaign_id", "id"), f("recipient_email", "email"), f("sent", "ts")),
        "message sends",
        append=True,
    ),
    Archetype(
        "opens",
        "open_id",
        (f("send_id", "id"), f("opened", "ts"), f("client_text", "text")),
        "message opens",
        append=True,
    ),
    Archetype(
        "clicks",
        "click_id",
        (f("send_id", "id"), f("link", "url"), f("clicked", "ts")),
        "message link clicks",
        append=True,
    ),
    Archetype(
        "bounces",
        "bounce_id",
        (f("send_id", "id"), f("bounce_type", "code"), f("bounced", "ts")),
        "message bounces",
        append=True,
    ),
    Archetype(
        "unsubscribes",
        "unsubscribe_id",
        (f("recipient_email", "email"), f("unsubscribed", "ts"), f("reason", "code")),
        "unsubscribes",
        append=True,
    ),
)

_AFFILIATE: tuple[Archetype, ...] = (
    Archetype(
        "clicks",
        "affiliate_click_id",
        (f("affiliate_id", "id"), f("landing", "url"), f("clicked", "ts")),
        "affiliate clicks",
        append=True,
    ),
    Archetype(
        "conversions",
        "affiliate_conversion_id",
        (
            f("affiliate_click_id", "id"),
            f("order_id", "id"),
            f("commission", "amount"),
            f("currency_code", "currency"),
            f("converted", "ts"),
            f("status", "status"),
        ),
        "affiliate conversions",
    ),
    Archetype(
        "payouts",
        "affiliate_payout_id",
        (
            f("affiliate_id", "id"),
            f("payout", "amount"),
            f("currency_code", "currency"),
            f("paid", "ts"),
        ),
        "affiliate payouts",
    ),
)

_SUPPORT: tuple[Archetype, ...] = (
    Archetype(
        "tickets",
        "ticket_id",
        (
            f("customer_email", "email"),
            f("contact_channel", "code"),
            f("priority", "int"),
            f("created", "ts"),
            f("custom_fields", "object"),
            f("tags", "array"),
        ),
        "support tickets",
        children=(Child("tags", "tags", (f("tag", "code"),), "ticket tags"),),
    ),
    Archetype(
        "ticket_comments",
        "comment_id",
        (
            f("ticket_id", "id"),
            f("author_type", "code"),
            f("body", "text"),
            f("written", "ts"),
        ),
        "ticket comments",
    ),
    Archetype(
        "csat_responses",
        "csat_id",
        (f("ticket_id", "id"), f("score", "int"), f("comment", "text"), f("responded", "ts")),
        "satisfaction survey responses",
    ),
    Archetype(
        "ticket_events",
        "ticket_event_id",
        (
            f("ticket_id", "id"),
            f("event_type", "code"),
            f("occurred", "ts"),
            f("details", "object"),
        ),
        "ticket lifecycle events",
        append=True,
    ),
)

_LEDGER: tuple[Archetype, ...] = (
    Archetype(
        "gl_entries",
        "gl_entry_id",
        (
            f("account_code", "code"),
            f("cost_centre", "code"),
            f("posted_value", "amount"),
            f("currency_code", "currency"),
            f("posted", "ts"),
            f("journal_ref", "id"),
        ),
        "general ledger entries",
    ),
    Archetype(
        "gl_accounts",
        "account_code",
        (f("account_name", "text"), f("account_type", "code"), f("active", "bool")),
        "chart of accounts",
    ),
    Archetype(
        "ap_invoices",
        "ap_invoice_id",
        (
            f("supplier_ref", "id"),
            f("invoiced_total", "amount"),
            f("currency_code", "currency"),
            f("invoiced", "ts"),
            f("due", "date"),
            f("status", "status"),
        ),
        "accounts payable invoices",
    ),
    Archetype(
        "ar_invoices",
        "ar_invoice_id",
        (
            f("customer_ref", "id"),
            f("invoiced_total", "amount"),
            f("currency_code", "currency"),
            f("invoiced", "ts"),
            f("due", "date"),
            f("status", "status"),
        ),
        "accounts receivable invoices",
    ),
    Archetype(
        "budgets",
        "budget_line_id",
        (
            f("cost_centre", "code"),
            f("period", "date"),
            f("budgeted", "amount"),
            f("currency_code", "currency"),
        ),
        "budget lines",
    ),
    Archetype(
        "bank_transactions",
        "bank_txn_id",
        (
            f("booked_value", "amount"),
            f("currency_code", "currency"),
            f("booked", "date"),
            f("counterparty", "text"),
            f("reference", "text"),
        ),
        "bank statement lines",
        append=True,
    ),
    Archetype(
        "journals",
        "journal_id",
        (
            f("journal_type", "code"),
            f("posted", "ts"),
            f("period", "date"),
            f("description_text", "text"),
            f("reversed", "bool"),
        ),
        "ledger journals",
    ),
    Archetype(
        "cost_centres",
        "cost_centre_code",
        (
            f("cost_centre_name", "text"),
            f("parent_code", "code"),
            f("owner_team", "code"),
            f("active", "bool"),
        ),
        "cost centres",
        history=True,
    ),
    Archetype(
        "fixed_assets",
        "asset_id",
        (
            f("asset_class", "code"),
            f("acquired", "ts"),
            f("cost", "amount"),
            f("currency_code", "currency"),
            f("useful_life_months", "int"),
        ),
        "fixed asset register",
    ),
    Archetype(
        "depreciation_runs",
        "depreciation_id",
        (
            f("asset_id", "id"),
            f("period", "date"),
            f("depreciation", "amount"),
            f("currency_code", "currency"),
        ),
        "monthly depreciation",
    ),
    Archetype(
        "tax_codes",
        "tax_code",
        (
            f("tax_rate", "rate"),
            f("jurisdiction", "code"),
            f("valid_from", "ts"),
        ),
        "tax codes",
        history=True,
    ),
    Archetype(
        "vendors",
        "vendor_id",
        (
            f("vendor_name", "name"),
            f("country_code", "country"),
            f("payment_terms", "code"),
            f("email", "email"),
        ),
        "vendor master",
        history=True,
    ),
    Archetype(
        "intercompany",
        "intercompany_id",
        (
            f("counterparty_entity", "code"),
            f("settled", "amount"),
            f("currency_code", "currency"),
            f("posted", "ts"),
        ),
        "intercompany settlements",
    ),
    Archetype(
        "accruals",
        "accrual_id",
        (
            f("account_code", "code"),
            f("accrued", "amount"),
            f("currency_code", "currency"),
            f("period", "date"),
            f("reversed", "bool"),
        ),
        "month-end accruals",
    ),
    Archetype(
        "bank_accounts",
        "bank_account_id",
        (
            f("bank_name", "name"),
            f("currency_code", "currency"),
            f("iban_suffix", "code"),
            f("opened", "ts"),
        ),
        "bank accounts",
    ),
    Archetype(
        "periods",
        "period_id",
        (
            f("period_start", "date"),
            f("period_end", "date"),
            f("closed", "bool"),
            f("closed_on", "ts"),
        ),
        "accounting periods",
    ),
)

_WHOLESALE: tuple[Archetype, ...] = (
    Archetype(
        "accounts",
        "account_id",
        (
            f("company_name", "name"),
            f("country_code", "country"),
            f("credit_limit", "amount"),
            f("currency_code", "currency"),
            f("opened", "ts"),
        ),
        "wholesale accounts",
        history=True,
    ),
    Archetype(
        "price_agreements",
        "agreement_id",
        (
            f("account_id", "id"),
            f("sku", "sku"),
            f("net_price", "amount"),
            f("valid_from", "ts"),
            f("valid_to", "ts"),
        ),
        "negotiated price agreements",
    ),
    Archetype(
        "orders",
        "b2b_order_id",
        (
            f("account_id", "id"),
            f("placed", "ts"),
            f("currency_code", "currency"),
            f("total", "amount"),
            f("status", "status"),
            f("po_reference", "text"),
        ),
        "wholesale orders",
    ),
    Archetype(
        "order_lines",
        "b2b_order_line_id",
        (
            f("b2b_order_id", "id"),
            f("sku", "sku"),
            f("quantity", "qty"),
            f("net_price", "amount"),
        ),
        "wholesale order lines",
    ),
    Archetype(
        "invoices",
        "b2b_invoice_id",
        (
            f("b2b_order_id", "id"),
            f("invoiced_total", "amount"),
            f("currency_code", "currency"),
            f("invoiced", "ts"),
            f("due", "date"),
        ),
        "wholesale invoices",
    ),
    Archetype(
        "payments",
        "b2b_payment_id",
        (
            f("b2b_invoice_id", "id"),
            f("received_value", "amount"),
            f("received", "ts"),
            f("method", "code"),
        ),
        "wholesale payments",
    ),
    Archetype(
        "credit_notes",
        "credit_note_id",
        (
            f("b2b_invoice_id", "id"),
            f("credited", "amount"),
            f("issued", "ts"),
            f("reason", "code"),
        ),
        "wholesale credit notes",
    ),
    Archetype(
        "contacts",
        "contact_id",
        (f("account_id", "id"), f("email", "email"), f("phone", "phone"), f("role_code", "code")),
        "wholesale account contacts",
    ),
)

_RETURNS: tuple[Archetype, ...] = (
    Archetype(
        "return_requests",
        "return_request_id",
        (
            f("order_id", "id"),
            f("sku", "sku"),
            f("quantity", "qty"),
            f("reason_text", "text"),
            f("requested", "ts"),
            f("photos", "array"),
        ),
        "return requests",
    ),
    Archetype(
        "return_labels",
        "label_id",
        (f("return_request_id", "id"), f("carrier_code", "code"), f("created", "ts")),
        "return labels",
    ),
    Archetype(
        "inspections",
        "inspection_id",
        (
            f("return_request_id", "id"),
            f("grade", "code"),
            f("inspected", "ts"),
            f("notes", "text"),
        ),
        "returned item inspections",
    ),
    Archetype(
        "refunds_issued",
        "refund_issue_id",
        (
            f("return_request_id", "id"),
            f("refunded", "amount"),
            f("currency_code", "currency"),
            f("issued", "ts"),
        ),
        "refunds issued for returns",
    ),
)

_CATALOGUE: tuple[Archetype, ...] = (
    Archetype(
        "products",
        "product_id",
        (
            f("title", "text"),
            f("category_path", "text"),
            f("product_line", "code"),
            f("launched", "ts"),
            f("specs", "object"),
        ),
        "products",
        history=True,
    ),
    Archetype(
        "product_variants",
        "sku",
        (
            f("product_id", "id"),
            f("colour", "code"),
            f("size_label", "code"),
            f("weight_grams", "int"),
            f("barcodes", "array"),
        ),
        "product variants",
        children=(Child("barcodes", "barcodes", (f("barcode", "code"),), "variant barcodes"),),
        history=True,
    ),
    Archetype(
        "categories",
        "category_id",
        (f("parent_category_id", "id"), f("slug", "code"), f("display_name", "name")),
        "catalogue categories",
    ),
    Archetype(
        "price_lists",
        "price_list_id",
        (
            f("sku", "sku"),
            f("currency_code", "currency"),
            f("list_price", "amount"),
            f("valid_from", "ts"),
            f("valid_to", "ts"),
        ),
        "list prices",
        history=True,
    ),
    Archetype(
        "bundles",
        "bundle_id",
        (f("title", "text"), f("components", "array")),
        "product bundles",
        children=(
            Child(
                "components",
                "components",
                (f("sku", "sku"), f("quantity", "qty")),
                "bundle components",
            ),
        ),
    ),
    Archetype(
        "media",
        "media_id",
        (f("product_id", "id"), f("asset", "url"), f("position", "int")),
        "product media",
    ),
)

ARCHETYPES: dict[str, tuple[Archetype, ...]] = {
    "storefront": _STOREFRONT,
    "marketplace": _MARKETPLACE,
    "carrier": _CARRIER,
    "warehouse": _WAREHOUSE,
    "store": _STORE,
    "supplier": _SUPPLIER,
    "gateway": _GATEWAY,
    "ad_network": _AD_NETWORK,
    "messaging": _MESSAGING,
    "affiliate": _AFFILIATE,
    "support": _SUPPORT,
    "ledger": _LEDGER,
    "wholesale": _WHOLESALE,
    "returns": _RETURNS,
    "catalogue": _CATALOGUE,
}

# Clickstream collectors deliver one append-only event table; staging splits it by event type.
EVENT_TYPES: tuple[tuple[str, tuple[Field, ...]], ...] = (
    ("page_view", (f("title", "text", True), f("referrer", "url", True))),
    ("product_view", (f("sku", "sku", True), f("list_name", "code", True))),
    ("add_to_cart", (f("sku", "sku", True), f("quantity", "qty", True))),
    ("remove_from_cart", (f("sku", "sku", True), f("quantity", "qty", True))),
    ("cart_view", (f("item_count", "int", True),)),
    ("checkout_step", (f("step", "int", True), f("option", "code", True))),
    ("shipping_info", (f("shipping_tier", "code", True),)),
    ("payment_info", (f("payment_type", "code", True),)),
    ("checkout_complete", (f("order_id", "id", True), f("revenue", "amount", True))),
    ("search", (f("search_term", "text", True), f("result_count", "int", True))),
    ("filter_applied", (f("filter_name", "code", True), f("filter_value", "text", True))),
    ("sort_changed", (f("sort_order", "code", True),)),
    ("wishlist_add", (f("sku", "sku", True),)),
    ("review_open", (f("sku", "sku", True), f("rating_filter", "int", True))),
    ("video_play", (f("video_id", "id", True), f("position_seconds", "int", True))),
    ("promo_click", (f("promo_id", "id", True), f("creative", "code", True))),
    ("coupon_applied", (f("promo_code", "code", True),)),
    ("coupon_failed", (f("promo_code", "code", True), f("failure_reason", "code", True))),
    ("login", (f("method", "code", True),)),
    ("signup", (f("method", "code", True), f("newsletter", "bool", True))),
    ("consent_banner", (f("choice", "code", True),)),
    ("store_locator", (f("postcode", "postcode", True), f("result_count", "int", True))),
    ("size_guide", (f("sku", "sku", True),)),
    ("share", (f("sku", "sku", True), f("share_target", "code", True))),
    ("chat_open", (f("entry_point", "code", True),)),
    ("recommendation_click", (f("sku", "sku", True), f("slot", "int", True))),
    ("scroll_depth", (f("depth_percent", "int", True),)),
    ("outbound_link", (f("target", "url", True),)),
    ("error_shown", (f("error_code", "code", True), f("message", "text", True))),
    ("gift_message", (f("message_length", "int", True),)),
)
