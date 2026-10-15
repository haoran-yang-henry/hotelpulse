-- Rebuild the room nights of exactly the reservations that changed in this batch
-- (delete + insert keyed on reservation_id): incremental and idempotent.

DELETE FROM core.fct_room_night AS rn
USING core.fct_reservation AS f
WHERE
    rn.reservation_id = f.reservation_id
    AND f._batch_id = '{{ run_id }}';

INSERT INTO core.fct_room_night (
    reservation_id, stay_date, hotel_id, room_type_code, channel_code, status, is_sold,
    created_at, canceled_at, room_revenue, commission_cost, _batch_id
)
SELECT
    f.reservation_id,
    night::date AS stay_date,
    f.hotel_id,
    coalesce(f.assigned_room_type, f.reserved_room_type) AS room_type_code,
    f.channel_code,
    f.status,
    f.status IN ('confirmed', 'checked_in', 'checked_out') AS is_sold,
    f.created_at,
    f.canceled_at,
    coalesce(f.adr, 0) AS room_revenue,
    round(coalesce(f.adr, 0) * c.commission_rate, 2) AS commission_cost,
    f._batch_id
FROM core.fct_reservation AS f
INNER JOIN core.dim_channel AS c ON f.channel_code = c.channel_code
CROSS JOIN
    LATERAL
    generate_series(f.arrival_date::timestamp, (f.departure_date - 1)::timestamp, interval '1 day') AS night
WHERE
    f._batch_id = '{{ run_id }}'
    AND f.nights > 0;
