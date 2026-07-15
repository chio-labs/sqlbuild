with order_payments as (
    select * from {{ ref('int_order_payments') }}
)

select
    order_id,
    customer_id,
    order_date,
    is_completed,
    is_returned,
    order_amount_cents,
    order_amount_cents / 100.0 as order_amount_usd
from order_payments
