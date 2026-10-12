"""TED defence tender tracker.

Pulls European public tenders for drones, counter-drone, missiles and more from
TED (the EU's official tender journal), keeps the ones a defence or security
buyer published, and writes a CSV plus an HTML report. Marks what is new since
the last run.

    python tracker.py                          # last 30 days, drones + counter-drone + missiles
    python tracker.py --days 90 --defence-only
    python tracker.py --categories drones,space --countries DEU,NLD,GRC
    python tracker.py --open-only              # only tenders you can still bid on
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

from categories import (CATEGORIES, CIVIL_OVERRIDE_TERMS, DEFAULT_CATEGORIES,
                        DEFENCE_LEGAL_BASIS, MILITARY_BUYER_TERMS, NOTICE_KIND,
                        SECURITY_BUYER_TERMS)

API_URL = "https://api.ted.europa.eu/v3/notices/search"
FIELDS = [
    "publication-number", "notice-title", "buyer-name", "buyer-country",
    "publication-date", "deadline-receipt-tender-date-lot", "notice-type",
    "classification-cpv", "estimated-value-lot", "total-value", "legal-basis",
    "main-activity", "links",
]
PAGE_SIZE = 100
OPEN_WITHOUT_DEADLINE_DAYS = 40
MAX_PAGES = 20


# ---------------------------------------------------------------- data model

@dataclass
class Tender:
    id: str
    published: str
    kind: str
    title: str
    buyer: str
    country: str
    deadline: str
    value_eur: float | None
    defence_buyer: bool
    buyer_type: str = "civil"      # military / security / civil
    buyer_reason: str = ""         # why we classified it that way
    categories: list[str] = field(default_factory=list)
    cpv: list[str] = field(default_factory=list)
    link: str = ""
    new: bool = False

    @property
    def is_open(self) -> bool:
        if self.kind != NOTICE_KIND["cn"]:
            return False
        if self.deadline:
            return self.deadline >= date.today().isoformat()
        # Many notices leave the deadline field empty. Most tenders close within ~40 days,
        # so without a deadline we only count recent ones as open.
        return self.published >= (date.today() - timedelta(days=OPEN_WITHOUT_DEADLINE_DAYS)).isoformat()


# ---------------------------------------------------------------- query

def build_query(categories: list[str], since: date, countries: list[str], defence_only: bool) -> str:
    cpv, terms = [], []
    for key in categories:
        cpv += CATEGORIES[key]["cpv"]
        terms += CATEGORIES[key]["title_terms"]

    parts = []
    if cpv:
        parts.append(f"classification-cpv IN ({' '.join(sorted(set(cpv)))})")
    for t in terms:
        parts.append(f'notice-title ~ ("{t}")')
    q = "(" + " OR ".join(parts) + ")"
    q += f" AND publication-date>={since:%Y%m%d}"
    if countries:
        q += f" AND buyer-country IN ({' '.join(countries)})"
    if defence_only:
        q += f" AND legal-basis IN ({DEFENCE_LEGAL_BASIS})"
    return q + " SORT BY publication-date DESC"


def fetch(query: str) -> list[dict]:
    import requests  # imported here so --fixture runs work without it

    notices: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        body = {"query": query, "fields": FIELDS, "limit": PAGE_SIZE, "page": page}
        for attempt in range(4):
            r = requests.post(API_URL, json=body, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            break
        if r.status_code != 200:
            sys.exit(f"TED API error {r.status_code}: {r.text[:500]}")
        data = r.json()
        batch = data.get("notices", [])
        notices += batch
        total = data.get("totalNoticeCount", 0)
        print(f"  page {page}: {len(notices)}/{total}")
        if len(notices) >= total or not batch:
            break
        time.sleep(1)  # be polite, TED rate-limits
    return notices


# ---------------------------------------------------------------- cleaning

def _first_lang(value, prefer=("eng",)) -> str:
    """TED returns multilingual dicts like {"eng": "..."} or {"pol": ["..."]}."""
    if not value:
        return ""
    if isinstance(value, str):
        return value
    for lang in list(prefer) + list(value.keys()):
        v = value.get(lang)
        if v:
            return v[0] if isinstance(v, list) else v
    return ""


def _value(n: dict) -> float | None:
    if n.get("total-value"):
        return float(n["total-value"])
    lots = {float(x) for x in n.get("estimated-value-lot") or [] if x}
    return sum(lots) if lots else None


def _kind(notice_type: str) -> str:
    for prefix, label in NOTICE_KIND.items():
        if notice_type.startswith(prefix + "-") or notice_type == prefix:
            return label
    return notice_type or "Other"


def _categories(cpv: list[str], title: str) -> list[str]:
    found = []
    t = title.lower()
    for key, cat in CATEGORIES.items():
        if any(c.startswith(code.rstrip("0")) for c in cpv for code in cat["cpv"]) \
                or any(term.lower() in t for term in cat["title_terms"]):
            found.append(key)
    return found


def classify_buyer(buyer: str, main_activity: list[str], legal_basis: list[str]) -> tuple[str, str]:
    """Return (military|security|civil, reason). Order explained in categories.py."""
    b = buyer.lower()
    for term in CIVIL_OVERRIDE_TERMS:
        if term in b:
            return "civil", f"name: {term}"
    for term in SECURITY_BUYER_TERMS:
        if term in b:
            return "security", f"name: {term}"
    for term in MILITARY_BUYER_TERMS:
        if term in b:
            return "military", f"name: {term}"
    if "defence" in main_activity:
        return "military", "TED activity: defence"
    if "pub-os" in main_activity:
        return "security", "TED activity: public order & safety"
    if DEFENCE_LEGAL_BASIS in legal_basis:
        return "military", "defence directive 2009/81"
    return "civil", f"TED activity: {'/'.join(sorted(set(main_activity))) or 'none'}"


def clean(n: dict) -> Tender:
    cpv = sorted(set(n.get("classification-cpv") or []))
    title = _first_lang(n.get("notice-title"))
    buyer = _first_lang(n.get("buyer-name"))
    deadlines = sorted({d[:10] for d in n.get("deadline-receipt-tender-date-lot") or []})
    btype, reason = classify_buyer(buyer, n.get("main-activity") or [], n.get("legal-basis") or [])
    links = (n.get("links") or {}).get("html") or {}
    return Tender(
        id=n["publication-number"],
        published=(n.get("publication-date") or "")[:10],
        kind=_kind(n.get("notice-type") or ""),
        title=title,
        buyer=buyer,
        country=", ".join(sorted(set(n.get("buyer-country") or []))),
        deadline=deadlines[0] if deadlines else "",
        value_eur=_value(n),
        defence_buyer=btype != "civil",
        buyer_type=btype,
        buyer_reason=reason,
        categories=_categories(cpv, title),
        cpv=cpv,
        link=links.get("ENG") or f"https://ted.europa.eu/en/notice/-/detail/{n['publication-number']}",
    )


# ---------------------------------------------------------------- state + output

def dedupe(tenders: list[Tender]) -> list[Tender]:
    """Buyers often republish the same tender (corrections, extensions). Keep the latest
    notice per buyer + title + type, so one tender isn't counted (and valued) three times."""
    latest: dict[tuple, Tender] = {}
    for t in tenders:
        key = (t.buyer.lower(), t.title.lower(), t.kind)
        if key not in latest or t.published > latest[key].published:
            latest[key] = t
    return sorted(latest.values(), key=lambda t: t.published, reverse=True)


