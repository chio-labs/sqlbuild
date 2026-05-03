MODEL (
  materialized view,
  tags [staging],
);

SELECT
  id AS customer_id,
  first_name,
  last_name,
  email,
  created_at
FROM __source("raw_customers")
