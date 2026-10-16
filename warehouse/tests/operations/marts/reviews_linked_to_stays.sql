-- severity: warn
-- description: At least 95 % of the last 30 days' reviews are linked to a PMS stay.
SELECT
    count(*) AS reviews,
    count(reservation_id) AS linked
FROM marts.guest_reviews
WHERE posted_date >= (now() AT TIME ZONE 'Europe/Lisbon')::date - 30
HAVING count(reservation_id) < 0.95 * count(*)
