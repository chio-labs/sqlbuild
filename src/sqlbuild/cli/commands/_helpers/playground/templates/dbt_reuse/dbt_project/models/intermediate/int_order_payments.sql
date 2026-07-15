with orders as (
    select * from {{ ref('stg_orders') }}
),

payments as (
    select * from {{ ref('stg_payments') }}
),

statuses as (
    select * from {{ ref('stg_order_statuses') }}
)

select
    orders.order_id,
    orders.customer_id,
    orders.order_date,
    statuses.is_completed,
    statuses.is_returned,
    coalesce(sum(payments.amount_cents), 0) as order_amount_cents
from orders
left join payments on payments.order_id = orders.order_id
left join statuses on statuses.order_id = orders.order_id
group by 1, 2, 3, 4, 5
