"""Deterministic facts about a chart (ADR-0016).

Everything quantitative is computed here - changes, trends, anomaly episodes, divergence
between series, share shifts, rankings, funnel drop-offs, gaps to last year or to a target -
and rendered with the chart's own number formats. The language model only turns these facts
into prose and may not introduce numbers of its own; the numbers recorded with each fact are
what the narrative is verified against.
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import pairwise
from typing import Any

DATE_TYPES = ("type/Date", "type/DateTime", "type/DateTimeWithLocalTZ", "type/DateTimeWithTZ")
NUMBER_TYPES = ("type/Integer", "type/BigInteger", "type/Decimal", "type/Float", "type/Number")
PERCENT_HINTS = ("_rate", "rate", "share", "occupancy", "coverage")
NON_ADDITIVE_HINTS = (*PERCENT_HINTS, "adr", "revpar", "avg", "average", "mean")
Z_THRESHOLD = 3.5  # deviation in noise units for a single anomalous point
RUN_Z = 2.0  # ... for each point of a run of two or more
MAX_FACTS = 18


# --------------------------------------------------------------------------- numbers


@dataclass(frozen=True)
class Number:
    value: float  # in display scale: 23.5 for 23.5 %
    unit: str  # "%", "pp", "€" or ""


@dataclass
class Fact:
    kind: str
    text: str
    numbers: list[Number]
    score: float
    meta: dict[str, Any] = field(default_factory=dict)
    id: str = ""


@dataclass
class FactSheet:
    title: str
    display: str
    facts: list[Fact]
    dates: set[date]
    notes: list[str] = field(default_factory=list)
    labels: set[str] = field(default_factory=set)  # categories/series, e.g. "70-80 %"

    def numbers(self) -> list[Number]:
        return [n for f in self.facts for n in f.numbers]

    def as_prompt(self) -> list[dict[str, str]]:
        return [{"id": f.id, "kind": f.kind, "fact": f.text} for f in self.facts]


class Fmt:
    """Formats numbers like the chart does and records every number it renders."""

    def __init__(self) -> None:
        self.numbers: list[Number] = []

    def _keep(self, value: float, unit: str) -> None:
        self.numbers.append(Number(round(value, 6), unit))

    def val(self, v: float, style: str) -> str:
        if style == "percent":
            self._keep(v * 100, "%")
            return f"{v * 100:.1f}%"
        if style == "currency":
            self._keep(v, "€")
            return f"€{v:,.0f}" if abs(v) >= 1000 else f"€{v:,.2f}"
        self._keep(v, "")
        return f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:,.2f}"

    def delta(self, d: float, style: str) -> str:
        if style == "percent":
            self._keep(d * 100, "pp")
            return f"{d * 100:+.1f} pp"
        if style == "currency":
            self._keep(d, "€")
            sign = "+" if d >= 0 else "-"
            return f"{sign}€{abs(d):,.0f}" if abs(d) >= 1000 else f"{sign}€{abs(d):,.2f}"
        self._keep(d, "")
        return f"{d:+,.0f}" if abs(d) >= 100 or float(d).is_integer() else f"{d:+,.2f}"

    def rel(self, r: float) -> str:
        self._keep(r * 100, "%")
        return f"{r * 100:+.1f}%"

    def share(self, s: float) -> str:
        self._keep(s * 100, "%")
        return f"{s * 100:.1f}%"

    def count(self, n: int) -> str:
        self._keep(n, "")
        return f"{n:,}"

    def ratio(self, r: float) -> str:
        self._keep(r, "")
        return f"{r:.1f}x"


def change_text(f: Fmt, old: float, new: float, style: str) -> str:
    """Absolute change in percentage points for rates, otherwise absolute and relative."""
    if style == "percent":
        return f.delta(new - old, style)
    if old:
        return f"{f.delta(new - old, style)} ({f.rel((new - old) / abs(old))})"
    return f.delta(new - old, style)


# --------------------------------------------------------------------------- columns


@dataclass(frozen=True)
class Column:
    index: int
    name: str
    title: str
    kind: str  # date | number | text
    style: str  # percent | currency | number


def humanize(name: str) -> str:
    """Native-query columns come back as snake_case names: conversion_rate -> Conversion rate."""
    return name.replace("_", " ").capitalize() if "_" in name and " " not in name else name


def read_columns(cols: list[dict], viz: dict) -> list[Column]:
    settings = viz.get("column_settings", {})
    series = viz.get("series_settings", {})
    out = []
    for i, c in enumerate(cols):
        base = c.get("base_type", "")
        effective = c.get("effective_type", base)
        kind = (
            "date"
            if base in DATE_TYPES or effective in DATE_TYPES
            else "number"
            if base in NUMBER_TYPES
            else "text"
        )
        cs = settings.get(f'["name","{c["name"]}"]', {})
        style = cs.get("number_style")
        if style not in ("percent", "currency"):
            style = (
                "percent"
                if kind == "number" and any(h in c["name"] for h in PERCENT_HINTS)
                else "number"
            )
        title = (
            series.get(c["name"], {}).get("title")
            or cs.get("column_title")
            or humanize(c.get("display_name") or c["name"])
        )
        out.append(Column(i, c["name"], title, kind, style))
    return out


def to_date(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


# --------------------------------------------------------------------------- statistics


def noise_sigma(values: list[float]) -> float:
    """Typical period-to-period noise, robust to trends and outliers (MAD of differences)."""
    diffs = [b - a for a, b in pairwise(values)]
    centre = statistics.median(diffs)
    deviations = [abs(d - centre) for d in diffs]
    sigma = 1.4826 * statistics.median(deviations) / 2**0.5
    if sigma == 0:
        sigma = 1.2533 * statistics.fmean(deviations) / 2**0.5
    return sigma


def anomaly_scores(values: list[float]) -> list[tuple[float, float]]:
    """(z, reference) per point: deviation from the median of its neighbours (+-3 periods),
    in units of the series' noise. Two passes, so a strong outlier does not distort the
    reference of the points around it (e.g. the recovery after a dip)."""
    n = len(values)
    sigma = noise_sigma(values)

    def score(excluded: set[int]) -> list[tuple[float, float]]:
        out = []
        for i in range(n):
            neighbours = [
                values[j]
                for j in range(max(0, i - 3), min(n, i + 4))
                if j != i and j not in excluded
            ]
            ref = statistics.median(neighbours) if neighbours else values[i]
            out.append(((values[i] - ref) / sigma if sigma else 0.0, ref))
        return out

    first = score(set())
    strong = {i for i, (z, _) in enumerate(first) if abs(z) >= Z_THRESHOLD}
    return score(strong)


@dataclass
class Episode:
    start: int
    end: int  # inclusive index
    direction: str  # "low" | "high"
    extreme: float
    z: float
    reference: float  # typical value around the episode


def min_deviation(values: list[float], reference: float, style: str) -> float:
    """Smallest deviation worth reporting: 3 pp for rates, Poisson noise for small counts."""
    if style == "percent":
        return 0.03
    floor = 0.15 * abs(reference)
    if all(float(v).is_integer() for v in values):
        floor = max(floor, 6.0, 3 * max(reference, 1.0) ** 0.5)
    return max(floor, 1e-9)


def episodes(values: list[float], style: str, max_episodes: int = 2) -> list[Episode]:
    """Short-lived deviations from the local level.

    A point is anomalous when it deviates by at least 3.5 noise units, or by at least 2 for
    runs of two or more consecutive points in the same direction (sustained deviation). The
    first point is skipped: the first period of a filter window is often incomplete. Longer
    shifts in level are left to ``level_shift``.
    """
    if len(values) < 6:
        return []
    scores = anomaly_scores(values)
    candidate: list[str | None] = [None]
    for v, (z, ref) in list(zip(values, scores, strict=True))[1:]:
        big = abs(z) >= RUN_Z and abs(v - ref) >= min_deviation(values, ref, style)
        candidate.append(("low" if z < 0 else "high") if big else None)
    found: list[Episode] = []
    i = 0
    while i < len(values):
        if candidate[i] is None:
            i += 1
            continue
        j = i
        while j + 1 < len(values) and candidate[j + 1] == candidate[i]:
            j += 1
        strongest = max(range(i, j + 1), key=lambda k: abs(scores[k][0]))
        if j > i or abs(scores[strongest][0]) >= Z_THRESHOLD:
            pick = min if candidate[i] == "low" else max
            refs = [scores[k][1] for k in range(i, j + 1)]
            found.append(
                Episode(
                    i,
                    j,
                    candidate[i],
                    pick(values[i : j + 1]),
                    scores[strongest][0],
                    statistics.median(refs),
                )
            )
        i = j + 1
    return sorted(found, key=lambda e: -abs(e.z))[:max_episodes]


def extreme_run(values: list[float], k: int = 2) -> tuple[str, int] | None:
    """The k lowest (or highest) values are consecutive and stand out from their neighbours.

    Adjacent extremes alone are common at the end of a trend; requiring the run to deviate
    from the *surrounding* periods (+-4, run excluded) by 1.5 noise units keeps only genuine
    short-lived dips or spikes.
    """
    if len(values) < 8:
        return None
    sigma = noise_sigma(values)
    body = list(range(1, len(values)))  # skip the possibly incomplete first period
    for direction, order in (("low", 1), ("high", -1)):
        top = sorted(body, key=lambda i: order * values[i])[:k]
        lo, hi = min(top), max(top)
        if hi - lo != k - 1:
            continue
        around = values[max(1, lo - 4) : lo] + values[hi + 1 : hi + 5]
        if not around or not sigma:
            continue
        run_mean = statistics.fmean(values[lo : hi + 1])
        if abs(run_mean - statistics.median(around)) >= 1.5 * sigma:
            return direction, lo
    return None


@dataclass
class LevelShift:
    index: int  # first point of the new level
    before: float
    after: float
    t: float


def _sse(values: list[float]) -> float:
    mean = statistics.fmean(values)
    return sum((v - mean) ** 2 for v in values)


def _linear_sse(values: list[float]) -> float:
    n = len(values)
    xs = range(n)
    mx, my = (n - 1) / 2, statistics.fmean(values)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, values, strict=True)) / sxx
    return sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, values, strict=True))


def level_shift(values: list[float], style: str, min_segment: int = 3) -> LevelShift | None:
    """The strongest step change, if a step explains the series much better than a trend."""
    n = len(values)
    if n < 2 * min_segment + 1:
        return None
    best: LevelShift | None = None
    for k in range(min_segment + 1, n - min_segment + 1):  # index 0: possibly incomplete
        a, b = values[1:k], values[k:]
        ma, mb = statistics.fmean(a), statistics.fmean(b)
        se = (statistics.pvariance(a) / len(a) + statistics.pvariance(b) / len(b)) ** 0.5
        t = abs(mb - ma) / se if se else float("inf")
        if best is None or t > best.t:
            best = LevelShift(k, ma, mb, t)
    if best is None or best.t < 4:
        return None
    if abs(best.after - best.before) < min_deviation(values, best.before, style):
        return None
    # a step must explain the series better than a gradual trend - clearly so unless the
    # step itself is very strong (a shift followed by further drift still counts)
    body = values[1:]
    split = best.index - 1
    ratio = (_sse(body[:split]) + _sse(body[split:])) / (_linear_sse(body) or 1)
    if ratio <= 0.8 or (best.t >= 6 and ratio <= 1.0):
        return best
    return None


# --------------------------------------------------------------------------- analysis


class Analysis:
    def __init__(self, title: str, display: str, spec: dict[str, Any]) -> None:
        self.title, self.display, self.spec = title, display, spec
        self.facts: list[Fact] = []
        self.dates: set[date] = set()
        self.labels: set[str] = set()

    def add(self, kind: str, text: str, f: Fmt, score: float, **meta: Any) -> None:
        self.facts.append(Fact(kind, text, list(f.numbers), score, meta))

    def sheet(self) -> FactSheet:
        ranked = sorted(self.facts, key=lambda x: -x.score)[:MAX_FACTS]
        for i, fact in enumerate(ranked, start=1):
            fact.id = f"F{i}"
        return FactSheet(self.title, self.display, ranked, self.dates, labels=self.labels)

    # ---------------------------------------------------------------- scalar
    def scalar(self, col: Column, value: float | None) -> None:
        if value is None:
            self.add("value", f"{self.title}: no data for the selected filters.", Fmt(), 1)
            return
        f = Fmt()
        self.add("value", f"{self.title}: {f.val(value, col.style)}.", f, 3)
        target = self.spec.get("target")
        if target is not None:
            f = Fmt()
            gap = value - target["value"]
            position = "above" if gap >= 0 else "below"
            self.add(
                "benchmark",
                f"{self.title} is {position} the {target.get('label', 'target')} of "
                f"{f.val(target['value'], col.style)} ({f.delta(gap, col.style)}).",
                f,
                2.5,
            )

    # ---------------------------------------------------------------- time series
    def label(self, d: date, weekly: bool) -> str:
        self.dates.add(d)
        if weekly:
            self.dates.add(d + timedelta(days=6))
            return f"week of {d.isoformat()}"
        return d.isoformat()

    def time_series(
        self,
        series: dict[str, list[tuple[date, float]]],
        style: str,
        additive: bool,
        breakdown: bool,
    ):
        """``breakdown``: the series split one metric by category (so totals and shares make
        sense); otherwise they are different metrics on the same axis."""
        all_dates = sorted({d for pts in series.values() for d, _ in pts})
        if len(all_dates) == 1:  # one period only: state the values
            for name, points in series.items():
                f = Fmt()
                self.add(
                    "value",
                    f"{name}: {f.val(points[0][1], style)} on {self.label(points[0][0], False)}.",
                    f,
                    2 + (abs(points[0][1]) > 0),
                    series=name,
                )
            return
        gaps = [(b - a).days for a, b in pairwise(all_dates)]
        weekly = bool(gaps) and statistics.median(gaps) == 7
        unit = "week" if weekly else "period"
        found: dict[str, list[Episode]] = {}
        for name, points in series.items():
            points = sorted(points)
            if len(points) < 2:
                continue
            dates_, values = [d for d, _ in points], [v for _, v in points]
            med = statistics.median(values)
            f = Fmt()
            last, prev = values[-1], values[-2]
            self.add(
                "latest",
                f"{name}: latest {unit} ({self.label(dates_[-1], weekly)}) "
                f"{f.val(last, style)}, {change_text(f, prev, last, style)} vs the {unit} before.",
                f,
                1.2 + min(abs(last - prev) / (abs(prev) or 1), 1),
                series=name,
            )
            imin, imax = values.index(min(values)), values.index(max(values))
            f = Fmt()
            self.add(
                "range",
                f"{name} ranged from {f.val(values[imin], style)} "
                f"({self.label(dates_[imin], weekly)}) to {f.val(values[imax], style)} "
                f"({self.label(dates_[imax], weekly)}); typical (median) {f.val(med, style)}.",
                f,
                0.8,
                series=name,
            )
            if len(values) >= 6:
                k = len(values) // 3
                early, late = statistics.fmean(values[:k]), statistics.fmean(values[-k:])
                f = Fmt()
                self.add(
                    "trend",
                    f"{name} averaged {f.val(late, style)} over the last {f.count(k)} {unit}s vs "
                    f"{f.val(early, style)} over the first {f.count(k)} "
                    f"({change_text(f, early, late, style)}).",
                    f,
                    0.6 + min(abs(late - early) / (abs(early) or 1), 1.5),
                    series=name,
                )
            found[name] = []
            for ep in episodes(values, style):
                found[name].append(ep)
                start, end = dates_[ep.start], dates_[ep.end]
                period = (
                    self.label(start, weekly)
                    if ep.start == ep.end
                    else f"{self.label(start, weekly)} to {self.label(end, weekly)}"
                )
                f = Fmt()
                self.add(
                    "anomaly",
                    f"{name} was unusually {ep.direction} in {period}: "
                    f"{f.val(ep.extreme, style)} vs {f.val(ep.reference, style)} in the "
                    f"surrounding {unit}s ({change_text(f, ep.reference, ep.extreme, style)}).",
                    f,
                    3 + min(abs(ep.z), 10) / 2,
                    series=name,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    direction=ep.direction,
                )
            run = extreme_run(values)
            if run and not found[name]:
                direction, i0 = run
                f = Fmt()
                self.add(
                    "extreme_run",
                    f"{name}: the two {'lowest' if direction == 'low' else 'highest'} {unit}s "
                    f"were consecutive - {self.label(dates_[i0], weekly)} "
                    f"({f.val(values[i0], style)}) and {self.label(dates_[i0 + 1], weekly)} "
                    f"({f.val(values[i0 + 1], style)}) - vs a typical {f.val(med, style)}.",
                    f,
                    3.2,
                    series=name,
                    start=dates_[i0].isoformat(),
                    end=dates_[i0 + 1].isoformat(),
                    direction=direction,
                )
            shift = level_shift(values, style)
            if shift:
                f = Fmt()
                self.add(
                    "level_shift",
                    f"{name} shifted to a new level from "
                    f"{self.label(dates_[shift.index], weekly)}: "
                    f"averaging {f.val(shift.after, style)} since vs {f.val(shift.before, style)} "
                    f"before ({change_text(f, shift.before, shift.after, style)}).",
                    f,
                    3.5 + min(shift.t, 10) / 4,
                    series=name,
                    start=dates_[shift.index].isoformat(),
                    end=dates_[-1].isoformat(),
                    direction="low" if shift.after < shift.before else "high",
                )
        target = self.spec.get("target")
        if target and target.get("series") in series:
            self.against_target(series[target["series"]], target, style, unit)
        self.divergence(series, found, style, weekly)
        for a, b in self.spec.get("compare", []):
            self.compare(series, a, b, style, additive, weekly)
        if breakdown and additive and len(series) > 1:
            self.shares(series, found, weekly)

    def against_target(self, points, target: dict, style: str, unit: str) -> None:
        """Deterministic comparison with a target, so the narrative never has to infer it."""
        values = [v for _, v in sorted(points)][1:] or [v for _, v in points]
        goal, label = target["value"], target.get("label", "target")
        mean = statistics.fmean(values)
        met = sum(v >= goal for v in values)
        f = Fmt()
        self.add(
            "benchmark",
            f"{target['series']} averaged {f.val(mean, style)}, "
            f"{'above' if mean >= goal else 'below'} the {label} of {f.val(goal, style)} "
            f"({f.delta(mean - goal, style)}); {f.count(met)} of {f.count(len(values))} "
            f"{unit}s met it.",
            f,
            3.0,
            series=target["series"],
        )

    def divergence(self, series, found, style: str, weekly: bool) -> None:
        """One series breaks out while the others stay normal: points to a specific cause."""
        with_ep = [n for n, eps in found.items() if eps]
        without = [n for n, eps in found.items() if not eps]
        if not with_ep or not without or len(series) > 6:
            return
        for name in with_ep:
            ep = max(found[name], key=lambda e: abs(e.z))
            pts = dict(sorted(series[name]))
            ep_dates = sorted(pts)[ep.start : ep.end + 1]
            f = Fmt()
            others = []
            for other in without:
                other_pts = dict(series[other])
                same = [other_pts[d] for d in ep_dates if d in other_pts]
                if same:
                    typical = statistics.median(other_pts.values())
                    others.append(
                        f"{other} {f.val(statistics.fmean(same), style)} "
                        f"(typical {f.val(typical, style)})"
                    )
            if others:
                self.add(
                    "divergence",
                    f"Only {name} broke out in {self.label(ep_dates[0], weekly)}"
                    f"{' to ' + self.label(ep_dates[-1], weekly) if len(ep_dates) > 1 else ''}; "
                    f"in the same period: {', '.join(others)}.",
                    f,
                    4.5,
                    series=name,
                    start=ep_dates[0].isoformat(),
                    end=ep_dates[-1].isoformat(),
                )

    def compare(self, series, a: str, b: str, style: str, additive: bool, weekly: bool) -> None:
        if a not in series or b not in series:
            return
        pa, pb = dict(series[a]), dict(series[b])
        common = sorted(set(pa) & set(pb))
        if not common:
            return
        va, vb = [pa[d] for d in common], [pb[d] for d in common]
        f = Fmt()
        if additive:
            ta, tb = sum(va), sum(vb)
            text = (
                f"{a} totals {f.val(ta, style)} vs {f.val(tb, style)} for {b} over the same "
                f"{f.count(len(common))} periods ({change_text(f, tb, ta, style)})."
            )
        else:
            ma, mb = statistics.fmean(va), statistics.fmean(vb)
            text = (
                f"{a} averaged {f.val(ma, style)} vs {f.val(mb, style)} for {b} over the same "
                f"{f.count(len(common))} periods ({change_text(f, mb, ma, style)})."
            )
        self.add("comparison", text, f, 2.6, series=a)
        diffs = [x - y for x, y in zip(va, vb, strict=True)]
        worst = min(range(len(diffs)), key=lambda i: diffs[i])
        best = max(range(len(diffs)), key=lambda i: diffs[i])
        for i, word in ((worst, "furthest below"), (best, "furthest above")):
            f = Fmt()
            self.add(
                "comparison",
                f"{a} was {word} {b} in {self.label(common[i], weekly)}: "
                f"{f.val(va[i], style)} vs {f.val(vb[i], style)} "
                f"({change_text(f, vb[i], va[i], style)}).",
                f,
                1.8,
                series=a,
            )

    def shares(self, series, found, weekly: bool) -> None:
        """For additive breakdowns: total over time, and shifts in each series' share."""
        totals: dict[date, float] = defaultdict(float)
        for pts in series.values():
            for d, v in pts:
                totals[d] += v
        dates_ = sorted(totals)
        values = [totals[d] for d in dates_]
        for ep in episodes(values, "number"):
            d = dates_[ep.start]
            f = Fmt()
            self.add(
                "anomaly",
                f"Total was unusually {ep.direction} in {self.label(d, weekly)}"
                f"{' to ' + self.label(dates_[ep.end], weekly) if ep.end > ep.start else ''}: "
                f"{f.val(ep.extreme, 'number')} vs {f.val(ep.reference, 'number')} in the "
                f"surrounding {'week' if weekly else 'period'}s.",
                f,
                3 + min(abs(ep.z), 10) / 2,
                series="Total",
                start=d.isoformat(),
                end=dates_[ep.end].isoformat(),
                direction=ep.direction,
            )
            for name, pts in series.items():
                p = dict(pts)
                share_now = p.get(d, 0) / totals[d] if totals[d] else 0
                shares = [p.get(x, 0) / totals[x] for x in dates_ if totals[x]]
                typical = statistics.median(shares)
                if abs(share_now - typical) >= 0.2:
                    f = Fmt()
                    self.add(
                        "share_shift",
                        f"{name} made up {f.share(share_now)} of the total in "
                        f"{self.label(d, weekly)} vs a typical {f.share(typical)}.",
                        f,
                        4.2 if share_now > typical else 2.4,
                        series=name,
                        start=d.isoformat(),
                        end=d.isoformat(),
                    )

    # ---------------------------------------------------------------- categories
    def categories(self, labels: list[str], metric: Column, values: list[float], additive: bool):
        pairs = sorted(
            ((lab, v) for lab, v in zip(labels, values, strict=True) if v is not None),
            key=lambda x: -x[1],
        )
        if not pairs:
            return
        self.labels.update(lab for lab, _ in pairs)
        style = metric.style
        f = Fmt()
        top = ", ".join(f"{lab} {f.val(v, style)}" for lab, v in pairs[:3])
        self.add("ranking", f"{metric.title} - highest: {top}.", f, 2.4, series=pairs[0][0], rank=1)
        if len(pairs) > 3:
            f = Fmt()
            low = ", ".join(f"{lab} {f.val(v, style)}" for lab, v in pairs[-2:])
            self.add(
                "ranking", f"{metric.title} - lowest: {low}.", f, 1.4, series=pairs[-1][0], rank=-1
            )
        if additive:
            total = sum(v for _, v in pairs)
            if total:
                f = Fmt()
                self.add(
                    "share",
                    f"{pairs[0][0]} accounts for {f.share(pairs[0][1] / total)} of the total "
                    f"{metric.title} of {f.val(total, style)}.",
                    f,
                    2.2,
                )
        if len(pairs) > 1 and pairs[1][1]:
            f = Fmt()
            self.add(
                "ranking",
                f"{pairs[0][0]} is {f.ratio(pairs[0][1] / pairs[1][1])} the runner-up "
                f"{pairs[1][0]} on {metric.title}.",
                f,
                1.6,
            )

    def grouped(self, rows: list[list], cat: int, group: int, metric: Column) -> None:
        """Category x group (e.g. channel x attribution model): biggest differences."""
        table: dict[str, dict[str, float]] = defaultdict(dict)
        for row in rows:
            table[str(row[cat])][str(row[group])] = row[metric.index] or 0
        groups = sorted({g for d in table.values() for g in d})
        if len(groups) != 2:  # e.g. runs by DAG and state: rank categories, show the split
            totals = {c: sum(d.values()) for c, d in table.items()}
            self.categories(list(totals), metric, list(totals.values()), is_additive(metric))
            for category, d in sorted(table.items(), key=lambda x: -sum(x[1].values()))[:5]:
                f = Fmt()
                parts = ", ".join(f"{g} {f.val(v, metric.style)}" for g, v in sorted(d.items()))
                self.add("breakdown", f"{category}: {parts}.", f, 1.5, series=category)
            return
        g1, g2 = groups
        diffs = []
        for category, d in table.items():
            a, b = d.get(g1, 0), d.get(g2, 0)
            diffs.append((b - a, category, a, b))
        for diff, category, a, b in sorted(diffs, key=lambda x: -abs(x[0]))[:4]:
            f = Fmt()
            self.add(
                "comparison",
                f"{category}: {g1} {f.val(a, metric.style)} vs {g2} {f.val(b, metric.style)} "
                f"({change_text(f, a, b, metric.style)}).",
                f,
                2.5 + min(abs(diff) / (max(a, b) or 1), 1),
                series=category,
            )
        f = Fmt()
        tot1 = sum(d.get(g1, 0) for d in table.values())
        tot2 = sum(d.get(g2, 0) for d in table.values())
        self.add(
            "value",
            f"{metric.title} in total: {g1} {f.val(tot1, metric.style)}, "
            f"{g2} {f.val(tot2, metric.style)}.",
            f,
            1,
        )

    def funnel(self, steps: list[str], values: list[float]) -> None:
        f = Fmt()
        overall = values[-1] / values[0] if values[0] else 0
        self.add(
            "funnel",
            f"{f.val(values[0], 'number')} entered at '{steps[0]}' and "
            f"{f.val(values[-1], 'number')} reached '{steps[-1]}' (overall {f.share(overall)}).",
            f,
            3,
        )
        worst = None
        for i in range(1, len(steps)):
            rate = values[i] / values[i - 1] if values[i - 1] else 0
            f = Fmt()
            self.add(
                "funnel",
                f"'{steps[i - 1]}' -> '{steps[i]}': {f.share(rate)} continue "
                f"({f.val(values[i - 1], 'number')} -> {f.val(values[i], 'number')}).",
                f,
                1.5,
            )
            if worst is None or rate < worst[0]:
                worst = (rate, steps[i - 1], steps[i])
        if worst:
            f = Fmt()
            self.add(
                "funnel",
                f"The largest drop-off is between '{worst[1]}' and '{worst[2]}': only "
                f"{f.share(worst[0])} continue.",
                f,
                3.5,
            )


