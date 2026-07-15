with order_payments as (
    select * from {{ ref('int_order_payments') }}
)

select
    customer_id,
    count(*) as order_count,
    sum(order_amount_cents) as lifetime_amount_cents,
    min(order_date) as first_order_date,
    max(order_date) as most_recent_order_date
from order_payments
group by 1
