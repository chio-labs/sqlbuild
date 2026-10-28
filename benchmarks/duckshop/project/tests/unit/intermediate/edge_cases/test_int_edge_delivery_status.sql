TEST (name "int_edge_delivery_status__keeps_the_latest_version_of_every_shipment");

WITH __source__edge__delivery_updates AS (
  SELECT
    v.delivery_id,
    v.shipment_id,
    v.order_ref,
    v.delivery_status,
    v.ordered_on::DATE AS ordered_on,
    v.delivered_on::DATE AS delivered_on,
    v._op,
    v._seq::NUMBER(38, 0) AS _seq,
    v._loaded_at::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('DU-01', 'SH-1', 'DS-O-3001', 'label_created', '2026-02-27', NULL, 'I', 10, '2026-03-01 10:00:00'),
    ('DU-02', 'SH-1', 'DS-O-3001', 'in_transit', '2026-02-27', NULL, 'U', 12, '2026-03-01 10:00:00'),
    ('DU-03', 'SH-2', 'DS-O-3002', 'label_created', '2026-02-28', NULL, 'I', 20, '2026-03-01 10:00:00'),
    ('DU-04', 'SH-3', 'DS-O-3003', 'delivered', '2026-02-20', '2026-02-25', 'I', 30, '2026-03-01 10:00:00'),
    ('DU-05', 'SH-4', 'DS-O-3004', 'in_transit', '2026-02-26', NULL, 'I', 40, '2026-03-01 10:00:00'),
    ('DU-06', 'SH-1', 'DS-O-3001', 'picked_up', '2026-02-27', NULL, 'U', 11, '2026-03-02 10:00:00'),
    ('DU-07', 'SH-2', 'DS-O-3002', 'label_created', '2026-02-28', NULL, 'I', 20, '2026-03-02 10:00:00'),
    ('DU-08', 'SH-2', 'DS-O-3002', 'delivered', '2026-02-28', '2026-03-02', 'U', 21, '2026-03-02 10:00:00'),
    ('DU-09', 'SH-4', 'DS-O-3004', 'in_transit', '2026-02-26', NULL, 'D', 41, '2026-03-02 10:00:00'),
    ('DU-10', 'SH-5', 'DS-O-3005', 'label_created', '2026-03-01', NULL, 'I', 50, '2026-03-02 10:00:00'),
    ('DU-11', 'SH-6', 'DS-O-3006', 'label_created', '2026-03-02', NULL, 'I', 60, '2026-03-03 10:00:00') AS v(delivery_id, shipment_id, order_ref, delivery_status, ordered_on, delivered_on, _op, _seq, _loaded_at)
),

__expected__int_edge_delivery_status AS (
  SELECT
    'SH-1' AS shipment_id,
    'DS-O-3001' AS order_ref,
    'in_transit' AS delivery_status,
    CAST(NULL AS DATE) AS delivered_on,
    FALSE AS is_deleted,
    12 AS latest_seq,
    '2026-03-02 10:00:00'::TIMESTAMP_NTZ(9) AS source_loaded_at
  UNION ALL
  SELECT
    'SH-2' AS shipment_id,
    'DS-O-3002' AS order_ref,
    'delivered' AS delivery_status,
    '2026-03-02'::DATE AS delivered_on,
    FALSE AS is_deleted,
    21 AS latest_seq,
    '2026-03-02 10:00:00'::TIMESTAMP_NTZ(9) AS source_loaded_at
  UNION ALL
  SELECT
    'SH-3' AS shipment_id,
    'DS-O-3003' AS order_ref,
    'delivered' AS delivery_status,
    '2026-02-25'::DATE AS delivered_on,
    FALSE AS is_deleted,
    30 AS latest_seq,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ(9) AS source_loaded_at
  UNION ALL
  SELECT
    'SH-4' AS shipment_id,
    'DS-O-3004' AS order_ref,
    'in_transit' AS delivery_status,
    CAST(NULL AS DATE) AS delivered_on,
    TRUE AS is_deleted,
    41 AS latest_seq,
    '2026-03-02 10:00:00'::TIMESTAMP_NTZ(9) AS source_loaded_at
  UNION ALL
  SELECT
    'SH-5' AS shipment_id,
    'DS-O-3005' AS order_ref,
    'label_created' AS delivery_status,
    CAST(NULL AS DATE) AS delivered_on,
    FALSE AS is_deleted,
    50 AS latest_seq,
    '2026-03-02 10:00:00'::TIMESTAMP_NTZ(9) AS source_loaded_at
  UNION ALL
  SELECT
    'SH-6' AS shipment_id,
    'DS-O-3006' AS order_ref,
    'label_created' AS delivery_status,
    CAST(NULL AS DATE) AS delivered_on,
    FALSE AS is_deleted,
    60 AS latest_seq,
    '2026-03-03 10:00:00'::TIMESTAMP_NTZ(9) AS source_loaded_at
)