# --------------------------------------------------------------------------- entry point


def is_additive(col: Column) -> bool:
    """Can values be summed across periods or categories? (counts, revenue - not ADR, rates)"""
    return col.style != "percent" and not any(h in col.name for h in NON_ADDITIVE_HINTS)


def extract(card: dict, result: dict, spec: dict[str, Any] | None = None) -> FactSheet:
    """Facts for a Metabase card given its query result (``POST .../query`` response)."""
    spec = spec or {}
    viz = card.get("visualization_settings", {})
    data = result["data"]
    cols = read_columns(data["cols"], viz)
    rows = data["rows"]
    display = card.get("display", "table")
    a = Analysis(card.get("name", "Chart"), display, spec)
    if not rows:
        a.add("value", "No data for the selected filters.", Fmt(), 1)
        return a.sheet()

    by_name = {c.name: c for c in cols}
    dims = [by_name[d] for d in viz.get("graph.dimensions", []) if d in by_name]
    metrics = [by_name[m] for m in viz.get("graph.metrics", []) if m in by_name]

    if display == "scalar" or (len(rows) == 1 and len(cols) == 1):
        col = next((c for c in cols if c.kind == "number"), cols[0])
        a.scalar(col, rows[0][col.index])
    elif display == "funnel":
        step = by_name.get(viz.get("funnel.dimension"), cols[0])
        metric = by_name.get(viz.get("funnel.metric"), cols[-1])
        a.funnel([str(r[step.index]) for r in rows], [r[metric.index] or 0 for r in rows])
    elif dims and dims[0].kind == "date":
        metric_cols = metrics or [c for c in cols if c.kind == "number"]
        series: dict[str, list[tuple[date, float]]] = defaultdict(list)
        if len(dims) > 1:
            metric = metric_cols[0]
            for r in rows:
                if r[metric.index] is not None:
                    series[str(r[dims[1].index])].append(
                        (to_date(r[dims[0].index]), r[metric.index])
                    )
            style, additive = metric.style, is_additive(metric)
            if additive:  # a category missing in a period means zero, not unknown
                all_d = sorted({d for pts in series.values() for d, _ in pts})
                for name, pts in series.items():
                    have = dict(pts)
                    series[name] = [(d, have.get(d, 0)) for d in all_d]
            if viz.get("stackable.stack_type") == "normalized" and additive:
                series = normalize(series)
                style, additive = "percent", False
        else:
            for metric in metric_cols:
                for r in rows:
                    if r[metric.index] is not None:
                        series[metric.title].append((to_date(r[dims[0].index]), r[metric.index]))
            style = metric_cols[0].style
            additive = all(is_additive(m) for m in metric_cols)
            target = spec.get("target")
            if target and target.get("series") in by_name:
                target = {**target, "series": by_name[target["series"]].title}
            a.spec = {
                **spec,
                "target": target,
                "compare": [
                    [by_name[x].title, by_name[y].title]
                    for x, y in spec.get("compare", [])
                    if x in by_name and y in by_name
                ],
            }
        a.time_series(dict(series), style, additive, breakdown=len(dims) > 1)
    elif dims:
        metric_cols = metrics or [c for c in cols if c.kind == "number"]
        if len(dims) > 1:
            a.grouped(rows, dims[0].index, dims[1].index, metric_cols[0])
        else:
            labels = [str(r[dims[0].index]) for r in rows]
            for metric in metric_cols:
                a.categories(labels, metric, [r[metric.index] for r in rows], is_additive(metric))
    else:
        number_cols = [c for c in cols if c.kind == "number"]
        text_cols = [c for c in cols if c.kind != "number"]
        if text_cols and number_cols:
            labels = [str(r[text_cols[0].index]) for r in rows]
            for metric in number_cols:
                a.categories(labels, metric, [r[metric.index] for r in rows], is_additive(metric))
    if not a.facts:  # rows but no pattern the engine knows: describe them, never "no data"
        for row in rows[:5]:
            f = Fmt()
            cells = [
                f"{c.title} {f.val(row[c.index], c.style)}"
                if c.kind == "number" and row[c.index] is not None
                else f"{c.title} {row[c.index]}"
                for c in cols
            ]
            a.add("row", "; ".join(cells) + ".", f, 1)
    return a.sheet()


def normalize(series: dict[str, list[tuple[date, float]]]) -> dict[str, list[tuple[date, float]]]:
    """Turn a stacked breakdown into shares of each period's total."""
    totals: dict[date, float] = defaultdict(float)
    for pts in series.values():
        for d, v in pts:
            totals[d] += v
    return {name: [(d, v / totals[d]) for d, v in pts if totals[d]] for name, pts in series.items()}
