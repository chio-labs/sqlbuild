with orders as (
    select * from {{ ref('fct_orders') }}
)

select
    order_date,
    count(*) as order_count,
    sum(order_amount_cents) as revenue_cents,
    sum(order_amount_cents) / 100.0 as revenue_usd
from orders
where is_completed
group by 1
order by 1
