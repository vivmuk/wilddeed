# WildDeed v2 — Build Brief

**Self-authored, not interviewed.** Directive from Vivek: "The website doesn't look that great. It's not interactive. I want to show the dossier generation right in the front. It should be the first thing the users do. Also, use a different color combination." Prior brief (v1, chaptered editorial) + PRD serve as background. Autonomous run per user preference.

## What this is
A naturalist's background check for any piece of US land. The API is real and deployed (wilddeed-production.up.railway.app): `/api/species` returns a live GBIF species preview in ~2s; `/api/dossiers` generates the full 7-page PDF in ~90s. The page IS the product surface.

## The one sentence the page must install
> "Type an address and watch the real wildlife record come back. This thing already works."

## Visitor's next action
Run a lookup on their own address. One label everywhere: **Run lookup** (free preview) → **Generate dossier** (the paid artifact).

## Grammar: Live surface (2.3)
Chosen from the eight. Why: the user explicitly asked for the generation to be the first thing, and it can be real. The other seven lost: chaptered editorial (v1's grammar; the user found the result not interactive), filmic one-shot (a marketing film about a data product, when the demo can literally run), continuous world (no journey geography), typographic poster (we have real plates but the ask is operation, not manifesto), gallery (not a range of objects), split stage (not a two-sided argument), rhythmic cutlist (energy grammar, opposite of an instrument).

**Grammar obligations honored:** app chrome replaces marketing nav; the hero is the surface already in a state (a lookup already running on arrival); the close is an actual input (the order form); copy lives in the surface's idiom (labels, status lines, empty states); no scrims, no full-bleed photography, no kinetic headline stacks, no 6rem display headings. Bans honored: no scrub, no kinetic, no spotlight, drift ≤ 2 stops (hard per-section grounds instead).

**Honesty rule:** the console runs real markup against the real deployed API. Nothing is a painted surface. When the API is unreachable the console shows a real error state, not a fake.

## Signature move
**The pipeline replay playhead.** Scroll drives a replay of the actual production run of dossier `0e5ad70c` (Babcock WI, 2026-08-29): the real log lines type out stage by stage (geocode → GBIF 29,371 records → IUCN enrich → narrative → cover art → PDF), each stage stamping its **real measured duration** onto a fixed trace rail at the bottom edge. Scroll is the playhead over the run; by the close the rail is the complete recipe of a dossier, and it doubles as navigation. Real timings, real log text, run ID on its face.

## Feeling curve (written before acts)
1. Competence — the console is already mid-run on arrival; results stream in before you touch anything
2. Curiosity — your turn: type your own address, the surface answers with real species in seconds
3. Clarity — the replay: scroll walks the actual pipeline, log lines and durations, nothing hidden
4. Weight — the plates rail: what 518 species looks like as a field guide (PEAK: the crane, endangered, on the parcel)
5. Confidence — the method and the limits, stated plainly, sourced
6. Readiness — the order input: address in, job queued, real job ID returned

Peak: "I scrolled through the actual making of a dossier, log lines and all, and then the crane plate showed up in the data."

Tell-someone: "it's the site where you type your land's address and it runs a real wildlife lookup while you watch, then shows you the log of how the dossier gets made."

## Device score (live surface: pin, count, pointer, --sc-p CSS; NO scrub/kinetic/spotlight)
| Beat | Device | Why |
|---|---|---|
| Console (hero) | pin + live fetch | The surface holds while the real lookup fills it; state advances under the reader's eye |
| Your turn | flow + live fetch | A second input, lower commitment, same surface idiom |
| Pipeline replay | pin + --sc-p driven log + count on real timings | Scroll as playhead over the run; the argument is the process itself |
| Field guide (peak) | pan rail + reveal on the crane + tilt | The plates travel sideways like a drawer of specimens |
| Method | flow + in | Plain document energy, one beat of rest |
| Order (close) | pin + real input | The close is an actual input: address in, job ID out |

Families: pin, flow, pan, count, tilt, reveal = 6. No family twice in a row. Total ~12.5 viewport-heights, 6 acts.

## Palette (deliberately not v1's cream/forest, and not the cream-and-brass trap)
Cold instrument graphite + signal orange:
```
--sc-canvas:     #0B0E11   (cold graphite)
--sc-surface:    #141A1F
--sc-ink:        #E9EDF0
--sc-ink-soft:   #97A3AC
--sc-accent:     #FF6B35   (signal orange)
--sc-accent-ink: #0B0E11
```
Display: Outfit. Text: Geist. Monospace (ui-monospace stack) for the console, log, labels — sanctioned for data, and it is the surface's native idiom, not a costume.

## Copy
All real. Dossier figures from the actual Babcock WI report (92,840 records, 518 species, Bald Eagle 42, Whooping Crane 7 IUCN Endangered). Replay log lines and durations from the real production run of dossier 0e5ad70c (2026-08-29): geocode → GBIF 29,371 records (8 km, ≥2011) → narrative (Venice LLM) → cover art → PDF, 7 pages, 5.2 MB, ~90 s wall clock. Live console numbers come from the live API at run time. No invented statistics anywhere.

## Assets
Reuse the 7 approved Venice watercolor plates from v1 (all passed vision review). One new plate in the v2 palette for the close, if review demands it. The plates sit in framed panels (gallery idiom), never full-bleed under type.

## Verification
shoot.mjs desktop + mobile 390 + reduced-motion; manual rail-overflow measurement on the pan act (the harness misses dead pans); console states checked live against the deployed API; feel check against the curve above.
