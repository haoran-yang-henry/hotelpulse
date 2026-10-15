-- severity: error
-- description: Core holds exactly the reservations present in staging.
SELECT
    (SELECT count(*) FROM staging.pms_reservations) AS staging_rows,
    (SELECT count(*) FROM core.fct_reservation) AS core_rows
WHERE (SELECT count(*) FROM staging.pms_reservations) <> (SELECT count(*) FROM core.fct_reservation)
