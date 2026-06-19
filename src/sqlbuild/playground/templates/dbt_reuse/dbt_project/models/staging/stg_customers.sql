with source as (
    select * from {{ ref('raw_customers') }}
)

select
    customer_id,
    first_name,
    last_name,
    first_name || ' ' || last_name as full_name,
    cast(signup_date as date) as signup_date
from source
