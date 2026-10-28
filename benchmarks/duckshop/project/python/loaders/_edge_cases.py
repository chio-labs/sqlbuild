"""Fixed rows for the edge-case area's raw tables.

Each row carries edge values that the edge models and their unit tests exercise. JSON documents are
written as raw text, exactly as a partner would send them, so key order, key case, number spelling
and escapes reach Snowflake unchanged. The rows never depend on `data_scale`.
"""

from __future__ import annotations

from datetime import datetime

Rows = list[dict[str, object]]


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text)


def partner_payloads() -> Rows:
    documents = [
        (
            "PM-1001",
            "mkt_eu",
            '{"sku": "MALLARD-01", "qty": 2, "amount": 19.990000000000002, '
            '"txn_id": 12345678901234567890, "gift": "yes", "placed_on": "2026-03-01", '
            '"colour": null, "channel": "web", "currency": "GBP", '
            '"items": [{"sku": "MALLARD-01", "qty": 2, "price": 4.995}, {"QTY": 2, "sku": "TEAL-02"}], '
            '"attrs": {"Size (cm)": "12", "a.b": "dotted", "a": {"b": "nested"}, '
            '"$discount": "5%", "": "blank", "*": "star", "$.a": "dollar path", "Sku": "MALLARD-01"}, '
            '"meta": {"order_id": "DS-O-1001"}, "tags": ["bath", "gift", "bath", null], '
            '"removed_tags": ["bath"], "extra_tags": ["gift"], "promo_code": "SPRING", '
            '"gift_code": null, "category_id": 2, "eligible_ids": [1, 2.0, 3], '
            '"pick_keys": ["sku", "qty"], "wanted": ["Size (cm)", "sku", "SKU", "a.b", ""], '
            '"lines": [{"sku": "MALLARD-01"}, {"sku": "TEAL-02"}], "tags_text": "bath,,gift"}',
            '{"sku": "MALLARD-01", "sku": "TEAL-02"}',
        ),
        (
            "PM-1002",
            "MKT_EU",
            '{"qty": "2.5", "amount": 1E+3, "txn_id": 9007199254740993, "gift": true, '
            '"colour": "teal", "channel": null, "currency": null, "items": [], '
            '"attrs": {"SKU": "TEAL-02", "sku": "teal-02"}, "tags": [], "removed_tags": [], '
            '"extra_tags": [], "category_id": "1", "eligible_ids": [1, 2.0, 3], "pick_keys": [], '
            '"wanted": [], "lines": [], "tags_text": ""}',
            "{'sku': 'TEAL-02', 'cart_id': 'CART-7'}",
        ),
        (
            "PM-1003",
            "giftbox",
            '{"qty": 2e0, "amount": -0, "txn_id": "00042", "gift": "N", "placed_on": null, '
            '"items": [{"sku": "EIDER-03"}], "attrs": "not an object", '
            '"tags": [1, 1.0, "1", {"b": 1, "a": 2}], "removed_tags": [1.0], "extra_tags": [1e0], '
            '"category_id": 3, "eligible_ids": [1, 2.0, 3e0], "lines": null, '
            '"note": "unit\\u001fseparator", "line": "para\\u2028graph"}',
            '"{\\"orderId\\": \\"DS-O-1003\\"}"',
        ),
        (
            "PM-1004",
            "giftbox",
            '{"qty": null, "amount": 1e-7, "gift": 0, '
            '"lines": {"sku": "PINTAIL-04", "qty": 1}, "\\u00e9": "precomposed", '
            '"e\\u0301": "combining", "tags_text": null}',
            '{"weight_kg": NaN, "lines": [1, 2,]}',
        ),
    ]
    rows: Rows = []
    for index, (message_id, partner_code, payload, payload_text) in enumerate(documents):
        rows.append(
            {
                "delivery_id": f"DL-{index + 1:04d}",
                "message_id": message_id,
                "partner_code": partner_code,
                "received_at": _at("2026-03-01 09:00:00"),
                "payload": payload,
                "payload_text": payload_text,
                "_loaded_at": _at("2026-03-01 10:00:00"),
            }
        )
    rows.append(
        {
            "delivery_id": "DL-0005",
            "message_id": "PM-1001",
            "partner_code": "mkt_eu",
            "received_at": _at("2026-03-01 08:00:00"),
            "payload": '{"sku": "MALLARD-01", "qty": 1}',
            "payload_text": None,
            "_loaded_at": _at("2026-03-01 09:30:00"),
        }
    )
    return rows


TABLES: dict[str, Rows] = {
    "edge__partner_payloads": partner_payloads(),
}
