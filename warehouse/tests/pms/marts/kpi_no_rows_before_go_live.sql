-- severity: error
-- description: KPIs are only reported from each hotel's PMS go-live date.
SELECT
    k.hotel_id,
    min(k.stay_date) AS first_reported_day,
    min(h.pms_live_date) AS pms_live_date
FROM marts.hotel_daily_kpi AS k
INNER JOIN core.dim_hotel AS h ON k.hotel_id = h.hotel_id
WHERE k.stay_date < h.pms_live_date
GROUP BY k.hotel_id
