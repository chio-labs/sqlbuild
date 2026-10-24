TEST (name "int_cross_device_identity__merges_web_visitors_and_app_devices");

WITH __ref__stg_web_identifies AS (
  SELECT
    'V1:C1' AS identity_link_key,
    'V1' AS anonymous_id,
    'C1' AS customer_id,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS first_seen_at_utc,
    NULL AS last_seen_at_utc,
    NULL AS event_count,
    NULL AS identify_methods
  UNION ALL
  SELECT
    'V2:C1',
    'V2',
    'C1',
    '2026-03-05 10:00:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'V3:C2',
    'V3',
    'C2',
    '2026-03-02 10:00:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    NULL
),

__ref__stg_app_events AS (
  SELECT
    'a1' AS event_id,
    NULL AS received_at,
    'phone' AS platform,
    NULL AS app_version,
    NULL AS app_major_version,
    NULL AS event_name,
    '2026-02-28 09:00:00'::TIMESTAMP_NTZ AS event_at_utc,
    'D1' AS device_id,
    'C1' AS customer_id,
    NULL AS screen_name,
    NULL AS attributes
  UNION ALL
  SELECT
    'a2',
    NULL,
    'phone',
    NULL,
    NULL,
    NULL,
    '2026-03-03 09:00:00'::TIMESTAMP_NTZ,
    'D1',
    'C1',
    NULL,
    NULL
  UNION ALL
  SELECT
    'a3',
    NULL,
    'tablet',
    NULL,
    NULL,
    NULL,
    '2026-03-04 09:00:00'::TIMESTAMP_NTZ,
    'D2',
    'C1',
    NULL,
    NULL
  UNION ALL
  SELECT
    'a4',
    NULL,
    'tablet',
    NULL,
    NULL,
    NULL,
    '2026-01-01 09:00:00'::TIMESTAMP_NTZ,
    NULL,
    'C1',
    NULL,
    NULL
  UNION ALL
  SELECT
    'a5',
    NULL,
    'phone',
    NULL,
    NULL,
    NULL,
    '2026-01-01 09:00:00'::TIMESTAMP_NTZ,
    'D9',
    NULL,
    NULL,
    NULL
),

__expected__int_cross_device_identity AS (
  SELECT
    'C1' AS customer_id,
    2 AS web_visitor_count,
    2 AS app_device_count,
    TRUE AS is_multi_device,
    '2026-02-28 09:00:00'::TIMESTAMPNTZ AS first_seen_at_utc
  UNION ALL
  SELECT
    'C2' AS customer_id,
    1 AS web_visitor_count,
    0 AS app_device_count,
    FALSE AS is_multi_device,
    '2026-03-02 10:00:00'::TIMESTAMPNTZ AS first_seen_at_utc
),

__assert__platforms_are_sorted AS (
  SELECT i.customer_id
  FROM __ref("int_cross_device_identity") AS i
  WHERE ARRAY_TO_STRING(i.platforms, ',') <> IFF(i.customer_id = 'C1', 'phone,tablet,web', 'web')
),

__assert__identity_graph_lists_identifiers_per_platform AS (
  SELECT i.customer_id
  FROM __ref("int_cross_device_identity") AS i
  WHERE
    i.customer_id = 'C1'
    AND (
      ARRAY_SIZE(i.identity_graph:phone) <> 1
      OR i.identity_graph:web[1]::VARCHAR <> 'V2'
    )
)
