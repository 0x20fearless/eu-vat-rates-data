#!/usr/bin/env python3
"""
Update EU VAT rates from European Commission TEDB SOAP web service.

Official source: https://ec.europa.eu/taxation_customs/tedb/ws/VatRetrievalService.wsdl
Documentation:  https://taxation-customs.ec.europa.eu/system/files/2021-06/soap_webservice_documentation.pdf

Usage:
    python3 scripts/update.py [--dry-run]

Options:
    --dry-run   Show diff without writing to file

Dependencies:
    pip install requests
"""

import json
import sys
import datetime
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    sys.exit("Error: 'requests' not installed. Run: pip install requests")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# EU member states use ISO 3166-1 alpha-2 codes (EL for Greece per EU convention)
EU_MEMBER_STATES = [
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL",
    "ES", "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU",
    "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK",
]

# EU uses "EL" for Greece; we normalise to ISO 3166-1 alpha-2 in the output
TEDB_TO_ISO: dict[str, str] = {"EL": "GR"}

COUNTRY_NAMES: dict[str, str] = {
    "AT": "Austria",      "BE": "Belgium",       "BG": "Bulgaria",
    "CY": "Cyprus",       "CZ": "Czech Republic", "DE": "Germany",
    "DK": "Denmark",      "EE": "Estonia",        "GR": "Greece",
    "ES": "Spain",        "FI": "Finland",        "FR": "France",
    "HR": "Croatia",      "HU": "Hungary",        "IE": "Ireland",
    "IT": "Italy",        "LT": "Lithuania",      "LU": "Luxembourg",
    "LV": "Latvia",       "MT": "Malta",          "NL": "Netherlands",
    "PL": "Poland",       "PT": "Portugal",       "RO": "Romania",
    "SE": "Sweden",       "SI": "Slovenia",       "SK": "Slovakia",
}

# EU-27 countries that do not use EUR as their currency
CURRENCY: dict[str, str] = {
    "BG": "BGN", "CZ": "CZK", "DK": "DKK", "HU": "HUF",
    "PL": "PLN", "RO": "RON", "SE": "SEK",
}

# Non-EU European countries — rates maintained manually.
# Sources: official tax authority websites, Tax Foundation, PWC Tax Summaries (2026).
NON_EU_COUNTRIES: dict[str, dict] = {
    "AD": {"country": "Andorra",              "currency": "EUR", "standard": 4.5,  "reduced": [2.5],       "super_reduced": 1.0,  "parking": None},
    "AL": {"country": "Albania",              "currency": "ALL", "standard": 20.0, "reduced": [6.0, 10.0], "super_reduced": None, "parking": None},
    "BA": {"country": "Bosnia and Herzegovina","currency": "BAM","standard": 17.0, "reduced": [],           "super_reduced": None, "parking": None},
    "CH": {"country": "Switzerland",          "currency": "CHF", "standard": 8.1,  "reduced": [2.6, 3.8],  "super_reduced": None, "parking": None},
    "GB": {"country": "United Kingdom",       "currency": "GBP", "standard": 20.0, "reduced": [5.0],       "super_reduced": None, "parking": None},
    "GE": {"country": "Georgia",              "currency": "GEL", "standard": 18.0, "reduced": [],           "super_reduced": None, "parking": None},
    "IS": {"country": "Iceland",              "currency": "ISK", "standard": 24.0, "reduced": [11.0],      "super_reduced": None, "parking": None},
    "LI": {"country": "Liechtenstein",        "currency": "CHF", "standard": 8.1,  "reduced": [2.6, 3.8],  "super_reduced": None, "parking": None},
    "MC": {"country": "Monaco",               "currency": "EUR", "standard": 20.0, "reduced": [5.5, 10.0], "super_reduced": 2.1,  "parking": None},
    "MD": {"country": "Moldova",              "currency": "MDL", "standard": 20.0, "reduced": [8.0],       "super_reduced": None, "parking": None},
    "ME": {"country": "Montenegro",           "currency": "EUR", "standard": 21.0, "reduced": [7.0, 15.0], "super_reduced": None, "parking": None},
    "MK": {"country": "North Macedonia",      "currency": "MKD", "standard": 18.0, "reduced": [5.0, 10.0], "super_reduced": None, "parking": None},
    "NO": {"country": "Norway",               "currency": "NOK", "standard": 25.0, "reduced": [12.0, 15.0],"super_reduced": None, "parking": None},
    "RS": {"country": "Serbia",               "currency": "RSD", "standard": 20.0, "reduced": [10.0],      "super_reduced": None, "parking": None},
    "TR": {"country": "Turkey",               "currency": "TRY", "standard": 20.0, "reduced": [1.0, 10.0], "super_reduced": None, "parking": None},
    "UA": {"country": "Ukraine",              "currency": "UAH", "standard": 20.0, "reduced": [7.0, 14.0], "super_reduced": None, "parking": None},
    "XK": {"country": "Kosovo",               "currency": "EUR", "standard": 18.0, "reduced": [8.0],       "super_reduced": None, "parking": None},
}

