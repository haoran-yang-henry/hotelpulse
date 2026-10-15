import pytest

from hotelpulse import quality
from hotelpulse.quality import Check, Result, parse_check


def test_parse_check_reads_header(tmp_path):
    path = tmp_path / "my_check.sql"
    path.write_text("-- severity: warn\n-- description: Something.\nSELECT 1 WHERE false;\n")
    check = parse_check(path, "staging")
    assert check.name == "staging.my_check"
    assert check.severity == "warn"
    assert check.query == "-- severity: warn\n-- description: Something.\nSELECT 1 WHERE false"


@pytest.mark.parametrize(
    "header", ["-- description: no severity\n", "-- severity: fatal\n-- description: x\n"]
)
def test_parse_check_rejects_bad_header(tmp_path, header):
    path = tmp_path / "bad.sql"
    path.write_text(header + "SELECT 1\n")
    with pytest.raises(ValueError):
        parse_check(path, "core")


@pytest.mark.parametrize("layer", ["staging", "core", "marts"])
def test_repository_checks_parse(layer):
    assert quality.discover(layer)


def _result(severity, failing):
    return Result(Check("x.y", "x", severity, "d", "SELECT 1"), failing, [])


def test_status_and_enforce():
    assert _result("error", 0).status == "pass"
    assert _result("warn", 3).status == "warn"
    quality.enforce([_result("warn", 3), _result("error", 0)])
    with pytest.raises(quality.DataQualityError, match=r"x\.y"):
        quality.enforce([_result("error", 1)])
