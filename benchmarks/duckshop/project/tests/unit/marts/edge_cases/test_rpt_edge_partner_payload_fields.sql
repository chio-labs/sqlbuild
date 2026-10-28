TEST (name "rpt_edge_partner_payload_fields__counts_json_nulls_as_present_on_the_path");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    'MKT_EU' AS partner_code,
    PARSE_JSON('{"colour": null}') AS payload
  UNION ALL
  SELECT
    'PM-2',
    'MKT_EU',
    PARSE_JSON('{"colour": "teal"}')
  UNION ALL
  SELECT
    'PM-3',
    'MKT_EU',
    PARSE_JSON('{}')
  UNION ALL
  SELECT
    'PM-4',
    'MKT_EU',
    CAST(NULL AS VARIANT)
  UNION ALL
  SELECT
    'PM-5',
    NULL,
    PARSE_JSON('{"colour": null}')
),

__expected__rpt_edge_partner_payload_fields AS (
  SELECT
    'MKT_EU' AS partner_code,
    4 AS messages,
    1 AS colour_values,
    1 AS colour_json_nulls,
    1 AS colour_texts
  UNION ALL
  SELECT
    'UNKNOWN' AS partner_code,
    1 AS messages,
    0 AS colour_values,
    1 AS colour_json_nulls,
    0 AS colour_texts
)
