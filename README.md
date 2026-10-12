# TED defence tender tracker

European governments publish their tenders on TED, the EU's official tender journal. Defence tenders are spread across 27 countries, many languages and mixed in with universities buying one drone for a lab.

This script pulls the tenders that matter for drones, counter-drone systems and missiles. It separates real defence and security buyers from civil buyers and shows what's open to bid, who won what, and what's new since the last run.

## Run it

```bash
pip install -r requirements.txt
python tracker.py                                  # last 30 days: drones, counter-drone, missiles
python tracker.py --hide-civil --open-only         # only defence/security buyers you can still bid to
python tracker.py --days 90 --countries DEU,NLD,GRC
python tracker.py --categories drones,space --defence-only
```

Each run writes `output/report.html` (open it in a browser) and `output/tenders.csv` (opens in Excel). It also remembers what it has already seen, so the next run flags new notices.

## Options

| Flag | What it does |
|---|---|
| `--days N` | Look back N days (default 30) |
| `--categories` | Any of `drones`, `counter-drone`, `missiles`, `isr-ew`, `space` |
| `--countries` | Buyer countries as ISO3 codes, e.g. `DEU,NLD,CHE,GRC` |
| `--defence-only` | Only notices published under the EU defence directive 2009/81 |
| `--hide-civil` | Keep only defence and security buyers: ministries, armed forces, police, border guards |
| `--open-only` | Only tenders still open to bid |

## How it works

1. **Query.** It builds a TED expert-search query from CPV codes (the EU's product codes, e.g. `35613000` unmanned military aerial vehicles). Counter-drone has no code of its own, so it also searches titles for terms like "counter-drone", "C-UAS" and "Drohnenabwehr".
2. **Fetch.** It pages through the public TED v3 search API (`api.ted.europa.eu/v3/notices/search`, no key needed) and backs off when rate-limited.
3. **Classify.** A notice counts as defence when it is published under directive 2009/81, or when the buyer name matches a list of defence and security terms in about 15 languages.
4. **Report.** Open tenders are listed first (defence buyers first, then by deadline). Awards come next, followed by the top countries by defence value.

Categories, CPV codes and buyer terms are all in `categories.py`.

## Tests

```bash
pip install pytest
python -m pytest tests
```

The tests run offline against a real TED response saved on 9 Oct 2026 (`tests/fixtures/ted_sample.json`, 114 notices).
