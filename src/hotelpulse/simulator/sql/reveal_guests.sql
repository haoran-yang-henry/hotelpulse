-- Reveal guest profiles created up to %(as_of)s. Idempotent.
INSERT INTO public.guests (guest_id, first_name, last_name, email, country_code, created_at, updated_at)
SELECT
    guest_id,
    first_name,
    last_name,
    email,
    country_code,
    created_at,
    created_at AS updated_at
FROM sim.guest_plan
WHERE created_at <= %(as_of)s
ON CONFLICT (guest_id) DO NOTHING
