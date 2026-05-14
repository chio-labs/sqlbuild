{{ config(tags=['nightly', 'staging']) }}

select 1 as order_id, cast('2026-01-01 00:00:00' as timestamp) as ordered_at