DATA_FILE = Path(__file__).parent.parent / "data" / "eu-vat-rates-data.json"

# EC TEDB SOAP service (HTTP per WSDL, redirects to HTTPS)
TEDB_ENDPOINT = "https://ec.europa.eu/taxation_customs/tedb/ws/"
TEDB_NS_MSG   = "urn:ec.europa.eu:taxud:tedb:services:v1:IVatRetrievalService"
TEDB_NS_TYPES = "urn:ec.europa.eu:taxud:tedb:services:v1:IVatRetrievalService:types"
TEDB_SOAP_ACTION = "urn:ec.europa.eu:taxud:tedb:services:v1:VatRetrievalService/RetrieveVatRates"

# rateValueTypeEnum values to skip — these are not real positive VAT rates
SKIP_RATE_TYPES = {"EXEMPTED", "OUT_OF_SCOPE", "NOT_APPLICABLE"}


# ---------------------------------------------------------------------------
# SOAP helpers
# ---------------------------------------------------------------------------

def _build_soap_body(member_states: list[str], situation_on: str) -> bytes:
    states_xml = "\n".join(
        f"        <types:isoCode>{s}</types:isoCode>" for s in member_states
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:v1="{TEDB_NS_MSG}"
    xmlns:types="{TEDB_NS_TYPES}">
  <soapenv:Body>
    <v1:retrieveVatRatesReqMsg>
      <types:memberStates>
{states_xml}
      </types:memberStates>
      <types:situationOn>{situation_on}</types:situationOn>
    </v1:retrieveVatRatesReqMsg>
  </soapenv:Body>
</soapenv:Envelope>"""
    return xml.encode("utf-8")


def _parse_soap_response(xml_bytes: bytes) -> Optional[dict[str, dict]]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        print(f"  XML parse error: {exc}", file=sys.stderr)
        return None

    # Accumulate unique (rate_value_type, rate_value) per country
    # Structure: country_code → { "standard": float, "reduced": set, "super_reduced": set, "parking": set }
    raw: dict[str, dict] = {}

    for el in root.iter():
        local_tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if local_tag != "vatRateResults":
            continue

        country_code: Optional[str] = None
        outer_type:   Optional[str] = None  # STANDARD | REDUCED
        rv_type:      Optional[str] = None  # DEFAULT | REDUCED_RATE | SUPER_REDUCED_RATE | PARKING_RATE | …
        rv_value:     Optional[float] = None

        for child in el:
            ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if ctag == "memberState":
                raw_code = (child.text or "").strip()
                country_code = TEDB_TO_ISO.get(raw_code, raw_code)
            elif ctag == "type":
                outer_type = (child.text or "").strip()
            elif ctag == "rate":
                for gc in child:
                    gctag = gc.tag.split("}")[-1] if "}" in gc.tag else gc.tag
                    if gctag == "type":
                        rv_type = (gc.text or "").strip()
                    elif gctag == "value":
                        try:
                            rv_value = float((gc.text or "").strip())
                        except ValueError:
                            pass

        if not country_code or not outer_type or rv_type is None:
            continue
        if rv_type in SKIP_RATE_TYPES:
            continue
        if rv_value is None or rv_value <= 0:
            continue

        entry = raw.setdefault(country_code, {
            "standard":     set(),
            "reduced":      set(),
            "super_reduced": set(),
            "parking":      set(),
        })

        if outer_type == "STANDARD" and rv_type == "DEFAULT":
            entry["standard"].add(rv_value)
        elif outer_type == "REDUCED":
            if rv_type == "REDUCED_RATE":
                entry["reduced"].add(rv_value)
            elif rv_type == "SUPER_REDUCED_RATE":
                entry["super_reduced"].add(rv_value)
            elif rv_type == "PARKING_RATE":
                entry["parking"].add(rv_value)

    if not raw:
        return None

    # Convert sets → canonical scalars / lists
    result: dict[str, dict] = {}
    for code, entry in raw.items():
        std_set = entry["standard"]
        result[code] = {
            # Standard rate: should be a single value per country
            "standard": max(std_set) if std_set else None,
            # Reduced rates: list, sorted ascending
            "reduced": sorted(entry["reduced"]),
            # Super-reduced: smallest value (some countries use multiple for special territories)
            "super_reduced": min(entry["super_reduced"]) if entry["super_reduced"] else None,
            # Parking: smallest value
            "parking": min(entry["parking"]) if entry["parking"] else None,
        }

    return result


def fetch_from_tedb() -> Optional[dict[str, dict]]:
    """Fetch current VAT rates via EC TEDB SOAP web service (official EU source)."""
    today = datetime.date.today().isoformat()
    body = _build_soap_body(EU_MEMBER_STATES, today)
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction":   TEDB_SOAP_ACTION,
    }
    print("  Requesting EC TEDB SOAP service…")
    try:
        resp = requests.post(TEDB_ENDPOINT, data=body, headers=headers, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  TEDB SOAP failed: {exc}", file=sys.stderr)
        return None

    result = _parse_soap_response(resp.content)
    if result:
        print(f"  Got rates for {len(result)} EU member states from TEDB.")
    else:
        print("  TEDB response parsed but yielded no rates.", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# Build final dataset
# ---------------------------------------------------------------------------

def build_dataset(eu_rates: dict[str, dict]) -> dict:
    today = datetime.date.today().isoformat()
    rates_out: dict[str, dict] = {}

    # EU-27: rates from TEDB
    for code_tedb in EU_MEMBER_STATES:
        code = TEDB_TO_ISO.get(code_tedb, code_tedb)
        entry = eu_rates.get(code)
        if not entry:
            print(f"  Warning: no data for {code} — skipped.", file=sys.stderr)
            continue
        rates_out[code] = {
            "country":      COUNTRY_NAMES.get(code, code),
            "currency":     CURRENCY.get(code, "EUR"),
            "eu_member":    True,
            "standard":     entry.get("standard"),
            "reduced":      entry.get("reduced", []),
            "super_reduced": entry.get("super_reduced"),
            "parking":      entry.get("parking"),
        }

    # Non-EU European countries: hardcoded, updated manually
    for code, entry in NON_EU_COUNTRIES.items():
        rates_out[code] = {**entry, "eu_member": False}

    return {
        "version": today,
        "source":  "European Commission TEDB",
        "url":     "https://taxation-customs.ec.europa.eu/tedb/vatRates.html",
        "rates":   dict(sorted(rates_out.items())),
    }


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------

def _diff(old: object, new: object, path: str, lines: list[str]) -> None:
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            _diff(old.get(key), new.get(key), f"{path}.{key}", lines)
    else:
        if old != new:
            lines.append(f"  ~ {path}: {old!r} → {new!r}")


def compute_diff(old_dataset: dict, new_dataset: dict) -> list[str]:
    lines: list[str] = []
    _diff(
        old_dataset.get("rates", {}),
        new_dataset.get("rates", {}),
        "rates",
        lines,
    )
    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _set_github_output(key: str, value: str) -> None:
    """Write a key=value pair to $GITHUB_OUTPUT if running in GitHub Actions."""
    import os
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a") as f:
            f.write(f"{key}={value}\n")


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    print("eu-vat-rates updater")
    print("=" * 40)

    eu_rates = fetch_from_tedb()
    if eu_rates is None:
        print(
            "\nError: EC TEDB SOAP service is unavailable. "
            "Check connectivity and retry.\n"
            "Endpoint: " + TEDB_ENDPOINT,
            file=sys.stderr,
        )
        _set_github_output("rates_changed", "false")
        return 1

    new_dataset = build_dataset(eu_rates)

    # Load existing data for comparison
    old_dataset: dict = {}
    if DATA_FILE.exists():
        try:
            old_dataset = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  Warning: could not read existing file: {exc}", file=sys.stderr)

    # Check if actual VAT rates changed (ignoring version date)
    rate_diff = compute_diff(old_dataset, new_dataset)
    rates_changed = bool(rate_diff)

    if rate_diff:
        print(f"\nRate changes ({len(rate_diff)} fields):")
        for line in rate_diff:
            print(line)
    else:
        print(f"\nNo rate changes. Updating version date: "
              f"{old_dataset.get('version', 'n/a')} → {new_dataset['version']}")

    _set_github_output("rates_changed", "true" if rates_changed else "false")

    if dry_run:
        print("\n[dry-run] File not updated.")
        return 0

    # Always write the file — version date is always today
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(new_dataset, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Updated: {DATA_FILE}  (version: {new_dataset['version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
