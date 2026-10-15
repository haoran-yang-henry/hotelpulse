-- severity: error
-- description: guest_key must be a SHA-256 hex digest - never a plain e-mail address.
SELECT guest_id
FROM staging.pms_guests
WHERE guest_key !~ '^[0-9a-f]{64}$'
