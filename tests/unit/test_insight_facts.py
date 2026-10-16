from datetime import date, timedelta

from hotelpulse.insight import facts

START = date(2026, 6, 1)  # a Monday


def weekly_result(series: dict[str, list[float]], percent: set[str] = frozenset()):
    names = list(series)
    n = len(next(iter(series.values())))
    cols = [{"name": "week", "display_name": "Week", "base_type": "type/Date"}] + [
        {"name": s, "display_name": s, "base_type": "type/Decimal"} for s in names
    ]
    rows = [
        [(START + timedelta(weeks=i)).isoformat()] + [series[s][i] for s in names] for i in range(n)
    ]
    card = {
        "name": "Test chart",
        "display": "line",
        "visualization_settings": {
            "graph.dimensions": ["week"],
            "graph.metrics": names,
            "column_settings": {f'["name","{s}"]': {"number_style": "percent"} for s in percent},
        },
    }
    return card, {"data": {"cols": cols, "rows": rows}}


NOISE = [0.0, 0.01, -0.012, 0.008, -0.005, 0.011, -0.009, 0.004, -0.01, 0.006, -0.003, 0.009]


def kinds(sheet):
    return [f.kind for f in sheet.facts]


def test_short_dip_is_an_anomaly_episode_with_divergence():
    mobile = [0.85 + n for n in NOISE]
    mobile[7], mobile[8] = 0.24, 0.35
    desktop = [0.88 + n for n in reversed(NOISE)]
    card, result = weekly_result({"mobile": mobile, "desktop": desktop}, {"mobile", "desktop"})
    sheet = facts.extract(card, result)
    anomaly = next(f for f in sheet.facts if f.kind == "anomaly")
    assert anomaly.meta["series"] == "mobile" and anomaly.meta["direction"] == "low"
    assert anomaly.meta["start"] == (START + timedelta(weeks=7)).isoformat()
    assert anomaly.meta["end"] == (START + timedelta(weeks=8)).isoformat()
    assert "divergence" in kinds(sheet)
    assert sheet.facts[0].kind in ("anomaly", "divergence")  # ranked first


def test_noise_and_seasonal_trend_are_not_anomalies():
    trend = [0.70 + 0.015 * i + n for i, n in enumerate(NOISE)]
    card, result = weekly_result({"occupancy": trend}, {"occupancy"})
    sheet = facts.extract(card, result)
    assert not {"anomaly", "level_shift"} & set(kinds(sheet))
    assert "trend" in kinds(sheet)


def test_step_change_is_a_level_shift():
    values = [0.76 + n for n in NOISE[:5]] + [0.54 + n for n in NOISE[5:]]
    card, result = weekly_result({"coverage": values}, {"coverage"})
    shift = next(f for f in facts.extract(card, result).facts if f.kind == "level_shift")
    assert shift.meta["start"] == (START + timedelta(weeks=5)).isoformat()
    assert shift.meta["direction"] == "low"


def test_percent_facts_record_display_numbers():
    card, result = weekly_result({"rate": [0.5 + n for n in NOISE]}, {"rate"})
    sheet = facts.extract(card, result)
    latest = next(f for f in sheet.facts if f.kind == "latest")
    assert "%" in latest.text and any(n.unit == "pp" for n in latest.numbers)
    assert all(0 <= n.value <= 100 for n in latest.numbers if n.unit == "%")


def test_breakdown_share_shift_for_additive_counts():
    weeks = 10
    cols = [
        {"name": "week", "base_type": "type/Date"},
        {"name": "error_code", "base_type": "type/Text"},
        {"name": "failures", "base_type": "type/BigInteger"},
    ]
    rows = []
    for i in range(weeks):
        day = (START + timedelta(weeks=i)).isoformat()
        rows.append([day, "card_declined", 3 + i % 2])
        if i == 6:
            rows.append([day, "gateway_timeout", 30])
    card = {
        "name": "Failed payments",
        "display": "bar",
        "visualization_settings": {
            "graph.dimensions": ["week", "error_code"],
            "graph.metrics": ["failures"],
        },
    }
    sheet = facts.extract(card, {"data": {"cols": cols, "rows": rows}})
    shift = next(f for f in sheet.facts if f.kind == "share_shift")
    assert shift.meta["series"] == "gateway_timeout"
    gateway = [
        f for f in sheet.facts if f.kind == "anomaly" and f.meta["series"] == "gateway_timeout"
    ]
    assert gateway, "missing weeks are filled with zeros, so the spike is detected"


def test_scalar_with_target_and_funnel():
    card = {
        "name": "Occupancy",
        "display": "scalar",
        "visualization_settings": {
            "column_settings": {'["name","occupancy"]': {"number_style": "percent"}}
        },
    }
    result = {
        "data": {"cols": [{"name": "occupancy", "base_type": "type/Decimal"}], "rows": [[0.723]]}
    }
    sheet = facts.extract(card, result, {"target": {"value": 0.8, "label": "group target"}})
    assert "72.3%" in sheet.facts[0].text
    assert any("below the group target" in f.text for f in sheet.facts)

    card = {
        "name": "Funnel",
        "display": "funnel",
        "visualization_settings": {"funnel.dimension": "step", "funnel.metric": "visits"},
    }
    cols = [
        {"name": "step", "base_type": "type/Text"},
        {"name": "visits", "base_type": "type/Integer"},
    ]
    rows = [["Visit", 1000], ["Search", 400], ["Room", 150], ["Pay", 40], ["Booked", 30]]
    sheet = facts.extract(card, {"data": {"cols": cols, "rows": rows}})
    drop = next(f for f in sheet.facts if "largest drop-off" in f.text)
    assert "'Room' and 'Pay'" in drop.text


def test_no_rows():
    card, result = weekly_result({"x": [1.0]})
    result["data"]["rows"] = []
    assert facts.extract(card, result).facts[0].text.startswith("No data")
