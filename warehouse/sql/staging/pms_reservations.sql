-- Reservations: newest version per reservation from this batch, typed and cleaned.
-- Source quirks are not silently dropped - they are recorded in dq_issues.
MERGE INTO staging.pms_reservations AS t
USING (
    SELECT DISTINCT ON (r.reservation_id)
        r.reservation_id,
        r.confirmation_code,
        r.hotel_id,
        r.guest_id,
        coalesce(r.booking_source, 'unknown') AS channel_code,
        nullif(r.market_segment, 'Undefined') AS market_segment,
        nullif(r.distribution_channel, 'Undefined') AS distribution_channel,
        r.reserved_room_type,
        r.assigned_room_type,
        r.arrival_date,
        r.departure_date,
        r.departure_date - r.arrival_date AS nights,
        (r.created_at AT TIME ZONE h.timezone)::date AS booked_date,
        r.arrival_date - (r.created_at AT TIME ZONE h.timezone)::date AS lead_time_days,
        coalesce(r.adults, 0) AS adults,
        coalesce(r.children, 0) AS children,
        coalesce(r.babies, 0) AS babies,
        CASE r.meal_plan
            WHEN 'BB' THEN 'bed_and_breakfast'
            WHEN 'HB' THEN 'half_board'
            WHEN 'FB' THEN 'full_board'
            ELSE 'room_only'  -- 'SC' (self catering) and 'Undefined' both mean no meal package
        END AS meal_plan,
        r.adr AS adr_source,
        CASE WHEN r.adr < 0 OR r.adr > 1000 THEN NULL ELSE r.adr END AS adr,
        r.deposit_type,
        r.customer_type,
        coalesce(r.is_repeated_guest, FALSE) AS is_repeated_guest,
        coalesce(r.special_requests, 0) AS special_requests,
        coalesce(r.parking_spaces, 0) AS parking_spaces,
        r.status,
        r.created_at,
        r.checked_in_at,
        r.checked_out_at,
        r.canceled_at,
        r.updated_at,
        array_remove(
            ARRAY[
                CASE WHEN r.booking_source IS NULL THEN 'unknown_channel' END,
                CASE WHEN r.adr < 0 THEN 'negative_adr' END,
                CASE WHEN r.adr > 1000 THEN 'adr_outlier' END,
                CASE
                    WHEN coalesce(r.adults, 0) + coalesce(r.children, 0) + coalesce(r.babies, 0) = 0
                        THEN 'zero_guests'
                END,
                CASE WHEN r.children IS NULL THEN 'missing_children' END,
                CASE WHEN r.meal_plan = 'Undefined' THEN 'undefined_meal_plan' END,
                CASE WHEN r.market_segment = 'Undefined' THEN 'undefined_segment' END
            ],
            NULL
        ) AS dq_issues,
        r._batch_id
    FROM raw.pms_reservations AS r
    INNER JOIN staging.pms_hotels AS h ON r.hotel_id = h.hotel_id
    WHERE r._batch_id = '{{ run_id }}'
    ORDER BY r.reservation_id ASC, r.updated_at DESC
) AS s
    ON t.reservation_id = s.reservation_id
WHEN MATCHED AND (s.updated_at > t.updated_at{% if params.full_refresh %} OR TRUE{% endif %}) THEN
    UPDATE SET
        confirmation_code = s.confirmation_code,
        hotel_id = s.hotel_id,
        guest_id = s.guest_id,
        channel_code = s.channel_code,
        market_segment = s.market_segment,
        distribution_channel = s.distribution_channel,
        reserved_room_type = s.reserved_room_type,
        assigned_room_type = s.assigned_room_type,
        arrival_date = s.arrival_date,
        departure_date = s.departure_date,
        nights = s.nights,
        booked_date = s.booked_date,
        lead_time_days = s.lead_time_days,
        adults = s.adults,
        children = s.children,
        babies = s.babies,
        meal_plan = s.meal_plan,
        adr_source = s.adr_source,
        adr = s.adr,
        deposit_type = s.deposit_type,
        customer_type = s.customer_type,
        is_repeated_guest = s.is_repeated_guest,
        special_requests = s.special_requests,
        parking_spaces = s.parking_spaces,
        status = s.status,
        created_at = s.created_at,
        checked_in_at = s.checked_in_at,
        checked_out_at = s.checked_out_at,
        canceled_at = s.canceled_at,
        updated_at = s.updated_at,
        dq_issues = s.dq_issues,
        _batch_id = s._batch_id,
        _loaded_at = now()
WHEN NOT MATCHED THEN
    INSERT (
        reservation_id, confirmation_code, hotel_id, guest_id, channel_code, market_segment,
        distribution_channel, reserved_room_type, assigned_room_type, arrival_date, departure_date,
        nights, booked_date, lead_time_days, adults, children, babies, meal_plan, adr_source, adr,
        deposit_type, customer_type, is_repeated_guest, special_requests, parking_spaces, status,
        created_at, checked_in_at, checked_out_at, canceled_at, updated_at, dq_issues, _batch_id
    )
    VALUES (
        s.reservation_id, s.confirmation_code, s.hotel_id, s.guest_id, s.channel_code, s.market_segment,
        s.distribution_channel, s.reserved_room_type, s.assigned_room_type, s.arrival_date,
        s.departure_date, s.nights, s.booked_date, s.lead_time_days, s.adults, s.children, s.babies,
        s.meal_plan, s.adr_source, s.adr, s.deposit_type, s.customer_type, s.is_repeated_guest,
        s.special_requests, s.parking_spaces, s.status, s.created_at, s.checked_in_at,
        s.checked_out_at, s.canceled_at, s.updated_at, s.dq_issues, s._batch_id
    );
