from hotelpulse.insight.service import resolve_parameters
from hotelpulse.metabase import provision, specs

DASHBOARD = {
    "parameters": [
        {
            "id": "period",
            "slug": "period",
            "name": "Period",
            "type": "date/all-options",
            "default": "past12weeks",
        },
        {"id": "device", "slug": "device", "name": "Device", "type": "string/="},
    ]
}
DASHCARD = {
    "parameter_mappings": [
        {"parameter_id": "period", "target": ["dimension", ["template-tag", "period"]]},
        {"parameter_id": "device", "target": ["dimension", ["template-tag", "device"]]},
    ]
}


def test_display_values_from_the_link_become_query_parameters():
    params, described = resolve_parameters(
        DASHBOARD, DASHCARD, {"period": ["Previous 26 weeks"], "device": ["mobile and tablet"]}
    )
    assert [p["value"] for p in params] == ["past26weeks", ["mobile", "tablet"]]
    assert described == ["Period: Previous 26 weeks", "Device: mobile and tablet"]


def test_display_value_matching_an_inclusive_default_keeps_the_current_period():
    dashboard = {"parameters": [{**DASHBOARD["parameters"][0], "default": "past7days~"}]}
    params, _ = resolve_parameters(dashboard, DASHCARD, {"period": ["Previous 7 days"]})
    assert params[0]["value"] == "past7days~"
    params, _ = resolve_parameters(dashboard, DASHCARD, {"period": ["Previous 30 days"]})
    assert params[0]["value"] == "past30days"


def test_absent_filter_uses_default_and_cleared_filter_is_all():
    params, described = resolve_parameters(DASHBOARD, DASHCARD, {"device": ["{{device}}"]})
    assert params == [
        {
            "id": "period",
            "type": "date/all-options",
            "value": "past12weeks",
            "target": ["dimension", ["template-tag", "period"]],
        }
    ]
    assert described == ["Period: past12weeks", "Device: all"]
    params, _ = resolve_parameters(DASHBOARD, DASHCARD, {"period": ["{{period}}"]})
    assert params == []


def test_explain_bars_sit_above_every_chart_without_overlap():
    for spec in specs.load_dashboards():
        names = [c["name"] for c in specs.iter_cards(spec)]
        explainable = [c["name"] for c in specs.iter_cards(spec) if provision.has_explain_link(c)]
        cards = provision.dashcards(spec, {n: i for i, n in enumerate(names, 100)}, 7, "http://i")
        occupied = set()
        for dc in cards:
            cells = {
                (r, c)
                for r in range(dc["row"], dc["row"] + dc["size_y"])
                for c in range(dc["col"], dc["col"] + dc["size_x"])
            }
            assert not occupied & cells, f"overlap in {spec['name']}"
            occupied |= cells
        links = [
            dc
            for dc in cards
            if f"[{provision.EXPLAIN_LABEL}](" in dc["visualization_settings"].get("text", "")
        ]
        assert len(links) == len(explainable)
        for link in links:
            chart = next(
                dc
                for dc in cards
                if dc["card_id"] and dc["col"] == link["col"] and dc["row"] == link["row"] + 1
            )
            assert f"card={chart['card_id']}" in link["visualization_settings"]["text"]
            tags = {m["parameter_id"] for m in chart["parameter_mappings"]}
            assert {m["parameter_id"] for m in link["parameter_mappings"]} == tags


def test_explain_link_keeps_metabase_variables_inside_angle_brackets():
    link = provision.explain_link("http://localhost:8020", 3, 41, ["period", "device"])
    assert link == (
        "[✨ Explain this chart](<http://localhost:8020/explain?dashboard=3&card=41"
        "&period={{period}}&device={{device}}>)"
    )


def test_glossary_matches_chart_vocabulary():
    terms = specs.relevant_glossary("Payment success rate by device", "payment_success_rate")
    assert "payment" in terms and "occupancy" not in terms
