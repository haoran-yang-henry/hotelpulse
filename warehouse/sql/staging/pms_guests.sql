-- Guests: personal data ends here. E-mail becomes a salted SHA-256 key that still lets us
-- recognise returning guests; names are dropped. The salt is a bound parameter, so it never
-- appears in rendered SQL or logs.
MERGE INTO staging.pms_guests AS t
USING (
    SELECT DISTINCT ON (guest_id)
        guest_id,
        encode(
            sha256(convert_to(%(salt)s || coalesce(lower(trim(email)), guest_id::text), 'UTF8')), 'hex'  -- noqa: PRS, LT01
        ) AS guest_key,
        CASE WHEN country_code = 'CN' THEN 'CHN' ELSE upper(country_code) END AS country_code,
        created_at,
        updated_at,
        array_remove(
            ARRAY[
                CASE WHEN country_code IS NULL THEN 'missing_country' END,
                CASE WHEN length(country_code) <> 3 THEN 'non_iso3_country' END,
                CASE WHEN email IS NULL THEN 'missing_email' END
            ],
            NULL
        ) AS dq_issues,
        _batch_id
    FROM raw.pms_guests
    WHERE _batch_id = '{{ run_id }}'
    ORDER BY guest_id ASC, updated_at DESC
) AS s
    ON t.guest_id = s.guest_id
WHEN MATCHED AND (s.updated_at > t.updated_at{% if params.full_refresh %} OR TRUE{% endif %}) THEN
    UPDATE SET
        guest_key = s.guest_key,
        country_code = s.country_code,
        created_at = s.created_at,
        updated_at = s.updated_at,
        dq_issues = s.dq_issues,
        _batch_id = s._batch_id,
        _loaded_at = now()
WHEN NOT MATCHED THEN
    INSERT (guest_id, guest_key, country_code, created_at, updated_at, dq_issues, _batch_id)
    VALUES (s.guest_id, s.guest_key, s.country_code, s.created_at, s.updated_at, s.dq_issues, s._batch_id);
