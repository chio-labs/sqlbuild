MODEL (tags [nightly, finance]);

select order_id from __dbt_ref("analytics", "fact_orders")
