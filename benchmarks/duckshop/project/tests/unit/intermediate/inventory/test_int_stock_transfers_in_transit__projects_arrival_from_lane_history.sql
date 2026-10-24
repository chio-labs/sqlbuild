TEST (name "int_stock_transfers_in_transit__projects_arrival_from_lane_history");

WITH __ref__stg_stock_transfers AS (
  SELECT
    'T1' AS transfer_id,
    'DUCK-1' AS sku,
    'W1' AS from_warehouse_code,
    'W2' AS to_warehouse_code,
    1 AS qty,
    '2026-03-01 00:00:00 +00:00'::TIMESTAMP_TZ AS shipped_at,
    '2026-03-01 20:00:00 +00:00'::TIMESTAMP_TZ AS arrived_at,
    20 AS transit_hours,
    NULL AS haulier_reference,
    NULL AS tracking,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'T2',
    'DUCK-1',
    'W1',
    'W2',
    1,
    '2026-03-02 00:00:00 +00:00'::TIMESTAMP_TZ,
    '2026-03-03 06:00:00 +00:00'::TIMESTAMP_TZ,
    30,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T3',
    'DUCK-1',
    'W1',
    'W2',
    4,
    '2026-03-29 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T4',
    'DUCK-2',
    'W2',
    'W3',
    2,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_stock_transfers_in_transit AS (
  SELECT
    'T1' AS transfer_id,
    'arrived' AS transfer_state,
    25.0::DECIMAL(10, 2) AS lane_median_transit_hours,
    FALSE AS is_overdue
  UNION ALL
  SELECT
    'T2' AS transfer_id,
    'arrived' AS transfer_state,
    25.0::DECIMAL(10, 2) AS lane_median_transit_hours,
    FALSE AS is_overdue
  UNION ALL
  SELECT
    'T3' AS transfer_id,
    'in_transit' AS transfer_state,
    25.0::DECIMAL(10, 2) AS lane_median_transit_hours,
    TRUE AS is_overdue
  UNION ALL
  SELECT
    'T4' AS transfer_id,
    'planned' AS transfer_state,
    CAST(NULL AS DECIMAL(10, 2)) AS lane_median_transit_hours,
    CAST(NULL AS BOOLEAN) AS is_overdue
),

__assert__arrival_is_shipped_plus_lane_median AS (
  SELECT t.transfer_id
  FROM __ref("int_stock_transfers_in_transit") AS t
  WHERE
    t.transfer_id = 'T3'
    AND t.expected_arrival_at <> '2026-03-30 01:00:00 +00:00'::TIMESTAMP_TZ
)
