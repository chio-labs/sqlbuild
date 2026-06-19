with payments as (
    select * from {{ ref('stg_payments') }}
),

orders as (
    select * from {{ ref('stg_orders') }}
)

select
    payments.payment_id,
    payments.order_id,
    orders.customer_id,
    payments.payment_method,
    payments.amount_cents,
    payments.amount_usd
from payments
left join orders on orders.order_id = payments.order_id
