{{ config(tags=['finance']) }}

select order_id, ordered_at from {{ ref('stg_orders') }}
