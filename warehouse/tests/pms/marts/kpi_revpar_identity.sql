-- severity: error
-- description: RevPAR equals occupancy x ADR (within rounding).
SELECT
    hotel_id,
    stay_date,
    occupancy,
    adr,
    revpar
FROM marts.hotel_daily_kpi
WHERE adr IS NOT NULL AND abs(revpar - occupancy * adr) > 0.05
