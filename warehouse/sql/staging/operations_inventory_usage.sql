-- Consumables usage of this batch's export files. A day can be re-exported (corrections):
-- the most recent file wins, within the batch and against what is already staged.
INSERT INTO staging.inventory_usage (
    usage_date, hotel_code, item_code, item_name, unit, quantity, unit_cost_eur, _file,
    _batch_id
)
SELECT DISTINCT ON (u.usage_date, u.hotel_code, u.item_code)
    u.usage_date,
    u.hotel_code,
    u.item_code,
    u.item_name,
    u.unit,
    u.quantity,
    u.unit_cost_eur,
    u._file,
    u._batch_id
FROM (
    SELECT
        (r.payload ->> 'export_date')::date AS usage_date,
        r.payload ->> 'hotel_code' AS hotel_code,
        r.payload ->> 'item_code' AS item_code,
        r.payload ->> 'item_name' AS item_name,
        r.payload ->> 'unit' AS unit,
        (r.payload ->> 'quantity')::int AS quantity,
        (r.payload ->> 'unit_cost_eur')::numeric(8, 2) AS unit_cost_eur,
        r._file,
        r._line,
        r._batch_id
    FROM raw.inventory_usage AS r
    WHERE r._batch_id = '{{ run_id }}'
) AS u
ORDER BY u.usage_date ASC, u.hotel_code ASC, u.item_code ASC, u._file DESC, u._line DESC
ON CONFLICT (usage_date, hotel_code, item_code) DO UPDATE SET
    item_name = excluded.item_name,
    unit = excluded.unit,
    quantity = excluded.quantity,
    unit_cost_eur = excluded.unit_cost_eur,
    _file = excluded._file,
    _batch_id = excluded._batch_id,
    _loaded_at = now()
WHERE excluded._file >= staging.inventory_usage._file;
