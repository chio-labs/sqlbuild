with orders as (
    select * from {{ ref('stg_orders') }}
)

select
    order_id,
    status,
    case when status = 'completed' then true else false end as is_completed,
    case when status = 'returned' then true else false end as is_returned
from orders
