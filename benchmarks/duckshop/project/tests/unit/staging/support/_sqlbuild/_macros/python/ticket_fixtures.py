"""Fixture rows for tests that read staged support tickets."""

import json

_COLUMNS = (
    "ticket_id",
    "customer_email",
    "channel",
    "priority",
    "ticket_status",
    "created_at",
    "solved_at",
    "order_id",
    "contact_reason",
    "tag_list",
    "is_vip",
    "custom_fields",
    "source_seq",
    "source_loaded_at",
)


def _text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def tagged_tickets(rows: list[list[object]]) -> str:
    """One stg_tickets row per [ticket_id, tags, labels] entry; other columns are typed NULLs."""
    selects = []
    for ticket_id, tags, labels in rows:
        custom_fields = {} if labels is None else {"labels": labels}
        values = {
            "ticket_id": _text(str(ticket_id)),
            "customer_email": "CAST(NULL AS VARCHAR)",
            "channel": "'email'",
            "priority": "CAST(NULL AS INT)",
            "ticket_status": "'open'",
            "created_at": "CAST(NULL AS TIMESTAMP_LTZ)",
            "solved_at": "CAST(NULL AS TIMESTAMP_TZ)",
            "order_id": "CAST(NULL AS VARCHAR)",
            "contact_reason": "CAST(NULL AS VARCHAR)",
            "tag_list": f"PARSE_JSON({_text(json.dumps(tags))})::ARRAY",
            "is_vip": "FALSE",
            "custom_fields": f"PARSE_JSON({_text(json.dumps(custom_fields))})::OBJECT",
            "source_seq": "CAST(NULL AS NUMBER(38, 0))",
            "source_loaded_at": "CAST(NULL AS TIMESTAMP_NTZ)",
        }
        selects.append("SELECT " + ", ".join(f"{values[c]} AS {c}" for c in _COLUMNS))
    return " UNION ALL ".join(selects)
