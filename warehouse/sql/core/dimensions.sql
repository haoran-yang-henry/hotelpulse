-- Conformed dimensions sourced from the PMS (dim_date and dim_channel are static, see migrations).

INSERT INTO core.dim_hotel AS d (
    hotel_id, hotel_code, hotel_name, city, country_code, timezone, total_rooms, pms_live_date
)
SELECT
    hotel_id,
    hotel_code,
    hotel_name,
    city,
    country_code,
    timezone,
    total_rooms,
    pms_live_date
FROM staging.pms_hotels
ON CONFLICT (hotel_id) DO UPDATE SET
    hotel_code = excluded.hotel_code,
    hotel_name = excluded.hotel_name,
    city = excluded.city,
    country_code = excluded.country_code,
    timezone = excluded.timezone,
    total_rooms = excluded.total_rooms,
    pms_live_date = excluded.pms_live_date,
    updated_at = now()
WHERE (d.hotel_code, d.hotel_name, d.city, d.country_code, d.timezone, d.total_rooms, d.pms_live_date)
IS DISTINCT FROM (
    excluded.hotel_code, excluded.hotel_name, excluded.city,
    excluded.country_code, excluded.timezone, excluded.total_rooms, excluded.pms_live_date
);

INSERT INTO core.dim_room_type AS d (hotel_id, room_type_code, room_type_name, room_count)
SELECT
    hotel_id,
    room_type_code,
    room_type_name,
    room_count
FROM staging.pms_room_types
ON CONFLICT (hotel_id, room_type_code) DO UPDATE SET
    room_type_name = excluded.room_type_name,
    room_count = excluded.room_count,
    updated_at = now()
WHERE (d.room_type_name, d.room_count) IS DISTINCT FROM (excluded.room_type_name, excluded.room_count);
