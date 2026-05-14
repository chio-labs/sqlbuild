TEST();

WITH
__ref__local_only AS (
  SELECT 10 AS order_id
),
__expected__local_only AS (
  SELECT 10 AS order_id
)
SELECT 1
