with source as (
    select * from {{ ref('raw_payments') }}
)

select
    payment_id,
    order_id,
    payment_method,
    amount_cents,
    amount_cents / 100.0 as amount_usd
from source
