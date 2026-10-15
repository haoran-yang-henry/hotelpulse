-- Reveal the state of every reservation as of %(as_of)s: new bookings appear, and
-- check-ins, check-outs, cancellations and no-shows are applied once their time has come.
-- Only rows whose state moved forward are written: re-running is a no-op and revealing an
-- earlier point in time can never roll a reservation back.
INSERT INTO public.reservations AS r (
    reservation_id, confirmation_code, hotel_id, guest_id, booking_source, market_segment,
    distribution_channel, reserved_room_type, assigned_room_type, arrival_date, departure_date,
    adults, children, babies, meal_plan, adr, deposit_type, customer_type, is_repeated_guest,
    previous_cancellations, previous_bookings_not_canceled, booking_changes, days_in_waiting_list,
    agent_id, company_id, parking_spaces, special_requests, status, created_at, checked_in_at,
    checked_out_at, canceled_at, updated_at
)
SELECT
    p.reservation_id,
    p.confirmation_code,
    p.hotel_id,
    p.guest_id,
    p.booking_source,
    p.market_segment,
    p.distribution_channel,
    p.reserved_room_type,
    CASE WHEN p.checked_in_at <= %(as_of)s THEN p.assigned_room_type END,
    p.arrival_date,
    p.departure_date,
    p.adults,
    p.children,
    p.babies,
    p.meal_plan,
    p.adr,
    p.deposit_type,
    p.customer_type,
    p.is_repeated_guest,
    p.previous_cancellations,
    p.previous_bookings_not_canceled,
    p.booking_changes,
    p.days_in_waiting_list,
    p.agent_id,
    p.company_id,
    p.parking_spaces,
    p.special_requests,
    CASE
        WHEN p.canceled_at <= %(as_of)s THEN 'canceled'
        WHEN p.no_show_at <= %(as_of)s THEN 'no_show'
        WHEN p.checked_out_at <= %(as_of)s THEN 'checked_out'
        WHEN p.checked_in_at <= %(as_of)s THEN 'checked_in'
        ELSE 'confirmed'
    END,
    p.created_at,
    CASE WHEN p.checked_in_at <= %(as_of)s THEN p.checked_in_at END,
    CASE WHEN p.checked_out_at <= %(as_of)s THEN p.checked_out_at END,
    CASE WHEN p.canceled_at <= %(as_of)s THEN p.canceled_at END,
    greatest(
        p.created_at,
        CASE WHEN p.checked_in_at <= %(as_of)s THEN p.checked_in_at END,
        CASE WHEN p.checked_out_at <= %(as_of)s THEN p.checked_out_at END,
        CASE WHEN p.canceled_at <= %(as_of)s THEN p.canceled_at END,
        CASE WHEN p.no_show_at <= %(as_of)s THEN p.no_show_at END
    )
FROM sim.reservation_plan AS p
WHERE p.created_at <= %(as_of)s
ON CONFLICT (reservation_id) DO UPDATE SET
    assigned_room_type = excluded.assigned_room_type,
    status = excluded.status,
    checked_in_at = excluded.checked_in_at,
    checked_out_at = excluded.checked_out_at,
    canceled_at = excluded.canceled_at,
    updated_at = excluded.updated_at
WHERE r.updated_at < excluded.updated_at
