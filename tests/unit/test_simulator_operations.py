from datetime import UTC, date, datetime, timedelta

from hotelpulse.simulator import anomalies, operations

ANCHOR = date(2026, 10, 16)
CATALOGUE = anomalies.load(ANCHOR)
A2, A3 = CATALOGUE["A2"], CATALOGUE["A3"]


def night(hotel: str, day: date, rooms: int = 150, total: int = 200) -> operations.Night:
    return operations.Night(hotel, day, rooms, breakfast_guests=2 * rooms, total_rooms=total)


def usage_rate(hotel: str, item: str, days: range) -> float:
    total = rooms = 0
    for offset in days:
        n = night(hotel, A2.start + timedelta(days=offset))
        records = {r["item_code"]: r for r in operations.consumption(n, A2)}
        total += records[item]["quantity"]
        rooms += n.rooms
    return total / rooms


def test_consumption_is_deterministic_and_complete():
    n = night("CITY", date(2026, 3, 1))
    first, second = operations.consumption(n, A2), operations.consumption(n, A2)
    assert first == second
    assert {r["item_code"] for r in first} == set(operations.ITEMS)
    assert all(r["quantity"] >= 0 and r["export_date"] == "2026-03-01" for r in first)


def test_consumption_follows_its_driver():
    n = night("CITY", date(2026, 3, 1), rooms=100)
    records = {r["item_code"]: r["quantity"] for r in operations.consumption(n, A2)}
    assert 150 <= records["towel_laundry"] <= 210  # 1.8 per room night +- noise
    assert 170 <= records["breakfast_cover"] <= 230  # 1 per breakfast guest (200)


def test_laundry_supplier_change_hits_only_resort_towels():
    before, after = range(-40, -5), range(0, 35)
    resort = usage_rate("RESORT", "towel_laundry", after) / usage_rate(
        "RESORT", "towel_laundry", before
    )
    city = usage_rate("CITY", "towel_laundry", after) / usage_rate("CITY", "towel_laundry", before)
    kits = usage_rate("RESORT", "toiletry_kit", after) / usage_rate(
        "RESORT", "toiletry_kit", before
    )
    assert 1.25 < resort < 1.45
    assert 0.95 < city < 1.05
    assert 0.95 < kits < 1.05


def stays(n: int, day: date, hotel: str = "CITY") -> list[tuple]:
    checkout = datetime.combine(day + timedelta(days=2), datetime.min.time(), UTC)
    return [(1_000_000 + i, f"HP{1_000_000 + i}", hotel, day, day + timedelta(days=2), checkout)
            for i in range(n)]  # fmt: skip


def breakfast_complaint_rate(occupied: int) -> float:
    day = date(2026, 7, 1)
    nights = {
        ("CITY", day + timedelta(days=i)): night("CITY", day + timedelta(days=i), occupied, 200)
        for i in range(2)
    }
    reviews = [r for s in stays(20_000, day) if (r := operations.review(s, nights, A3))]
    complaints = sum(
        {"topic": "breakfast", "sentiment": "negative"} in r["topics"] for r in reviews
    )
    return complaints / len(reviews)


def test_about_one_in_eight_stays_is_reviewed():
    day = date(2026, 7, 1)
    nights = {
        ("CITY", day): night("CITY", day),
        ("CITY", day + timedelta(days=1)): night("CITY", day),
    }
    reviews = [r for s in stays(5_000, day) if (r := operations.review(s, nights, A3))]
    assert 0.10 < len(reviews) / 5_000 < 0.14
    r = reviews[0]
    assert r["review_id"] == f"R{r['confirmation_code'][2:]}"
    assert 1 <= r["rating"] <= 10 and r["topics"]
    assert datetime.fromisoformat(r["posted_at"]) > datetime(2026, 7, 3, tzinfo=UTC)


def test_full_house_doubles_breakfast_complaints():
    quiet, full = breakfast_complaint_rate(140), breakfast_complaint_rate(190)  # 70 % vs 95 %
    assert quiet < 0.05
    assert full / quiet > 2


def test_export_time_is_the_following_night():
    assert operations.export_time(date(2026, 10, 15)) == datetime(2026, 10, 16, 1, tzinfo=UTC)
