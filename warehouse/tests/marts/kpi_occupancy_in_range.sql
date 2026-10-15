-- severity: error
-- description: Occupancy is between 0 and 100 %.
SELECT
    hotel_id,
    stay_date,
    occupancy
FROM marts.hotel_daily_kpi
WHERE occupancy < 0 OR occupancy > 1
