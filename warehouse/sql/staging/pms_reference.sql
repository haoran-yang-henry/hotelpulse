-- Hotels and room types: small reference tables, refreshed from this run's snapshot.

INSERT INTO staging.pms_hotels AS t (
    hotel_id, hotel_code, hotel_name, city, country_code, timezone, total_rooms, pms_live_date,
    updated_at, _batch_id
)
SELECT DISTINCT ON (hotel_id)
    hotel_id,
    upper(trim(hotel_code)) AS hotel_code,
    trim(hotel_name) AS hotel_name,
    trim(city) AS city,
    upper(country_code) AS country_code,
    timezone,
    total_rooms,
    pms_live_date,
    updated_at,
    _batch_id
FROM raw.pms_hotels
WHERE _batch_id = '{{ run_id }}'
ORDER BY hotel_id ASC, updated_at DESC
ON CONFLICT (hotel_id) DO UPDATE SET
    hotel_code = excluded.hotel_code,
    hotel_name = excluded.hotel_name,
    city = excluded.city,
    country_code = excluded.country_code,
    timezone = excluded.timezone,
    total_rooms = excluded.total_rooms,
    pms_live_date = excluded.pms_live_date,
    updated_at = excluded.updated_at,
    _batch_id = excluded._batch_id,
    _loaded_at = now();

INSERT INTO staging.pms_room_types AS t (
    hotel_id, room_type_code, room_type_name, room_count, updated_at, _batch_id
)
SELECT DISTINCT ON (hotel_id, room_type_code)
    hotel_id,
    upper(trim(room_type_code)) AS room_type_code,
    trim(room_type_name) AS room_type_name,
    room_count,
    updated_at,
    _batch_id
FROM raw.pms_room_types
WHERE _batch_id = '{{ run_id }}'
ORDER BY hotel_id ASC, room_type_code ASC, updated_at DESC
ON CONFLICT (hotel_id, room_type_code) DO UPDATE SET
    room_type_name = excluded.room_type_name,
    room_count = excluded.room_count,
    updated_at = excluded.updated_at,
    _batch_id = excluded._batch_id,
    _loaded_at = now();
