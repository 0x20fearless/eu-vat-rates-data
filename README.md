# eu-vat-rates-data

[![Last updated](https://img.shields.io/github/last-commit/vatnode/eu-vat-rates-data?path=data%2Feu-vat-rates-data.json&label=last%20updated)](https://github.com/vatnode/eu-vat-rates-data/commits/main/data/eu-vat-rates-data.json)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Canonical data source for EU VAT rates — all **27 EU member states** plus the **United Kingdom**, sourced from the [European Commission TEDB](https://taxation-customs.ec.europa.eu/tedb/vatRates.html). Checked daily, committed automatically when rates change.

This repository contains **only the data and the update script**. Language-specific packages are published separately:

| Language | Package | Install |
|---|---|---|
| JavaScript / TypeScript | [npm](https://www.npmjs.com/package/eu-vat-rates-data) | `npm install eu-vat-rates-data` |
| Python | [PyPI](https://pypi.org/project/eu-vat-rates-data/) | `pip install eu-vat-rates-data` |
| PHP | [Packagist](https://packagist.org/packages/vatnode/eu-vat-rates-data) | `composer require vatnode/eu-vat-rates-data` |
| Go | [pkg.go.dev](https://pkg.go.dev/github.com/vatnode/eu-vat-rates-data-go) | `go get github.com/vatnode/eu-vat-rates-data-go` |
| Ruby | [RubyGems](https://rubygems.org/gems/eu_vat_rates_data) | `gem install eu_vat_rates_data` |

---

## Direct JSON access

No package needed — use the JSON directly via CDN:

```
# jsDelivr CDN (cached):
https://cdn.jsdelivr.net/gh/vatnode/eu-vat-rates-data@main/data/eu-vat-rates-data.json

# Raw GitHub (always latest commit):
https://raw.githubusercontent.com/vatnode/eu-vat-rates-data/main/data/eu-vat-rates-data.json
```

```js
const res = await fetch(
  'https://cdn.jsdelivr.net/gh/vatnode/eu-vat-rates-data@main/data/eu-vat-rates-data.json'
)
const { rates } = await res.json()
console.log(rates.DE.standard) // 19
```

---

## Data structure

\`\`\`ts
interface VatRate {
  country:       string        // "Finland"
  currency:      string        // "EUR" (or "DKK", "GBP", …)
  standard:      number        // 25.5
  reduced:       number[]      // [10, 13.5] — sorted ascending
  super_reduced: number | null // null when not applicable
  parking:       number | null // null when not applicable
}
\`\`\`

### Example JSON entry

\`\`\`json
{
  "version": "2026-02-25",
  "source": "European Commission TEDB",
  "url": "https://taxation-customs.ec.europa.eu/tedb/vatRates.html",
  "rates": {
    "FI": {
      "country": "Finland",
      "currency": "EUR",
      "standard": 25.5,
      "reduced": [10, 13.5],
      "super_reduced": null,
      "parking": null
    }
  }
}
\`\`\`

---

## Update frequency

- Fetched from EC TEDB SOAP API: **daily at 07:00 UTC**
- Committed on every run (version date always updated)
- Full audit trail: \`git log -- data/eu-vat-rates-data.json\`

To manually trigger: [Actions → Run workflow](https://github.com/vatnode/eu-vat-rates-data/actions/workflows/update.yml)

To run locally:

\`\`\`bash
git clone https://github.com/vatnode/eu-vat-rates-data.git
pip install requests
python3 scripts/update.py
\`\`\`

---

## Covered countries

EU-27 member states + United Kingdom (28 countries total):

\`AT\` \`BE\` \`BG\` \`CY\` \`CZ\` \`DE\` \`DK\` \`EE\` \`ES\` \`FI\` \`FR\` \`GB\` \`GR\` \`HR\` \`HU\` \`IE\` \`IT\` \`LT\` \`LU\` \`LV\` \`MT\` \`NL\` \`PL\` \`PT\` \`RO\` \`SE\` \`SI\` \`SK\`

---

## Need to validate VAT numbers?

This repository provides **VAT rates** only. If you also need to **validate EU VAT numbers** against the official VIES database, check out [vatnode.dev](https://vatnode.dev) — a simple REST API with a free tier.

---

## License

MIT

If you find this useful, a ⭐ on GitHub is appreciated.
