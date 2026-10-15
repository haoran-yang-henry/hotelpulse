-- Sold room nights, revenue and commission per hotel, stay date and channel.

DELETE FROM marts.channel_daily;

INSERT INTO marts.channel_daily (
    hotel_id, hotel_name, stay_date, channel_code, channel_name, channel_group, is_direct,
    rooms_sold, room_revenue, commission_cost
)
SELECT
    rn.hotel_id,
    h.hotel_name,
    rn.stay_date,
    c.channel_code,
    c.channel_name,
    c.channel_group,
    c.is_direct,
    count(*) AS rooms_sold,
    sum(rn.room_revenue) AS room_revenue,
    sum(rn.commission_cost) AS commission_cost
FROM core.fct_room_night AS rn
INNER JOIN core.dim_hotel AS h ON rn.hotel_id = h.hotel_id
INNER JOIN core.dim_channel AS c ON rn.channel_code = c.channel_code
WHERE
    rn.is_sold
    AND rn.stay_date >= h.pms_live_date
GROUP BY rn.hotel_id, h.hotel_name, rn.stay_date, c.channel_code, c.channel_name, c.channel_group, c.is_direct;
