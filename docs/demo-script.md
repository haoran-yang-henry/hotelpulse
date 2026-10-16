# Demo script (about 8 minutes)

A walkthrough for a live demo or a screen recording. The story is the hotel group's Monday
operations review: start with the business question, show how the platform answers it, and
only then show how it is built.

**Before the demo**

- `make up` (or `make e2e-clean` for a fresh, fully tested stack); `make evaluate` once, so
  explanations are cached and appear instantly.
- Open tabs: Metabase (http://localhost:3001), Airflow (http://localhost:8081), the demo website
  (http://localhost:8030), the repository.
- Dashboard filters on their defaults: *Previous 26 weeks*, all hotels.

---

## 1. The problem (30 s)

> "Two hotels, a city hotel in Lisbon and a resort in the Algarve. Bookings live in the PMS,
> website behaviour in a tracker, consumables in the inventory system and reviews on
> Booking.com and Google. The managers have one hour on Monday morning. HotelPulse brings
> these sources together into four dashboards, and every chart can explain itself."

Show the README's business-problem table.

## 2. Revenue: something happened to direct bookings (1 min)

*Revenue & Distribution* dashboard (home page).

- KPIs against the 80 % occupancy target, year-over-year trends, channel mix.
- **Direct share of new bookings**: the dip at the end of September.
- Click **Explain this chart**: the facts engine finds the episode and its dates, and the model
  turns them into a headline, hypotheses and next steps. Point out the *Facts used* list and
  the "all numbers verified" badge.

> "The model never computes anything. It only phrases facts the engine computed, and every
> number it writes is checked against those facts."

## 3. Website: why it happened (1.5 min)

*Website & Booking Funnel* dashboard.

- **Payment success rate by device**: only mobile collapses → a checkout bug, not demand.
- **Failed payments by error code**: `gateway_timeout` → a payment-provider problem.
- **Tracking coverage**: below the 60 % threshold since the cookie-banner redesign. Web numbers
  are lower bounds, and coverage is measured against the PMS, not guessed.
- Optional live booking: book a room on the demo website with card `4000 0000 0000 0002`
  (declined), then `make trigger DAG=pms_ingest` and `make trigger DAG=web_events_ingest`,
  and find the visit in the funnel.

> "Revenue showed the *what*. The website data shows the *why*: guests who could not pay on
> mobile booked the same stay on Booking.com, at 17 % commission."

## 4. Operations and guest experience (1.5 min)

*Operations & Guest Experience* dashboard.

- **Usage per room night by item**: usage is normalised by rooms sold from the PMS, so a busy
  summer does not look like waste. Select *HotelPulse Resort Algarve*: towels laundered per
  room night jump in September (a new laundry supplier). Explain it: the level shift with
  before and after values.
- **Purchase suggestion**: a transparent rule (recent usage × rooms on the books × buffer).
  The *Change* column flags the resort towels before the next order is placed.
- **Breakfast complaints by occupancy during the stay**: reviews are linked to the stay by
  confirmation code. At 90 %+ occupancy, breakfast complaints more than double → staff
  breakfast from the occupancy forecast.

## 5. Can we trust it? (1.5 min)

*Data Platform Health* dashboard.

- Freshness against SLAs, DAG success rates and durations, rows loaded, data-quality trends.
- Trigger `ops_alert_drill` in Airflow → an error alert appears (and in Slack, if a webhook is
  configured).

Airflow:

- `pms_ingest` graph: extract (mapped per table) → stage → core → quality gates. Assets
  trigger `marts_build`.
- Backfills are safe: loads are idempotent per batch, and the e2e suite proves it.

## 6. How it is built (1.5 min)

Repository:

- `warehouse/migrations` (checksum-verified), `warehouse/sql` per layer, `warehouse/tests`:
  data-quality checks that return violating rows.
- `bi/metabase/dashboards/*.yaml`: dashboards as code, including each chart's *intent* for the
  explanation.
- `src/hotelpulse/insight/facts.py`: anomaly episodes in units of the series' own noise,
  level shifts that must beat a trend, and targets compared in code.
- `docs/insight-evaluation.md`: the explanations are scored against injected anomalies
  (ground truth), with control charts for false alarms.
- Quality: `make lint test test-dags e2e`.

## 7. Close (30 s)

> "The same pattern scales to more hotels: sources land as files or change logs, Airflow
> orchestrates idempotent loads, quality is code, dashboards are code, and the explanation
> layer turns charts into decisions."

Hand over to the business memo (`docs/business-memo.md`) for the numbers.
