{{ config(tags=['finance']) }}

select order_id from {{ ref('stg_orders') }}
