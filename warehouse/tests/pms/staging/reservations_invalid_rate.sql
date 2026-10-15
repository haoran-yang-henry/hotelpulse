-- severity: warn
-- description: Nightly rate is negative or implausibly high (> 1000 EUR); excluded from revenue.
SELECT
    reservation_id,
    adr_source,
    dq_issues
FROM staging.pms_reservations
WHERE dq_issues && ARRAY['negative_adr', 'adr_outlier']