def mark_new(tenders: list[Tender], state_file: Path) -> None:
    seen = set(json.loads(state_file.read_text())) if state_file.exists() else set()
    first_run = not seen
    for t in tenders:
        t.new = not first_run and t.id not in seen
    state_file.write_text(json.dumps(sorted(seen | {t.id for t in tenders})))


def write_csv(tenders: list[Tender], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig so Excel reads Greek/Polish
        w = csv.writer(f)
        w.writerow(["new", "published", "kind", "deadline", "country", "buyer", "buyer_type", "buyer_reason",
                    "value_eur", "categories", "title", "link", "id"])
        for t in tenders:
            w.writerow([t.new, t.published, t.kind, t.deadline, t.country, t.buyer, t.buyer_type, t.buyer_reason,
                        f"{t.value_eur:.0f}" if t.value_eur else "", "|".join(t.categories),
                        t.title, t.link, t.id])


def _money(v: float | None) -> str:
    if not v:
        return "–"
    return f"€{v/1e6:.1f}M" if v >= 1e6 else f"€{v/1e3:.0f}K"


def write_html(tenders: list[Tender], path: Path, query: str, excluded: list[Tender] | None = None) -> None:
    e = html.escape
    open_ = [t for t in tenders if t.is_open]
    open_.sort(key=lambda t: (not t.defence_buyer, t.deadline or "9999"))
    rest = sorted((t for t in tenders if not t.is_open), key=lambda t: not t.defence_buyer)
    defence_value = sum(t.value_eur or 0 for t in tenders if t.defence_buyer)
    by_country: dict[str, float] = {}
    for t in tenders:
        if t.defence_buyer and t.value_eur:
            by_country[t.country] = by_country.get(t.country, 0) + t.value_eur
    top = sorted(by_country.items(), key=lambda x: -x[1])[:6]
    civil = sorted({(t.buyer, t.buyer_reason) for t in list(tenders) + list(excluded or []) if not t.defence_buyer})

    def _tag(t):
        if not t.defence_buyer:
            return ""
        return f" <span class='tag {t.buyer_type}' title='{e(t.buyer_reason)}'>{t.buyer_type}</span>"

    def rows(items):
        out = []
        for t in items:
            out.append(
                f"<tr class='{'def' if t.defence_buyer else ''}'>"
                f"<td>{'<b class=new>NEW</b> ' if t.new else ''}{e(t.published)}</td>"
                f"<td>{e(t.kind)}</td><td>{e(t.deadline or '–')}</td><td>{e(t.country)}</td>"
                f"<td>{e(t.buyer)}{_tag(t)}</td>"
                f"<td class=num>{_money(t.value_eur)}</td>"
                f"<td><a href='{e(t.link)}' target=_blank>{e(t.title)}</a>"
                f"<div class=cats>{e(', '.join(CATEGORIES[c]['label'] for c in t.categories))}</div></td></tr>")
        return "\n".join(out) or "<tr><td colspan=7>Nothing here.</td></tr>"

    head = "<tr><th>Published</th><th>Type</th><th>Deadline</th><th>Country</th><th>Buyer</th><th>Value</th><th>Tender</th></tr>"
    path.write_text(f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Defence tenders</title><style>
body{{font:14px/1.45 system-ui,sans-serif;margin:24px;color:#1c1c1c;background:#fff}}
h1{{font-size:22px;margin:0}} h2{{font-size:16px;margin:28px 0 8px}}
.sub{{color:#666;margin:4px 0 18px}} .kpis{{display:flex;gap:12px;flex-wrap:wrap}}
.kpi{{border:1px solid #e3e3e3;border-radius:8px;padding:10px 14px;min-width:140px}}
.kpi b{{display:block;font-size:20px}} table{{border-collapse:collapse;width:100%}}
th,td{{text-align:left;padding:7px 8px;border-bottom:1px solid #eee;vertical-align:top}}
th{{font-size:12px;color:#666;text-transform:uppercase;letter-spacing:.03em}}
tr.def td{{background:#f6f9ff}} .num,td:nth-child(-n+3){{white-space:nowrap}} .num{{text-align:right}}
.tag{{font-size:11px;background:#dfe8ff;color:#1d3f99;border-radius:4px;padding:1px 5px}} .tag.security{{background:#eee6fb;color:#5b2d9e}}
details{{margin-top:24px;color:#555}} details li{{margin:2px 0}}
.new{{color:#b3261e}} .cats{{color:#888;font-size:12px}} a{{color:#1d3f99}}
code{{font-size:11px;color:#888;word-break:break-all}}
</style></head><body>
<h1>European defence tenders</h1>
<div class=sub>Source: TED, run {datetime.now():%d %b %Y %H:%M}. Blue rows = military or security buyer (hover the tag to see why).</div>
<div class=kpis>
<div class=kpi><b>{len(tenders)}</b>notices</div>
<div class=kpi><b>{len(open_)}</b>open to bid</div>
<div class=kpi><b>{sum(t.defence_buyer for t in tenders)}</b>from defence/security buyers</div>
<div class=kpi><b>{_money(defence_value)}</b>defence value</div>
<div class=kpi><b>{sum(t.new for t in tenders)}</b>new since last run</div>
</div>
<h2>Top buyers by defence value</h2><div class=sub>{' · '.join(f'{e(c)} {_money(v)}' for c, v in top) or '–'}</div>
<h2>Open tenders (defence buyers first, then by deadline)</h2><table>{head}{rows(open_)}</table>
<h2>Awards and other notices</h2><table>{head}{rows(rest)}</table>
<details><summary>Left out as civil buyers ({len(civil)}) — check nothing military slipped in here</summary><ul>{''.join(f"<li>{e(b)} <span class=cats>({e(r)})</span></li>" for b, r in civil)}</ul></details>
<p><code>{e(query)}</code></p>
</body></html>""", encoding="utf-8")


# ---------------------------------------------------------------- main

def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Track European defence tenders on TED.")
    p.add_argument("--days", type=int, default=30, help="look back this many days (default 30)")
    p.add_argument("--categories", default=",".join(DEFAULT_CATEGORIES),
                   help=f"comma list from: {', '.join(CATEGORIES)}")
    p.add_argument("--countries", default="", help="ISO3 buyer countries, e.g. DEU,NLD,GRC")
    p.add_argument("--defence-only", action="store_true",
                   help="only notices under the EU defence directive 2009/81")
    p.add_argument("--hide-civil", action="store_true",
                   help="drop universities, cities etc.; keep defence and security buyers")
    p.add_argument("--military-only", action="store_true",
                   help="keep only military buyers (drops police, border guards, interior ministries)")
    p.add_argument("--open-only", action="store_true", help="only tenders still open to bid")
    p.add_argument("--out", default="output", help="output folder (default ./output)")
    p.add_argument("--fixture", help="read a saved TED JSON response instead of calling the API")
    a = p.parse_args(argv)

    cats = [c.strip() for c in a.categories.split(",") if c.strip()]
    bad = [c for c in cats if c not in CATEGORIES]
    if bad:
        p.error(f"unknown categories: {bad}")
    countries = [c.strip().upper() for c in a.countries.split(",") if c.strip()]
    query = build_query(cats, date.today() - timedelta(days=a.days), countries, a.defence_only)

    print(f"Query: {query}")
    raw = json.loads(Path(a.fixture).read_text(encoding="utf-8"))["notices"] if a.fixture else fetch(query)
    tenders = [clean(n) for n in raw]
    before = len(tenders)
    tenders = dedupe(tenders)
    if before != len(tenders):
        print(f"Merged {before - len(tenders)} republished duplicates.")
    excluded = [t for t in tenders if not t.defence_buyer]
    if a.hide_civil:
        tenders = [t for t in tenders if t.defence_buyer]
    if a.military_only:
        tenders = [t for t in tenders if t.buyer_type == "military"]
    if a.open_only:
        tenders = [t for t in tenders if t.is_open]

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    mark_new(tenders, out / "seen.json")
    write_csv(tenders, out / "tenders.csv")
    write_html(tenders, out / "report.html", query, excluded)

    d = sum(t.defence_buyer for t in tenders)
    print(f"{len(tenders)} notices, {d} from defence/security buyers, "
          f"{sum(t.is_open for t in tenders)} open, {sum(t.new for t in tenders)} new.")
    print(f"Wrote {out/'report.html'} and {out/'tenders.csv'}")


if __name__ == "__main__":
    main()
