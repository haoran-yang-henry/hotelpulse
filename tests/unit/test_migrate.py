import pytest

from hotelpulse import migrate
from hotelpulse.migrate import MigrationError, discover, pending


def write(tmp_path, name, body="SELECT 1;"):
    (tmp_path / name).write_text(body)


def test_discover_orders_by_version(tmp_path):
    write(tmp_path, "V002__second.sql")
    write(tmp_path, "V001__first.sql")
    assert [m.version for m in discover(tmp_path)] == [1, 2]


def test_invalid_filename_is_rejected(tmp_path):
    write(tmp_path, "001_first.sql")
    with pytest.raises(MigrationError, match="Invalid migration filename"):
        discover(tmp_path)


def test_pending_skips_applied(tmp_path):
    write(tmp_path, "V001__first.sql")
    write(tmp_path, "V002__second.sql")
    first, second = discover(tmp_path)
    assert pending([first, second], {1: first.checksum}) == [second]


def test_modified_applied_migration_fails(tmp_path):
    write(tmp_path, "V001__first.sql")
    (m,) = discover(tmp_path)
    with pytest.raises(MigrationError, match="modified after being applied"):
        pending([m], {1: "not-the-checksum"})


def test_repository_migrations_are_well_formed():
    migrations = discover(migrate.settings.WAREHOUSE_DIR / "migrations")
    assert [m.version for m in migrations] == list(range(1, len(migrations) + 1))