TEST (
  name "int_edge_delivery_status__recomputes_shipments_touched_in_the_window_from_history",
  cursor_start "2026-03-02 00:00:00",
  cursor_end "2026-03-03 00:00:00",
);

WITH __source__edge__delivery_updates AS (
  SELECT
    v.delivery_id,
    v.shipment_id,
    v.order_ref,
    v.delivery_status,
    v.ordered_on::DATE AS ordered_on,
    v.delivered_on::DATE AS delivered_on,
    v._op,
    v._seq::NUMBER(38, 0) AS _seq,
    v._loaded_at::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('DU-01', 'SH-1', 'DS-O-3001', 'label_created', '2026-02-27', NULL, 'I', 10, '2026-03-01 10:00:00'),
    ('DU-02', 'SH-1', 'DS-O-3001', 'in_transit', '2026-02-27', NULL, 'U', 12, '2026-03-01 10:00:00'),
    ('DU-03', 'SH-2', 'DS-O-3002', 'label_created', '2026-02-28', NULL, 'I', 20, '2026-03-01 10:00:00'),
    ('DU-04', 'SH-3', 'DS-O-3003', 'delivered', '2026-02-20', '2026-02-25', 'I', 30, '2026-03-01 10:00:00'),
    ('DU-05', 'SH-4', 'DS-O-3004', 'in_transit', '2026-02-26', NULL, 'I', 40, '2026-03-01 10:00:00'),
    ('DU-06', 'SH-1', 'DS-O-3001', 'picked_up', '2026-02-27', NULL, 'U', 11, '2026-03-02 10:00:00'),
    ('DU-07', 'SH-2', 'DS-O-3002', 'label_created', '2026-02-28', NULL, 'I', 20, '2026-03-02 10:00:00'),
    ('DU-08', 'SH-2', 'DS-O-3002', 'delivered', '2026-02-28', '2026-03-02', 'U', 21, '2026-03-02 10:00:00'),
    ('DU-09', 'SH-4', 'DS-O-3004', 'in_transit', '2026-02-26', NULL, 'D', 41, '2026-03-02 10:00:00'),
    ('DU-10', 'SH-5', 'DS-O-3005', 'label_created', '2026-03-01', NULL, 'I', 50, '2026-03-02 10:00:00'),
    ('DU-11', 'SH-6', 'DS-O-3006', 'label_created', '2026-03-02', NULL, 'I', 60, '2026-03-03 10:00:00') AS v(delivery_id, shipment_id, order_ref, delivery_status, ordered_on, delivered_on, _op, _seq, _loaded_at)
),

__expected__int_edge_delivery_status AS (
  SELECT
    'SH-1' AS shipment_id,
    'DS-O-3001' AS order_ref,
    'in_transit' AS delivery_status,
    CAST(NULL AS DATE) AS delivered_on,
    FALSE AS is_deleted,
    12 AS latest_seq,
    '2026-03-02 10:00:00'::TIMESTAMP_NTZ(9) AS source_loaded_at
  UNION ALL
  SELECT
    'SH-2' AS shipment_id,
    'DS-O-3002' AS order_ref,
    'delivered' AS delivery_status,
    '2026-03-02'::DATE AS delivered_on,
    FALSE AS is_deleted,
    21 AS latest_seq,
    '2026-03-02 10:00:00'::TIMESTAMP_NTZ(9) AS source_loaded_at
  UNION ALL
  SELECT
    'SH-4' AS shipment_id,
    'DS-O-3004' AS order_ref,
    'in_transit' AS delivery_status,
    CAST(NULL AS DATE) AS delivered_on,
    TRUE AS is_deleted,
    41 AS latest_seq,
    '2026-03-02 10:00:00'::TIMESTAMP_NTZ(9) AS source_loaded_at
  UNION ALL
  SELECT
    'SH-5' AS shipment_id,
    'DS-O-3005' AS order_ref,
    'label_created' AS delivery_status,
    CAST(NULL AS DATE) AS delivered_on,
    FALSE AS is_deleted,
    50 AS latest_seq,
    '2026-03-02 10:00:00'::TIMESTAMP_NTZ(9) AS source_loaded_at
)
