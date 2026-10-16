-- Total consumables cost for the selected period (EUR)
SELECT round(sum(cost_eur), 0) AS consumables_cost
FROM marts.consumables_daily
WHERE {{hotel}} AND {{period}}
