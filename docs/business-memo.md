---
title: Business memo
---

# Monday review memo: four findings and what they are worth

- **To:** General managers, HotelPulse City Lisbon and HotelPulse Resort Algarve
- **From:** Data team
- **Data as of:** 16 October 2026, last 12 months unless stated otherwise

> All figures come from the HotelPulse warehouse. The bookings are the public *Hotel Booking
> Demand* dataset, replayed as a live PMS. The four problems below were **injected into the
> simulation as ground truth**, so this memo also shows that the platform finds them, and how
> close the dashboard estimates come to the truth.

## Summary

| # | Finding | Where it shows | Estimated impact | Action |
|---|---|---|---|---|
| 1 | A mobile payment outage (22 Sep – 5 Oct) pushed direct bookers to Booking.com | Revenue › *Direct share of new bookings*; Website › *Payment success rate by device*, *Failed payments by error code* | **≈ €3.5k** extra commission in two weeks; **≈ €90k a year** had it gone unnoticed | Alert on payment success per device; escalate `gateway_timeout` to the payment provider |
| 2 | Since the cookie-banner redesign (17 Aug), web analytics sees only half of the website's bookings | Website › *Tracking coverage by week* | Web KPIs understated by about **28 %** compared with before the redesign | Restore a balanced banner; report revenue from the PMS only |
| 3 | The resort's new laundry supplier: **+32 %** towels laundered per room night since 11 Sep | Operations › *Usage per room night by item*, *Purchase suggestion* | **≈ €25k a year** | Check invoices against the contract; renegotiate per-towel billing or collection frequency |
| 4 | When the hotel is 90 %+ full, breakfast complaints are **2.8×** as frequent | Operations › *Breakfast complaints by occupancy during the stay* | 189 nights a year are affected; extra breakfast staff on those nights costs **≈ €11k a year** | Staff breakfast from the occupancy forecast |

Context for every euro below: OTAs bring **44 %** of room nights at an average commission of
**17.1 %**, which is **€948k** a year. Direct channels bring **11.6 %**.

---

## 1. Mobile payment outage: €3.5k in two weeks, €90k a year if unnoticed

**What happened.** From 22 September the website's mobile payment step failed intermittently
with `gateway_timeout`. Mobile payment success collapsed while desktop and tablet stayed
normal. Guests did not give up on the stay: they booked it on Booking.com instead.

**Evidence.** Website bookings fell from **7.9 a day** (the 8 weeks before) to **3.9 a day**
during the 14 days. That is about **56 missing direct bookings** at an average value of **€458**,
about **€25.7k** of bookings moved to OTAs. Booking.com intake rose from 51.9 to 59.0 a day
over the same period.

**Estimate.** €25.7k × (17 % Booking.com − 3 % website cost) ≈ **€3.6k** extra commission. The
simulation's ground truth is 62 diverted bookings worth €23.7k, which gives **€3.3k**: the
dashboard-based estimate is within 10 %. Repeated every two weeks, the same leak would cost
**≈ €90k a year**, about 10 % of the group's total OTA commission.

**Action.** Alert on payment success rate *per device type* (a group-wide rate hides a
mobile-only failure). Escalate `gateway_timeout` to the payment provider with the affected time
window.

## 2. Tracking coverage: web analytics now sees half the bookings

**What happened.** The redesigned cookie banner made "Reject" the more prominent button. The
tracker only sees visitors who accept.

**Evidence.** We match tracked bookings to the PMS by confirmation code. Coverage was
**72 %** before 17 August and **52 %** since, which is below our 60 % reliability threshold.

**Impact.** Before vs. after comparisons of visits or tracked bookings are biased by about
**−28 %** (52 / 72). A "drop in website traffic" since August is mostly a measurement effect.
Rates such as conversion and payment success remain usable. No revenue is lost: revenue is
always reported from the PMS.

**Action.** Give "Accept" and "Reject" equal prominence (consent stays free). Annotate
dashboards with the change date. Keep reporting revenue from the PMS, never from the tracker.

## 3. Laundry supplier change at the resort: ≈ €25k a year

**What happened.** On 11 September the resort switched to a supplier that bills per towel and
collects more often.

**Evidence.** Towels laundered per occupied room night went from **1.79** to **2.36** at the
resort (**+32 %**), while the city hotel stayed at **1.79**. Usage is measured per room night
sold, so this is not explained by occupancy. The purchase suggestion shows the same change (+25 %
against the previous 28 days) before the next order is placed.

**Estimate.** +0.57 towels × €0.85 = **€0.48 per room night** × 52,110 resort room nights a year
≈ **€25k a year**. About €3k has been spent so far.

**Action.** Check the invoices against the contract: billed towels per room vs. what
housekeeping hands out. Renegotiate collection frequency, or reintroduce the towel-reuse card.
Watch the *Usage per room night* chart for the resort after the change.

## 4. Breakfast at full house: staff from the forecast

**What happened.** Breakfast is staffed for a normal house. On nights when the hotel is (nearly)
full, queues and empty buffets follow.

**Evidence.** We link each review to its stay through the confirmation code and compare it with
the hotel's occupancy during that stay. Breakfast complaints appear in **9.2 %** of reviews from
stays at 90 %+ occupancy, against **3.2–3.4 %** at every lower level. A review that complains
about breakfast scores **6.6** instead of **8.4**. Both hotels together had **189 nights** at 90 %+
in the last year.

**Estimate.** One extra breakfast attendant for 4 hours on those nights costs about
189 × 4 h × €15 ≈ **€11k a year**. That would avoid about 58 complaint reviews a year. The effect
on the overall score is small (+0.03), but these are the nights with the most guests and the
highest rates, so this is a guest-experience fix on the most visible nights.

**Action.** Use the booking pace (rooms on the books for the next 120 nights) to plan breakfast
staff and buffet replenishment for nights forecast at 90 %+. Only 8 such nights are on the books
right now (low season); the summer peak is when it matters.

---

## Method and caveats

- **Sources:** PMS reservations (incremental daily extract), website tracking (consent-based,
  reconciled against the PMS), daily consumables and review exports. All data is joined in the
  warehouse (`marts.*`).
- **Commission rates:** OTAs 15–18 % (Booking.com 17 %), the hotel website 3 % (booking
  engine and payment fees), phone and walk-in 0 %.
- **Simulation:** consumable prices, usage rates and review behaviour are simulated with
  realistic but assumed parameters, and the four findings are injected anomalies. The value of
  this memo is the method: each figure comes from a query against the warehouse and can be
  re-run.
- **Explanations:** every chart referenced here has an *Explain this chart* button. Its
  detection of these four problems is scored in [insight-evaluation.md](insight-evaluation.md).
