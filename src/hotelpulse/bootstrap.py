"""One-shot initialisation, run by the `bootstrap` container on every `make up`.

1. Apply pending warehouse migrations.
2. Seed the simulated PMS once (download dataset, build timeline) and reveal up to now.
3. Seed the website-tracking history once (landing-zone files since tracking go-live).

Both steps are idempotent.
"""

import logging
from datetime import UTC, date, datetime

import psycopg

from hotelpulse import migrate, settings
from hotelpulse.simulator import pms, web

log = logging.getLogger("hotelpulse.bootstrap")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    migrate.run(settings.dwh_dsn())
    with psycopg.connect(settings.pms_admin_dsn()) as conn:
        pms.seed(conn, settings.sim_anchor_date() or date.today(), settings.DATA_DIR)
        pms.reveal(conn, datetime.now(UTC))
        web.seed_history(conn, settings.landing_dir(), datetime.now(UTC))
    log.info("Bootstrap complete")


if __name__ == "__main__":
    main()
