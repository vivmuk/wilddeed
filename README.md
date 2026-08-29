# WildDeed

**A naturalist's background check for any piece of land.**

Enter a US address, get a 7-page AI-written wildlife dossier in ~3 minutes: species observed near the parcel (GBIF occurrence records), conservation status (IUCN Red List), a plain-English naturalist's narrative (Venice LLM), and painted cover art — delivered as a branded PDF.

## Why

- Land buyers make five- and six-figure decisions with almost no ecological context. Listing copy says "abundant whitetail"; nobody checks.
- The data already exists and is free (GBIF, IUCN, Census geocoder). It's locked in scientific interfaces no buyer or broker can read.
- Primary buyer: recreational/hunting land brokers who want listing collateral that builds trust. Secondary: buyers doing due diligence.

## Repo layout

```
app/wilddeed.py     # The pipeline: geocode → GBIF → dedupe → IUCN → LLM narrative → cover art → PDF
site/               # The landing page (chaptered-editorial scrollcraft build, static, no build step)
  index.html
  scrollcraft.js    # scroll engine (unmodified)
  scrollcraft.css
  static/img/       # 7 Venice-generated watercolor plates (one style preamble)
  BRIEF.md          # design brief: grammar choice, feeling curve, signature move, device score
reports/            # sample dossiers generated for a real Wood County, WI parcel (not committed)
```

## The pipeline (app/wilddeed.py)

```
address
  → US Census Geocoder (free, keyless)
  → GBIF occurrence search (radius, 15-year window, quality filters)
  → species dedupe + flagship ranking (counts + game list + threatened)
  → IUCN status enrichment
  → stats: month histogram, year histogram, freshness
  → Venice LLM narrative from structured JSON (never raw tables; species names validated post-generation)
  → Venice image gen: naturalist cover art
  → WeasyPrint: branded PDF
```

Usage:

```bash
python3 -m venv venv && venv/bin/pip install requests weasyprint pillow
export VENICE_API_KEY=...
venv/bin/python app/wilddeed.py --address "W1215 County Road B, Babcock, WI 54413" --radius 8 --out reports/
```

Sample output (real parcel, 8 km radius, 2011–2026): 92,840 records, 518 species, Bald Eagle 42 records (last seen 2026), Whooping Crane 7 records (IUCN Endangered), White-tailed Deer 39, Wood Duck 28.

## The landing page

Chaptered-editorial grammar: the page reads like the dossier it sells. Title page on a painted survey plat, six chapters with hard-cut grounds (bone paper / forest / night / dusk), folio margin nav, and a colophon close. Signature move: a fixed **field ledger** rail that stamps each real figure (radius, species, eagle records, crane records, total observations) as its chapter passes — a totaled record of the argument by the last screen. All numbers on the page come from the actual sample dossier. No invented statistics.

Verified: scroll harness (desktop / mobile 390px / reduced-motion) — no dead scroll, no failed requests; contact-sheet review on all three.

## Honest limits

Every report carries: "Generated from public biodiversity records (GBIF) and IUCN conservation data. Not a biological survey; not a guarantee of species presence. For land-use decisions, consult a licensed biologist."

## Status

MVP complete and verified. Next: Stripe checkout, broker white-label tier, parcel boundary polygons (county GIS), occurrence map.
