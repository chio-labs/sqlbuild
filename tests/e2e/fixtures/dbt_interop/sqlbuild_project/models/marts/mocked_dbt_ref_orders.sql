MODEL (tags [sqb_only]);

SELECT
  one_arg.order_id,
  package_ref.package_order_id
FROM __dbt_ref("fact_orders") AS one_arg
JOIN __dbt_ref("analytics", "fact_orders") AS package_ref
  ON one_arg.order_id = package_ref.order_id
