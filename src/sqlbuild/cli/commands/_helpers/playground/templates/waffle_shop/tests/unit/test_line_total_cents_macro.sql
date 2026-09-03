TEST (mode macro, name "calculates_line_total_cents");

WITH
input_values AS (
  SELECT 950 AS price_cents, 3 AS quantity
),
__macro_actual__ AS (
  SELECT @line_total_cents("price_cents", "quantity") AS line_total_cents
  FROM input_values
),
__macro_expected__ AS (
  SELECT 2850 AS line_total_cents
)
SELECT 1
