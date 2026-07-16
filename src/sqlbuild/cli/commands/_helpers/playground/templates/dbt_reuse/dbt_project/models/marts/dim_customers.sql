with customers as (
    select * from {{ ref('stg_customers') }}
),

customer_orders as (
    select * from {{ ref('int_customer_orders') }}
)

select
    customers.customer_id,
    customers.full_name,
    customers.signup_date,
    coalesce(customer_orders.order_count, 0) as order_count,
    coalesce(customer_orders.lifetime_amount_cents, 0) as lifetime_amount_cents,
    customer_orders.first_order_date,
    customer_orders.most_recent_order_date
from customers
left join customer_orders on customer_orders.customer_id = customers.customer_id
