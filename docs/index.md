---
layout: page
title: HotelPulse
---

**An end-to-end data platform for hotel operations.** Bookings from the property management
system (PMS), website tracking events, consumables and guest reviews flow through an
Airflow-orchestrated PostgreSQL warehouse into Metabase dashboards - and every chart has a
button that explains what it shows in plain language.

## Start here: the business memo

[**Monday review memo: four findings and what they are worth →**](business-memo.md)

| Finding | Estimated impact |
|---|---|
| A mobile payment outage pushed direct bookers to Booking.com | ≈ €3.5k extra commission in two weeks; ≈ €90k a year had it gone unnoticed |
| After a cookie-banner redesign, web analytics sees only half of the bookings | web KPIs understated by ≈ 28 % |
| The resort's new laundry supplier: +32 % towels per room night | ≈ €25k a year |
| Breakfast complaints are 2.8× as frequent when the hotel is 90 %+ full | 189 nights a year; extra staff ≈ €11k a year |

The data is a public hotel booking dataset replayed as a live PMS; the four problems were
injected as ground truth, so the memo also shows that the platform finds them.

## Dashboards

![Revenue & Distribution dashboard](images/revenue-dashboard.png)

*Revenue & Distribution: occupancy, ADR and RevPAR against last year, channel mix and
commission, and the booking pace for the next four months.*

![Website & Booking Funnel dashboard](images/website-dashboard.png)

*Website & Booking Funnel: the closed booking funnel, payment success by device, error codes,
first- vs. last-touch attribution and tracking coverage reconciled against the PMS.*

![Operations & Guest Experience dashboard](images/operations-dashboard.png)

*Operations & Guest Experience: consumables per occupied room night, a transparent 14-day
purchase suggestion, and reviews linked to the guest's stay.*

![Data Platform Health dashboard](images/health-dashboard.png)

*Data Platform Health: freshness against SLAs, pipeline runs, data-quality trends and alerts.*

## Explain this chart

<img src="images/explain-page.png" alt="Explanation of the payment success chart" width="720">

A deterministic facts engine computes what changed (anomaly episodes in units of the series'
own noise, level shifts, divergence between series, gaps to targets and last year); a language
model only phrases those facts, and every number it writes is checked against them.
[How well it finds the injected anomalies →](insight-evaluation.md)

## Built with

Python 3.12 · Apache Airflow 3.3 · PostgreSQL 17 · Metabase 0.64 · FastAPI · Docker Compose ·
an OpenAI-compatible LLM API. Layered warehouse (raw → staging → core → marts), idempotent
incremental loads, exactly-once file ingestion, data-quality checks as code, dashboards as
code, alerting and end-to-end tests.
