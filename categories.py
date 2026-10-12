"""What we track on TED, and how we tell a defence buyer from a university.

Every CPV code here was checked against the TED v3 search API (Oct 2026).
CPV matching on TED is hierarchical: 35600000 also returns 35611500 etc.
"""

CATEGORIES = {
    "drones": {
        "label": "Drones / UAS",
        "cpv": ["34711200", "35613000"],  # non-piloted aircraft, unmanned military aerial vehicles
        "title_terms": [],
    },
    "counter-drone": {
        "label": "Counter-drone (C-UAS)",
        "cpv": [],  # no CPV exists for C-UAS, so we search titles
        "title_terms": ["counter-drone", "anti-drone", "C-UAS", "counter-UAS", "drone detection",
                        "Drohnenabwehr", "antidrone", "lutte anti-drones"],
    },
    "missiles": {
        "label": "Missiles, munitions, military aircraft",
        "cpv": ["35600000", "35610000", "35330000"],
        "title_terms": [],
    },
    "isr-ew": {
        "label": "ISR, C4I, electronic warfare",
        "cpv": ["35710000", "35720000", "35730000"],
        "title_terms": [],
    },
    "space": {
        "label": "Space (military + navigation satellites)",
        "cpv": ["35630000", "35640000"],
        "title_terms": ["satellite", "space situational awareness", "space surveillance"],
    },
}

DEFAULT_CATEGORIES = ["drones", "counter-drone", "missiles"]

# Directive 2009/81/EC = the EU defence and security procurement directive.
# If a notice is published under it, the buyer is buying defence/security kit.
DEFENCE_LEGAL_BASIS = "32009L0081"

# How a buyer is classified (see classify_buyer in tracker.py), in this order:
#   1. name looks like fire brigade / city guard / prison / civil protection -> civil
#   2. name looks like police / border / interior                          -> security
#   3. name looks like ministry of defence / armed forces                  -> military
#   4. TED's own "main-activity" field: defence -> military, pub-os -> security
#   5. published under the defence directive 2009/81                       -> military
#   6. anything else                                                        -> civil
# Names come first because TED's main-activity field is sometimes empty or wrong
# (e.g. Portugal's Ministério da Defesa Nacional tagged "gen-pub").

MILITARY_BUYER_TERMS = [
    "defence", "defense", "armed forces", "army", "navy", "air force",
    "bundeswehr", "baainbw", "verteidigung", "bundesamt für ausrüstung", "bwi gmbh",  # DE / AT
    "défense", "armée",                                  # FR / BE
    "defensie",                                          # NL
    "difesa", "esercito", "aeronautica militare", "comando brigata",  # IT
    "defensa", "armada", "ejército", "fuerza aérea", "mando de apoyo logístico",  # ES
    "defesa", "força aérea", "estado-maior", "estado maior",  # PT
    "obrany", "obrony", "wojsk", "agencja uzbrojenia",   # CZ / PL
    "kaitse", "puolustus", "försvar", "forsvar", "fmv",  # EE / FI / SE / DK-NO
    "militar", "unitatea militara", "um 0",              # RO
    "krašto apsaugos", "šaulių", "aizsardzības",          # LT / LV
    "obramb", "honvéd", "védelmi",                       # SI / HU
    "εθνικής άμυνας", "άμυνας", "γεετα",                 # GR
]

SECURITY_BUYER_TERMS = [
    "police", "polizei", "policja", "policji", "politsei", "polícia", "policía", "polizia",
    "politie", "poliției", "polis", "policijos", "rendőrség", "αστυνομία",
    "gendarm", "жандармерия", "guardia civil", "guarda nacional republicana",
    "guardia di finanza", "carabinieri", "border", "frontex", "coast guard", "piirivalve",
    "kustbevakning", "ministerstvo vnitra", "ministerstvo vnútra", "ministry of interior",
    "ministerium des innern", "intérieur", "dell'interno", "vidaus reikal", "unutarnjih poslova",
]

# Buyers TED often tags as "public order and safety" that don't buy defence kit.
CIVIL_OVERRIDE_TERMS = [
    "feuerwehr", "fire", "pompier", "bomberos", "pożar", "пожарна", "straż miejska",
    "situatii de urgenta", "proteção civil", "protección civil", "penitenci", "giustizia",
]

# Kept for backwards compatibility.
DEFENCE_BUYER_TERMS = MILITARY_BUYER_TERMS + SECURITY_BUYER_TERMS

# Notice types: cn = open call for tenders (can still bid), can = contract award (who won),
# pin = prior information (coming soon). Prefixes are enough.
NOTICE_KIND = {
    "cn": "Open tender",
    "can": "Award",
    "pin": "Coming soon",
    "veat": "Award (no tender)",
}
