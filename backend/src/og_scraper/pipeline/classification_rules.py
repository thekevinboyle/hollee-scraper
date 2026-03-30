"""
Classification rules for Oil & Gas document types.

Keyword weights:
  3 = Strong signal (definitive phrases like "production report", "permit to drill")
  2 = Medium signal (supporting phrases like "proposed total depth", "barrels produced")
  1 = Weak signal (general terms like "drilling", "spud", "injected")
"""

# --- Weighted Keyword Dictionaries ---

DOCUMENT_PATTERNS: dict[str, dict[str, dict[str, int]]] = {
    "well_permit": {
        "keywords": {
            # Strong signals (weight 3)
            "application to drill": 3,
            "permit to drill": 3,
            "drilling permit": 3,
            "intent to drill": 3,
            "application for permit": 3,
            "notice of intention to drill": 3,
            # Medium signals (weight 2)
            "proposed total depth": 2,
            "proposed casing program": 2,
            "anticipated spud date": 2,
            "surface location": 2,
            "bottom hole location": 2,
            "proposed formation": 2,
            "drilling bond": 2,
            # Weak signals (weight 1)
            "drilling": 1,
            "spud": 1,
            "casing": 1,
        },
    },
    "production_report": {
        "keywords": {
            # Strong signals (weight 3)
            "production report": 3,
            "monthly production": 3,
            "annual production": 3,
            "production summary": 3,
            # Medium signals (weight 2)
            "oil production": 2,
            "gas production": 2,
            "water production": 2,
            "barrels produced": 2,
            "mcf produced": 2,
            "days produced": 2,
            "producing days": 2,
            "disposition": 2,
            "lease production": 2,
            "well production": 2,
            "production volume": 2,
            # Weak signals (weight 1)
            "sold": 1,
            "flared": 1,
            "vented": 1,
            "injected": 1,
        },
    },
    "completion_report": {
        "keywords": {
            # Strong signals (weight 3)
            "completion report": 3,
            "well completion": 3,
            "recompletion report": 3,
            "completed interval": 3,
            # Medium signals (weight 2)
            "perforation interval": 2,
            "initial production": 2,
            "frac stages": 2,
            "proppant": 2,
            "stimulation": 2,
            "lateral length": 2,
            "total depth": 2,
            "completion date": 2,
            "ip rate": 2,
            "initial potential": 2,
            "back pressure test": 2,
            # Weak signals (weight 1)
            "perforated": 1,
            "cement": 1,
            "tubing": 1,
        },
    },
    "plugging_report": {
        "keywords": {
            # Strong signals (weight 3)
            "plugging report": 3,
            "plug and abandon": 3,
            "plugging record": 3,
            "plugged and abandoned": 3,
            "well plugging": 3,
            # Medium signals (weight 2)
            "cement plug": 2,
            "plug placed": 2,
            "surface restoration": 2,
            "casing left in hole": 2,
            "plug depth": 2,
            # Weak signals (weight 1)
            "abandoned": 1,
            "plugged": 1,
        },
    },
    "spacing_order": {
        "keywords": {
            # Strong signals (weight 3)
            "spacing order": 3,
            "pooling order": 3,
            "drilling unit": 3,
            "forced pooling": 3,
            "compulsory pooling": 3,
            "drilling and spacing unit": 3,
            # Medium signals (weight 2)
            "spacing exception": 2,
            "rule 37": 2,
            "rule 38": 2,
            "drilling unit order": 2,
            "unit boundaries": 2,
            "hearing examiner": 2,
            # Weak signals (weight 1)
            "spacing": 1,
            "pooling": 1,
            "unit": 1,
        },
    },
    "inspection_record": {
        "keywords": {
            # Strong signals (weight 3)
            "inspection report": 3,
            "field inspection": 3,
            "well inspection": 3,
            "compliance inspection": 3,
            "site inspection": 3,
            # Medium signals (weight 2)
            "inspection findings": 2,
            "violation": 2,
            "inspector": 2,
            "compliance status": 2,
            "inspection date": 2,
            "corrective action": 2,
            # Weak signals (weight 1)
            "inspected": 1,
            "compliant": 1,
            "non-compliant": 1,
        },
    },
    "incident_report": {
        "keywords": {
            # Strong signals (weight 3)
            "incident report": 3,
            "spill report": 3,
            "release notification": 3,
            "blowout": 3,
            "h2s release": 3,
            # Medium signals (weight 2)
            "environmental release": 2,
            "volume released": 2,
            "volume recovered": 2,
            "corrective action": 2,
            "spill": 2,
            "reportable quantity": 2,
            # Weak signals (weight 1)
            "leak": 1,
            "release": 1,
            "incident": 1,
        },
    },
}


# --- State-Specific Form Number Patterns ---
# Detecting a form number is nearly 100% accurate for classification.

