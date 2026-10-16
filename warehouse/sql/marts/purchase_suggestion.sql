-- Suggested order for the next 14 nights (rule-based, ADR-0019):
--   median usage per driver unit of the last 28 days
--   x driver units on the books for the next 14 nights (rooms; breakfast guests estimated
--     from rooms with the last 28 days' breakfast guests per room)
--   x the item's safety factor.
-- The previous 28 days' median is kept next to it, so a changed usage rate is visible.

DELETE FROM marts.purchase_suggestion;

INSERT INTO marts.purchase_suggestion (
    hotel_id, hotel_name, item_code, item_name, unit, usage_per_driver, usage_per_driver_prev,
    forecast_driver_units, suggested_quantity, estimated_cost_eur
)
WITH latest AS (
    SELECT
        hotel_id,
        max(usage_date) AS last_day
    FROM marts.consumables_daily
    GROUP BY hotel_id
),

rates AS (
    SELECT
        d.hotel_id,
        d.hotel_name,
        d.item_code,
        d.item_name,
        d.unit,
        d.usage_driver,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY d.quantity::numeric / d.driver_units)
        FILTER (WHERE d.usage_date > l.last_day - 28) AS usage_per_driver,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY d.quantity::numeric / d.driver_units)
        FILTER (WHERE d.usage_date <= l.last_day - 28) AS usage_per_driver_prev,
        sum(d.breakfast_guests) FILTER (WHERE d.usage_date > l.last_day - 28)::numeric
        / nullif(sum(d.rooms_sold) FILTER (WHERE d.usage_date > l.last_day - 28), 0)
            AS breakfast_guests_per_room,
        (array_agg(d.unit_cost_eur ORDER BY d.usage_date DESC))[1] AS unit_cost_eur
    FROM marts.consumables_daily AS d
    INNER JOIN latest AS l ON d.hotel_id = l.hotel_id
    WHERE d.usage_date > l.last_day - 56 AND d.driver_units > 0
    GROUP BY d.hotel_id, d.hotel_name, d.item_code, d.item_name, d.unit, d.usage_driver
),

otb AS (
    SELECT
        hotel_id,
        sum(otb_rooms) AS rooms
    FROM marts.booking_pace
    WHERE days_out BETWEEN 0 AND 13
    GROUP BY hotel_id
),

forecast AS (
    SELECT
        r.*,
        CASE
            WHEN r.usage_driver = 'breakfast_guest'
                THEN round(o.rooms * coalesce(r.breakfast_guests_per_room, 0))
            ELSE o.rooms
        END::int AS driver_units
    FROM rates AS r
    INNER JOIN otb AS o ON r.hotel_id = o.hotel_id
)

SELECT
    f.hotel_id,
    f.hotel_name,
    f.item_code,
    f.item_name,
    f.unit,
    round(f.usage_per_driver::numeric, 3) AS usage_per_driver,
    round(f.usage_per_driver_prev::numeric, 3) AS usage_per_driver_prev,
    f.driver_units AS forecast_driver_units,
    ceil(f.usage_per_driver::numeric * f.driver_units * c.safety_factor)::int AS suggested_quantity,
    round(ceil(f.usage_per_driver::numeric * f.driver_units * c.safety_factor) * f.unit_cost_eur, 2)
        AS estimated_cost_eur
FROM forecast AS f
INNER JOIN core.dim_consumable AS c ON f.item_code = c.item_code;
