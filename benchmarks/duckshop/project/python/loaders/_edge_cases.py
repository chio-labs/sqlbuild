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


def gateway_callbacks() -> Rows:
    callbacks = [
        # zone, wall time, zoned event, nanosecond event, free text, business date, period, body
        (
            "Europe/London",
            "2026-03-29 01:30:00",
            "2026-03-01 10:00:00 +05:45",
            "2026-03-01 23:59:59.9999995",
            "2026-03-01T10:15:00Z",
            "2026-01-31",
            ("2026-03-31 23:59:00", "2026-04-01 00:01:00"),
            '{"ts_ms": 1772359200000}',
        ),
        (
            "Europe/London",
            "2026-10-25 01:30:00",
            "2026-03-01 04:15:00 -00:00",
            "2026-03-01 10:00:00.0005",
            "01-MAR-26 10:15",
            "2028-02-29",
            ("2026-01-31 00:00:00", "2026-02-01 00:00:00"),
            '{"ts_ms": "1772359200000"}',
        ),
        (
            "America/New_York",
            "2026-11-01 01:30:00",
            "2026-02-28 18:45:00 -09:30",
            "1962-07-01 12:00:00.123456789",
            "2026-03-01 24:00:00",
            "2026-12-27",
            ("2028-02-28 12:00:00", "2028-03-01 12:00:00"),
            '{"ts_ms": 1772359200}',
        ),
        (
            "Australia/Sydney",
            "2026-04-05 02:30:00",
            "2026-03-01 23:30:00 +05:45",
            "2250-06-01 00:00:00.123456",
            "  2026-3-1 7:5:0  ",
            "2027-01-03",
            ("2026-03-01 10:00:59", "2026-03-01 10:01:00"),
            "{}",
        ),
    ]
    rows: Rows = []
    for index, (zone, wall, zoned, nano, text, business, period, body) in enumerate(callbacks):
        rows.append(
            {
                "callback_id": f"CB-{index + 1:04d}",
                "merchant_zone": zone,
                "local_wall_time": wall,
                "event_at": zoned,
                "event_at_ns": nano,
                "event_time_text": text,
                "business_date": business,
                "period_start": period[0],
                "period_end": period[1],
                "body": body,
                "_loaded_at": _at("2026-03-02 00:00:00"),
            }
        )
    return rows


def price_windows() -> Rows:
    windows = [
        ("MALLARD-01", 1299, None, None),
        ("TEAL-02", 899, "0001-01-01 00:00:00", "9999-12-31 23:59:59.999999"),
        ("EIDER-03", 2450, "2026-01-01 00:00:00", None),
        ("PINTAIL-04", 1575, "1969-12-31 23:59:59.999999", "1970-01-01 00:00:00.000001"),
    ]
    return [
        {
            "window_id": f"PW-{index + 1:04d}",
            "sku": sku,
            "price_minor": price,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "_loaded_at": _at("2026-03-02 00:00:00"),
        }
        for index, (sku, price, valid_from, valid_to) in enumerate(windows)
    ]


TABLES: dict[str, Rows] = {
    "edge__partner_payloads": partner_payloads(),
    "edge__gateway_callbacks": gateway_callbacks(),
    "edge__price_windows": price_windows(),
}
