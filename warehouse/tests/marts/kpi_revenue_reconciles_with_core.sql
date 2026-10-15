-- severity: error
-- description: Room revenue in the KPI mart equals sold room-night revenue in core (from go-live).
WITH totals AS (
    SELECT
        (SELECT sum(room_revenue) FROM marts.hotel_daily_kpi) AS mart_revenue,
        (
            SELECT sum(rn.room_revenue)
            FROM core.fct_room_night AS rn
            INNER JOIN core.dim_hotel AS h ON rn.hotel_id = h.hotel_id
            WHERE rn.is_sold AND rn.stay_date >= h.pms_live_date
        ) AS core_revenue
)

SELECT
    mart_revenue,
    core_revenue
FROM totals
WHERE abs(coalesce(mart_revenue, 0) - coalesce(core_revenue, 0)) > 0.01
