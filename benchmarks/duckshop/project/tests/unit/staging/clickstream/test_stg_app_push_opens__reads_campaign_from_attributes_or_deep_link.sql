TEST (name "stg_app_push_opens__reads_campaign_from_attributes_or_deep_link");

WITH __ref__stg_app_events AS (
  SELECT
    'e1' AS event_id,
    NULL AS received_at,
    'phone' AS platform,
    NULL AS app_version,
    NULL AS app_major_version,
    'push_open' AS event_name,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS event_at_utc,
    'D1' AS device_id,
    'C1' AS customer_id,
    NULL AS screen_name,
    PARSE_JSON('{"campaign_id": "CMP1", "deep_link": "duckshop://app/sale?cid=CMP9"}')::OBJECT AS attributes
  UNION ALL
  SELECT
    'e2',
    NULL,
    'phone',
    NULL,
    NULL,
    'push_open',
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ,
    'D1',
    NULL,
    NULL,
    PARSE_JSON('{"deep_link": "duckshop://app/p/duck-1?cid=SPRING-26"}')::OBJECT
  UNION ALL
  SELECT
    'e3',
    NULL,
    'phone',
    NULL,
    NULL,
    'screen_view',
    '2026-03-10 11:00:05'::TIMESTAMP_NTZ,
    'D1',
    NULL,
    NULL,
    PARSE_JSON('{"deep_link": "duckshop://app/x"}')::OBJECT
  UNION ALL
  SELECT
    'e4',
    NULL,
    'phone',
    NULL,
    NULL,
    'push_open',
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ,
    'D2',
    NULL,
    NULL,
    PARSE_JSON('{}')::OBJECT
),

__expected__stg_app_push_opens AS (
  SELECT
    'e1' AS event_id,
    'C1' AS customer_id,
    'CMP1' AS push_campaign_id,
    '/sale?cid=CMP9' AS deep_link_path
  UNION ALL
  SELECT
    'e2' AS event_id,
    CAST(NULL AS VARCHAR) AS customer_id,
    'SPRING-26' AS push_campaign_id,
    '/p/duck-1?cid=SPRING-26' AS deep_link_path
  UNION ALL
  SELECT
    'e4' AS event_id,
    CAST(NULL AS VARCHAR) AS customer_id,
    CAST(NULL AS VARCHAR) AS push_campaign_id,
    CAST(NULL AS VARCHAR) AS deep_link_path
)
