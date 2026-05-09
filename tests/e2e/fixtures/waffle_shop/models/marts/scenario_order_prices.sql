MODEL (
  materialized table,
  tags [marts, scenario],
  description "Small model used by scenario CLI e2e retain coverage.",
);

SELECT
  o.id AS order_id,
  o.quantity,
  w.waffle_name,
  w.price_cents,
  w.price_cents * o.quantity AS line_total_cents,
  p.amount_cents AS payment_amount_cents
FROM __source("raw_orders") o
INNER JOIN __seed("waffle_types") w ON o.waffle_type_id = w.waffle_type_id
LEFT JOIN __ref("stg_payments") p ON o.id = p.order_id