FORM_PATTERNS: dict[str, dict[str, str]] = {
    # Texas Railroad Commission forms
    "TX_W-1": {
        "pattern": r"\bform\s*w[\s-]*1\b|\bw[\s-]*1\s*(?:form|application)\b",
        "type": "well_permit",
        "state": "TX",
    },
    "TX_W-2": {
        "pattern": r"\bform\s*w[\s-]*2\b|\bw[\s-]*2\s*(?:form|completion|report)\b",
        "type": "completion_report",
        "state": "TX",
    },
    "TX_G-1": {
        "pattern": r"\bform\s*g[\s-]*1\b|\bg[\s-]*1\s*(?:form|completion|report|gas)\b",
        "type": "completion_report",
        "state": "TX",
    },
    "TX_W-3": {
        "pattern": r"\bform\s*w[\s-]*3\b|\bw[\s-]*3\s*(?:form|plugging)\b",
        "type": "plugging_report",
        "state": "TX",
    },
    "TX_PR": {
        "pattern": r"\bform\s*pr\b|\bpr\s*(?:form|production)\b",
        "type": "production_report",
        "state": "TX",
    },
    "TX_W-14": {
        "pattern": r"\bform\s*w[\s-]*14\b|\bw[\s-]*14\b",
        "type": "plugging_report",
        "state": "TX",
    },
    "TX_H-10": {
        "pattern": r"\bform\s*h[\s-]*10\b|\bh[\s-]*10\b",
        "type": "incident_report",
        "state": "TX",
    },
    # Oklahoma Corporation Commission
    "OK_1002A": {
        "pattern": r"\b(?:form\s*)?1002[\s-]*a\b",
        "type": "well_permit",
        "state": "OK",
    },
    "OK_1002C": {
        "pattern": r"\b(?:form\s*)?1002[\s-]*c\b",
        "type": "completion_report",
        "state": "OK",
    },
    "OK_1012D": {
        "pattern": r"\b(?:form\s*)?1012[\s-]*d\b",
        "type": "production_report",
        "state": "OK",
    },
    "OK_1003": {
        "pattern": r"\b(?:form\s*)?1003\b.*(?:plug|abandon)",
        "type": "plugging_report",
        "state": "OK",
    },
    # Colorado ECMC/COGCC
    "CO_Form2": {
        "pattern": r"\bform\s*2\b.*(?:permit|drill)",
        "type": "well_permit",
        "state": "CO",
    },
    "CO_Form5": {
        "pattern": r"\bform\s*5\b.*(?:complet|interval)",
        "type": "completion_report",
        "state": "CO",
    },
    "CO_Form5A": {
        "pattern": r"\bform\s*5[\s-]*a\b",
        "type": "completion_report",
        "state": "CO",
    },
    "CO_Form6": {
        "pattern": r"\bform\s*6\b.*(?:plug|abandon)",
        "type": "plugging_report",
        "state": "CO",
    },
    "CO_Form7": {
        "pattern": r"\bform\s*7\b.*(?:production|operator)",
        "type": "production_report",
        "state": "CO",
    },
    # North Dakota DMR
    "ND_Form1": {
        "pattern": r"\bform\s*1\b.*(?:permit|drill).*(?:north\s*dakota|nd|dmr)",
        "type": "well_permit",
        "state": "ND",
    },
    "ND_Form6": {
        "pattern": r"\bform\s*6\b.*(?:complet).*(?:north\s*dakota|nd|dmr)",
        "type": "completion_report",
        "state": "ND",
    },
    "ND_Form4": {
        "pattern": r"\bform\s*4\b.*(?:sundry|plugging).*(?:north\s*dakota|nd|dmr)",
        "type": "plugging_report",
        "state": "ND",
    },
    # New Mexico OCD
    "NM_C-101": {
        "pattern": r"\bc[\s-]*101\b.*(?:permit|drill)",
        "type": "well_permit",
        "state": "NM",
    },
    "NM_C-105": {
        "pattern": r"\bc[\s-]*105\b.*(?:complet)",
        "type": "completion_report",
        "state": "NM",
    },
    "NM_C-103": {
        "pattern": r"\bc[\s-]*103\b.*(?:plug|abandon)",
        "type": "plugging_report",
        "state": "NM",
    },
    "NM_C-115": {
        "pattern": r"\bc[\s-]*115\b.*(?:production|monthly)",
        "type": "production_report",
        "state": "NM",
    },
    # Wyoming WOGCC
    "WY_APD": {
        "pattern": r"\b(?:application\s*for\s*permit\s*to\s*drill|apd)\b.*(?:wyoming|wogcc)",
        "type": "well_permit",
        "state": "WY",
    },
    "WY_Sundry": {
        "pattern": r"\bsundry\s*notice\b.*(?:wyoming|wogcc)",
        "type": "plugging_report",
        "state": "WY",
    },
    # Pennsylvania DEP
    "PA_5500": {
        "pattern": r"\b(?:form\s*)?5500[\s-]*pm\b",
        "type": "well_permit",
        "state": "PA",
    },
    "PA_Completion": {
        "pattern": r"\bwell\s*completion\s*report\b.*(?:pennsylvania|pa\s*dep)",
        "type": "completion_report",
        "state": "PA",
    },
    # Federal EIA
    "EIA_914": {
        "pattern": r"\beia[\s-]*914\b|\bform\s*eia[\s-]*914\b",
        "type": "production_report",
        "state": "FED",
    },
}


# --- State Agency Patterns (for header/footer analysis) ---

AGENCY_PATTERNS: dict[str, str] = {
    "TX": r"railroad commission of texas|rrc.*texas|texas\s+railroad",
    "OK": r"corporation commission.*oklahoma|occ|oklahoma\s+corporation",
    "ND": r"department of mineral resources|north dakota.*dmr|industrial commission.*north dakota",
    "CO": r"colorado.*oil.*gas|ecmc|cogcc|colorado\s+energy.*(?:mineral|carbon\s+management)",
    "NM": r"oil conservation division|new mexico.*ocd|energy.*minerals.*natural resources.*nm",
    "WY": r"oil.*gas conservation commission|wogcc|wyoming\s+oil",
    "LA": r"department of natural resources|sonris|louisiana.*dnr|conservation.*louisiana",
    "PA": r"department of environmental protection|pa.*dep|pennsylvania.*dep",
    "CA": r"geologic energy management|calgem|division of oil.*gas.*geothermal|california.*doggr",
    "AK": r"alaska oil.*gas conservation commission|aogcc|alaska.*oil.*gas",
}
