TEST (mode table_fn, name "table_fn__customer_orders__returns_nothing_for_unknown_customers");

WITH __table_fn_actual__ AS (
  SELECT
    o.order_id,
    o.order_number
  FROM __table_fn("table_fn__customer_orders")('DS-NO-SUCH-CUSTOMER') AS o
),

__table_fn_expected__ AS (
  SELECT
    CAST(NULL AS VARCHAR) AS order_id,
    CAST(NULL AS INT) AS order_number
  WHERE FALSE
)
