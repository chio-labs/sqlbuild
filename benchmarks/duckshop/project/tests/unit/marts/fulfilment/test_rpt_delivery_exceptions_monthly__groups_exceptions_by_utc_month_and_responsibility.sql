TEST (name "rpt_delivery_exceptions_monthly__groups_exceptions_by_utc_month_and_responsibility");

WITH __ref__int_delivery_exceptions_classified AS (
  SELECT
    'X1' AS exception_id,
    'S1' AS shipment_id,
    'FLAPWING' AS carrier_code,
    'ADDR_INVALID' AS exception_code,
    'customer' AS responsibility,
    '2026-03-31 23:30:00 -02:00'::TIMESTAMP_TZ AS occurred_at,
    2.0::DECIMAL(10, 2) AS hours_to_resolve,
    NULL AS resolution_type,
    5.0::DECIMAL(18, 2) AS compensation_usd,
    NULL AS exception_rank_in_shipment
  UNION ALL
  SELECT
    'X2',
    'S2',
    'FLAPWING',
    'ADDR_INVALID',
    'customer',
    '2026-04-05 10:00:00 +00:00'::TIMESTAMP_TZ,
    4.0::DECIMAL(10, 2),
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'X3',
    'S2',
    'FLAPWING',
    'NOT_HOME',
    'customer',
    '2026-04-06 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    1.5::DECIMAL(18, 2),
    NULL
  UNION ALL
  SELECT
    'X4',
    'S3',
    'FLAPWING',
    'LOST_PARCEL',
    'carrier',
    '2026-03-02 10:00:00 +00:00'::TIMESTAMP_TZ,
    10.0::DECIMAL(10, 2),
    NULL,
    3.0::DECIMAL(18, 2),
    NULL
),

__expected__rpt_delivery_exceptions_monthly AS (
  SELECT
    '2026-04:FLAPWING:customer' AS exception_month_key,
    3 AS exceptions,
    2 AS shipments_affected,
    3.0::DECIMAL(10, 2) AS median_hours_to_resolve,
    6.5::DECIMAL(18, 2) AS compensation_usd,
    'ADDR_INVALID' AS top_exception_code
  UNION ALL
  SELECT
    '2026-03:FLAPWING:carrier' AS exception_month_key,
    1 AS exceptions,
    1 AS shipments_affected,
    10.0::DECIMAL(10, 2) AS median_hours_to_resolve,
    3.0::DECIMAL(18, 2) AS compensation_usd,
    'LOST_PARCEL' AS top_exception_code
),

__assert__exception_month_key_is_unique_and_present AS (
  SELECT t.exception_month_key
  FROM __ref("rpt_delivery_exceptions_monthly") AS t
  GROUP BY
    t.exception_month_key
  HAVING
    COUNT(*) > 1
    OR t.exception_month_key IS NULL
)
