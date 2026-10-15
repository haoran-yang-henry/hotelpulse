-- severity: warn
-- description: Guest country is missing or not an ISO 3166-1 alpha-3 code.
SELECT
    guest_id,
    country_code,
    dq_issues
FROM staging.pms_guests
WHERE dq_issues && ARRAY['missing_country', 'non_iso3_country']
