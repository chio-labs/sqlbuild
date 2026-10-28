TEST (
  name "fct_edge_delivery_events__emits_deliveries_outside_the_window_it_deletes",
  cursor_start "2026-02-27",
  cursor_end "2026-02-28",
);

WITH __source__edge__delivery_updates AS (
  SELECT
    v.delivery_id,
    v.shipment_id,
    NULL AS order_ref,
    NULL AS delivery_status,
    v.ordered_on::DATE AS ordered_on,
    v.delivered_on::DATE AS delivered_on,
    'I' AS _op,
    v._seq::NUMBER(38, 0) AS _seq,
    '2026-03-02 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('DU-01', 'SH-1', '2026-02-27', '2026-02-27', 1),
    ('DU-02', 'SH-2', '2026-02-27', '2026-03-04', 2),
    ('DU-03', 'SH-3', '2026-02-26', '2026-02-27', 3),
    ('DU-04', 'SH-4', '2026-02-27', NULL, 4) AS v(delivery_id, shipment_id, ordered_on, delivered_on, _seq)
),

__expected__fct_edge_delivery_events AS (
  SELECT
    'DU-01' AS delivery_id,
    '2026-02-27'::DATE AS ordered_on,
    '2026-02-27'::DATE AS delivered_on
  UNION ALL
  SELECT
    'DU-02' AS delivery_id,
    '2026-02-27'::DATE AS ordered_on,
    '2026-03-04'::DATE AS delivered_on
)
