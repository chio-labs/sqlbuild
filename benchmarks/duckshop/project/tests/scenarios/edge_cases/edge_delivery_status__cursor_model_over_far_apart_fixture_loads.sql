SCENARIO (
  description """
    The incremental delivery status, whose window comes from its cursor, builds over fixture loads a
    millennium apart and keeps the latest version of each shipment, as the full-history rebuild does
  """,
  tags ["edge_case"],
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
    ('DU-01', 'SH-1', 'DS-O-3001', 'label_created', '1899-12-30', NULL, 'I', 10, '1900-01-01 00:00:00'),
    ('DU-02', 'SH-1', 'DS-O-3001', 'delivered', '1899-12-30', '2999-12-29', 'U', 12, '2999-12-30 00:00:00'),
    ('DU-03', 'SH-1', 'DS-O-3001', 'in_transit', '1899-12-30', NULL, 'U', 11, '2999-12-30 00:00:00'),
    ('DU-04', 'SH-2', 'DS-O-3002', 'label_created', '2026-03-01', NULL, 'I', 20, '1900-01-01 00:00:00'),
    ('DU-05', 'SH-2', 'DS-O-3002', 'label_created', '2026-03-01', NULL, 'D', 21, '2999-12-30 00:00:00') AS v(delivery_id, shipment_id, order_ref, delivery_status, ordered_on, delivered_on, _op, _seq, _loaded_at)
),

expected_status AS (
  SELECT
    v.shipment_id,
    v.delivery_status,
    v.delivered_on::DATE AS delivered_on,
    v.is_deleted,
    v.latest_seq::NUMBER(38, 0) AS latest_seq,
    v.source_loaded_at::TIMESTAMP_NTZ AS source_loaded_at
  FROM VALUES
    ('SH-1', 'delivered', '2999-12-29', FALSE, 12, '2999-12-30 00:00:00'),
    ('SH-2', 'label_created', NULL, TRUE, 21, '2999-12-30 00:00:00') AS v(shipment_id, delivery_status, delivered_on, is_deleted, latest_seq, source_loaded_at)
),

__expected__int_edge_delivery_status AS (
  SELECT
    e.shipment_id,
    e.delivery_status,
    e.delivered_on,
    e.is_deleted,
    e.latest_seq,
    e.source_loaded_at
  FROM expected_status AS e
),

__expected__int_edge_delivery_status_rebuilt AS (
  SELECT
    e.shipment_id,
    e.delivery_status,
    e.delivered_on,
    e.is_deleted,
    e.latest_seq,
    e.source_loaded_at
  FROM expected_status AS e
)
