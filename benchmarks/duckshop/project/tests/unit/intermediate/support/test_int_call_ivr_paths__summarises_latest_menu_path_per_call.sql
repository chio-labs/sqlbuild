TEST (name "int_call_ivr_paths__summarises_latest_menu_path_per_call");

WITH __source__support__call_records AS (
  SELECT
    'C1' AS call_id,
    NULL AS ticket_id,
    NULL AS agent_id,
    NULL AS phone_number,
    NULL AS started_at,
    NULL AS duration_seconds,
    PARSE_JSON('["Orders", "Returns"]')::VARIANT AS ivr_path,
    NULL AS _op,
    1 AS _seq,
    NULL AS _loaded_at
  UNION ALL
  SELECT
    'C1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    PARSE_JSON('["ORDERS", "returns", "orders", "self_service_complete"]')::VARIANT,
    NULL,
    2,
    NULL
  UNION ALL
  SELECT
    'C2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    PARSE_JSON('["billing"]')::VARIANT,
    NULL,
    1,
    NULL
  UNION ALL
  SELECT
    'C4',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    PARSE_JSON('["support", "hold"]')::VARIANT,
    NULL,
    1,
    NULL
),

__ref__stg_call_records AS (
  SELECT
    'C1' AS call_id,
    NULL AS ticket_id,
    NULL AS agent_id,
    NULL AS caller_phone,
    '44' AS caller_country_prefix,
    NULL AS started_at,
    45 AS duration_seconds,
    NULL AS ivr_path,
    NULL AS ivr_depth,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'C2',
    NULL,
    'A1',
    NULL,
    '1',
    NULL,
    400,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'C3',
    NULL,
    NULL,
    NULL,
    '965',
    NULL,
    1000,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'C4',
    NULL,
    'A2',
    NULL,
    NULL,
    NULL,
    120,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_call_ivr_paths AS (
  SELECT
    'C1' AS call_id,
    'orders' AS first_menu_choice,
    'self_service_complete' AS final_menu_node,
    4 AS menu_steps,
    1 AS repeated_menu_visits,
    FALSE AS abandoned_in_ivr,
    'EU' AS caller_region,
    'under_1m' AS duration_bucket
  UNION ALL
  SELECT
    'C2' AS call_id,
    'billing' AS first_menu_choice,
    'billing' AS final_menu_node,
    1 AS menu_steps,
    0 AS repeated_menu_visits,
    FALSE AS abandoned_in_ivr,
    'US' AS caller_region,
    '5_to_15m' AS duration_bucket
  UNION ALL
  SELECT
    'C3' AS call_id,
    CAST(NULL AS VARCHAR) AS first_menu_choice,
    CAST(NULL AS VARCHAR) AS final_menu_node,
    0 AS menu_steps,
    0 AS repeated_menu_visits,
    TRUE AS abandoned_in_ivr,
    'MENA' AS caller_region,
    'over_15m' AS duration_bucket
  UNION ALL
  SELECT
    'C4' AS call_id,
    'support' AS first_menu_choice,
    'hold' AS final_menu_node,
    2 AS menu_steps,
    0 AS repeated_menu_visits,
    FALSE AS abandoned_in_ivr,
    'EU' AS caller_region,
    '1_to_5m' AS duration_bucket
)
