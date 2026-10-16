-- Consumables per hotel, day and item next to the occupancy that drove them, from each
-- hotel's PMS go-live (usage per room night is only meaningful with complete PMS data).

DELETE FROM marts.consumables_daily;

INSERT INTO marts.consumables_daily (
    usage_date, hotel_id, hotel_name, item_code, item_name, unit, usage_driver, quantity,
    unit_cost_eur, cost_eur, rooms_sold, breakfast_guests, driver_units
)
WITH breakfast AS (
    SELECT
        rn.hotel_id,
        rn.stay_date,
        sum(r.guests) AS breakfast_guests
    FROM core.fct_room_night AS rn
    INNER JOIN core.fct_reservation AS r ON rn.reservation_id = r.reservation_id
    WHERE rn.is_sold AND r.meal_plan IN ('bed_and_breakfast', 'half_board', 'full_board')
    GROUP BY rn.hotel_id, rn.stay_date
)

SELECT
    u.usage_date,
    h.hotel_id,
    h.hotel_name,
    u.item_code,
    c.item_name,
    c.unit,
    c.usage_driver,
    u.quantity,
    u.unit_cost_eur,
    round(u.quantity * u.unit_cost_eur, 2) AS cost_eur,
    k.rooms_sold,
    coalesce(b.breakfast_guests, 0) AS breakfast_guests,
    CASE
        WHEN c.usage_driver = 'breakfast_guest' THEN coalesce(b.breakfast_guests, 0)
        ELSE k.rooms_sold
    END AS driver_units
FROM staging.inventory_usage AS u
INNER JOIN core.dim_hotel AS h ON u.hotel_code = h.hotel_code
INNER JOIN core.dim_consumable AS c ON u.item_code = c.item_code
INNER JOIN marts.hotel_daily_kpi AS k ON h.hotel_id = k.hotel_id AND u.usage_date = k.stay_date
LEFT JOIN breakfast AS b ON h.hotel_id = b.hotel_id AND u.usage_date = b.stay_date
WHERE u.usage_date >= h.pms_live_date AND NOT k.is_future;
