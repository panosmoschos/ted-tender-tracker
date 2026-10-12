"""Offline tests against a real TED response saved on 9 Oct 2026.  Run: python -m pytest tests"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tracker  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "ted_sample.json"
NOTICES = json.loads(FIXTURE.read_text(encoding="utf-8"))["notices"]


def by_id(pub):
    return tracker.clean(next(n for n in NOTICES if n["publication-number"] == pub))


def test_query_has_cpv_titles_and_filters():
    q = tracker.build_query(["drones", "counter-drone"], date(2026, 9, 1), ["DEU", "NLD"], True)
    assert "classification-cpv IN (34711200 35613000)" in q
    assert 'notice-title ~ ("counter-drone")' in q
    assert "publication-date>=20260901" in q
    assert "buyer-country IN (DEU NLD)" in q
    assert "legal-basis IN (32009L0081)" in q


def test_defence_directive_marks_defence_buyer():
    t = by_id("689863-2026")  # Cyprus Police, UAS for border surveillance, under 2009/81
    assert t.defence_buyer and t.kind == "Open tender" and t.value_eur == 20_000_000
    assert "drones" in t.categories


def test_university_is_not_defence():
    assert not by_id("698831-2026").defence_buyer  # Politechnika Śląska buying one drone


def test_new_since_last_run(tmp_path):
    state = tmp_path / "seen.json"
    first = [tracker.clean(n) for n in NOTICES[:10]]
    tracker.mark_new(first, state)
    assert not any(t.new for t in first)  # first run: nothing is "new"
    second = [tracker.clean(n) for n in NOTICES[:12]]
    tracker.mark_new(second, state)
    assert [t.new for t in second].count(True) == 2


def test_end_to_end_with_fixture(tmp_path):
    tracker.main(["--fixture", str(FIXTURE), "--out", str(tmp_path)])
    assert (tmp_path / "report.html").read_text(encoding="utf-8").count("<tr") > 50
    assert (tmp_path / "tenders.csv").exists()


# Real buyers seen on TED (Jul–Oct 2026) with TED's own main-activity value and whether the
# notice used the defence directive. Expected label decided by hand. Add a row whenever
# you spot a buyer in the wrong bucket, then fix categories.py until this passes.
LABELLED = [
    # buyer, main-activity, defence directive?, expected
    ("Bundesamt für Ausrüstung, Informationstechnik und Nutzung der Bundeswehr", ["defence"], True, "military"),
    ("Ministerie van Defensie", [], True, "military"),
    ("Ministério da Defesa Nacional - Marinha", ["gen-pub"], False, "military"),  # TED tag is wrong
    ("Puolustusvoimat", [], True, "military"),
    ("Valsts aizsardzības loģistikas un iepirkumu centrs", ["defence"], False, "military"),
    ("Védelmi Beszerzési Ügynökség Zrt.", ["defence"], True, "military"),
    ("Jednostka Wojskowa nr 4026", ["defence"], False, "military"),
    ("UM 0929 Bucuresti", ["pub-os"], True, "military"),
    ("Riigi Kaitseinvesteeringute Keskus", ["defence"], True, "military"),
    ("FMV", ["defence"], False, "military"),
    ("Comando Brigata Paracadutisti \"Folgore\"", ["defence"], True, "military"),
    ("Lietuvos šaulių sąjunga (PV)", [], True, "military"),
    ("Polismyndigheten", ["pub-os"], True, "security"),
    ("Guarda Nacional Republicana", ["pub-os"], False, "security"),
    ("Jefatura de Asuntos Económicos de la Guardia Civil", ["pub-os"], False, "security"),
    ("Kustbevakningen", ["pub-os"], False, "security"),
    ("Ministerstvo vnitra", ["pub-os"], False, "security"),
    ("Išteklių agentūra prie Lietuvos Respublikos vidaus reikalų ministerijos", [], True, "security"),
    ("European Border and Coast Guard Agency (FRONTEX)", ["gen-pub"], False, "security"),
    ("Präsidium der Bayer. Bereitschaftspolizei", ["pub-os"], False, "security"),
    ("Berliner Feuerwehr", ["pub-os"], False, "civil"),
    ("Straż Miejska Miasta Krakowa", ["pub-os"], False, "civil"),
    ("Ministero della giustizia Dipartimento dell'amministrazione penitenziaria", ["pub-os"], False, "civil"),
    ("Inspectoratul General pentru Situatii de Urgenta", ["pub-os"], False, "civil"),
    ("Politechnika Śląska", ["education"], False, "civil"),
    ("Kauno technologijos universitetas (PV)", ["education"], False, "civil"),
    ("Hansel Oy", ["gen-pub"], False, "civil"),
    ("Daugavpils valstspilsētas pašvaldība", ["gen-pub"], False, "civil"),
    ("European Space Agency", ["gen-pub"], False, "civil"),
    ("N.V. Nederlandse Gasunie", ["gas-heat"], False, "civil"),
]


def test_buyer_classification_on_real_buyers():
    wrong = []
    for buyer, activity, directive, expected in LABELLED:
        got, why = tracker.classify_buyer(buyer, activity, ["32009L0081"] if directive else [])
        if got != expected:
            wrong.append(f"{buyer}: expected {expected}, got {got} ({why})")
    assert not wrong, "\n".join(wrong)


def test_dedupe_keeps_latest_republished_notice():
    a = by_id("689863-2026")
    b = tracker.Tender(**{**a.__dict__, "id": "x-2026", "published": "2026-10-12"})
    out = tracker.dedupe([a, b])
    assert len(out) == 1 and out[0].id == "x-2026"


def test_no_deadline_only_open_if_recent():
    t = by_id("689863-2026")  # open tender without a deadline field
    old = tracker.Tender(**{**t.__dict__, "published": "2020-01-01"})
    assert not old.is_open
