#!/usr/bin/env python3
"""
WildDeed — instant, AI-generated wildlife dossier for any US land parcel.

Pipeline:
  address → Census geocode → GBIF occurrence query → normalize/dedupe
  → rank flagship species → IUCN enrichment → stats
  → Venice LLM narrative (from structured JSON only)
  → Venice image gen (cover art) → branded PDF via WeasyPrint.

Usage:
  python wilddeed.py --address "..." [--radius 5] [--out DIR]
  python wilddeed.py --lat 43.6 --lng -91.2
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import re
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import requests

VENICE_KEY = None  # set from env in main()
VENICE_BASE = "https://api.venice.ai/api/v1"
GBIF_BASE = "https://api.gbif.org/v1"
CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

# Models (verified against live catalog 2026-08-27)
LLM_MODEL = "gemini-3-6-flash"          # fast, cheap, 1M ctx, JSON schema support
IMG_MODEL = "nano-banana-2"             # fast, reliable, painterly-capable
IMG_MODEL_FALLBACK = "flux-2-pro"

MAX_GBIF_RECORDS = 2000
DEFAULT_RADIUS_KM = 5
DEFAULT_YEARS = 15

# US game-species watchlist (scientific names GBIF keys on)
GAME_SPECIES = {
    "Odocoileus virginianus": "White-tailed Deer",
    "Odocoileus hemionus": "Mule Deer",
    "Alces alces": "Moose",
    "Cervus canadensis": "Elk",
    "Cervus elaphus": "Red Deer / Elk",
    "Rangifer tarandus": "Caribou",
    "Bison bison": "American Bison",
    "Antilocapra americana": "Pronghorn",
    "Meleagris gallopavo": "Wild Turkey",
    "Meleagris ocellata": "Ocellated Turkey",
    "Aix sponsa": "Wood Duck",
    "Anas platyrhynchos": "Mallard",
    "Anas americana": "American Wigeon",
    "Anas clypeata": "Northern Shoveler",
    "Anas acuta": "Northern Pintail",
    "Anas crecca": "Green-winged Teal",
    "Aythya americana": "Redhead",
    "Aythya valisineria": "Canvasback",
    "Aythya marila": "Greater Scaup",
    "Aythya affinis": "Lesser Scaup",
    "Mareca americana": "American Wigeon",
    "Mareca strepera": "Gadwall",
    "Mareca penelope": "Eurasian Wigeon",
    "Spatula discors": "Blue-winged Teal",
    "Spatula clypeata": "Northern Shoveler",
    "Branta canadensis": "Canada Goose",
    "Branta bernicla": "Brant",
    "Chen caerulescens": "Snow Goose",
    "Anser caerulescens": "Snow Goose",
    "Cygnus cygnus": "Whooper Swan",
    "Cygnus buccinator": "Trumpeter Swan",
    "Tympanuchus cupido": "Greater Prairie-Chicken",
    "Tympanuchus pallidicinctus": "Lesser Prairie-Chicken",
    "Tympanuchus phasianellus": "Sharp-tailed Grouse",
    "Bonasa umbellus": "Ruffed Grouse",
    "Centrocercus urophasianus": "Greater Sage-Grouse",
    "Dendragapus obscurus": "Dusky Grouse",
    "Colinus virginianus": "Northern Bobwhite",
    "Callipepla squamata": "Scaled Quail",
    "Callipepla gambelii": "Gambel's Quail",
    "Coturnix coturnix": "Common Quail",
    "Perdix perdix": "Gray Partridge",
    "Phasianus colchicus": "Ring-necked Pheasant",
    "Colinus cristatus": "Crested Bobwhite",
    "Cyrtonyx montezumae": "Montezuma Quail",
    "Oreortyx pictus": "Mountain Quail",
    "Alectoris chukar": "Chukar",
    "Colaptes auratus": "Northern Flicker",
    "Scolopax minor": "American Woodcock",
    "Gallinago gallinago": "Common Snipe",
    "Gallinago delicata": "Wilson's Snipe",
    "Columba livia": "Rock Pigeon",
    "Zenaida macroura": "Mourning Dove",
    "Zenaida asiatica": "White-winged Dove",
    "Cyanocitta cristata": "Blue Jay",
    "Corvus corax": "Common Raven",
    "Lepus americanus": "Snowshoe Hare",
    "Lepus californicus": "Black-tailed Jackrabbit",
    "Lepus townsendii": "White-tailed Jackrabbit",
    "Sylvilagus floridanus": "Eastern Cottontail",
    "Sylvilagus nuttallii": "Mountain Cottontail",
    "Sylvilagus audubonii": "Desert Cottontail",
    "Sylvilagus palustris": "Marsh Rabbit",
    "Lepus europaeus": "European Hare",
    "Oryctolagus cuniculus": "European Rabbit",
    "Marmota monax": "Groundhog",
    "Marmota flaviventris": "Yellow-bellied Marmot",
    "Cynomys ludovicianus": "Black-tailed Prairie Dog",
    "Sciurus niger": "Eastern Fox Squirrel",
    "Sciurus carolinensis": "Gray Squirrel",
    "Tamiasciurus hudsonicus": "Red Squirrel",
    "Tamias striatus": "Eastern Chipmunk",
    "Eutamias minimus": "Least Chipmunk",
    "Neotoma cinerea": "Bushy-tailed Woodrat",
    "Ondatra zibethicus": "Muskrat",
    "Canis latrans": "Coyote",
    "Canis lupus": "Gray Wolf",
    "Canis aureus": "Golden Jackal",
    "Vulpes vulpes": "Red Fox",
    "Vulpes velox": "Swift Fox",
    "Urocyon cinereoargenteus": "Gray Fox",
    "Ursus americanus": "American Black Bear",
    "Ursus arctos": "Grizzly Bear",
    "Ursus maritimus": "Polar Bear",
    "Puma concolor": "Mountain Lion",
    "Lynx rufus": "Bobcat",
    "Lynx canadensis": "Canada Lynx",
    "Lynx lynx": "Eurasian Lynx",
    "Martes americana": "American Marten",
    "Martes pennanti": "Fisher",
    "Pekania pennanti": "Fisher",
    "Gulo gulo": "Wolverine",
    "Taxidea taxus": "American Badger",
    "Mephitis mephitis": "Striped Skunk",
    "Spilogale gracilis": "Western Spotted Skunk",
    "Mephitis macroura": "Hooded Skunk",
    "Lontra canadensis": "North American River Otter",
    "Mustela erminea": "Ermine",
    "Mustela frenata": "Long-tailed Weasel",
    "Neovison vison": "American Mink",
    "Neogale vison": "American Mink",
    "Neovison macrodon": "Sea Mink",
    "Procyon lotor": "Raccoon",
    "Bassariscus astutus": "Ringtail",
    "Spilogale putorius": "Eastern Spotted Skunk",
    "Felis rufus": "Bobcat",
    "Felis concolor": "Mountain Lion",
    "Sus scrofa": "Wild Boar",
    "Scalopus aquaticus": "Eastern Mole",
    "Condylura cristata": "Star-nosed Mole",
    "Didelphis virginiana": "Virginia Opossum",
    "Dasypus novemcinctus": "Nine-banded Armadillo",
    "Myocastor coypus": "Nutria",
    "Castor canadensis": "North American Beaver",
    "Alces americanus": "Moose",
    "Rangifer caribou": "Caribou",
    "Cervus nippon": "Sika Deer",
    "Damaliscus dorcas": "Blesbok",
    "Ammotragus lervia": "Barbary Sheep",
    "Hemitragus jemlahicus": "Himalayan Tahr",
    "Capra hircus": "Feral Goat",
    "Ovis canadensis": "Bighorn Sheep",
    "Ovis aries": "Dall Sheep / Mouflon",
    "Ovis dalli": "Dall Sheep",
    "Oreamnos americanus": "Mountain Goat",
    "Oreamnos americanus missoulae": "Mountain Goat",
    # fish — popular game species
    "Micropterus dolomieu": "Smallmouth Bass",
    "Micropterus salmoides": "Largemouth Bass",
    "Micropterus punctulatus": "Spotted Bass",
    "Micropterus floridanus": "Florida Bass",
    "Sander vitreus": "Walleye",
    "Sander canadensis": "Sauger",
    "Perca flavescens": "Yellow Perch",
    "Scomberomorus maculatus": "Spanish Mackerel",
    "Esox lucius": "Northern Pike",
    "Esox americanus": "Redfin Pickerel",
    "Esox niger": "Chain Pickerel",
    "Salmo trutta": "Brown Trout",
    "Salmo salar": "Atlantic Salmon",
    "Salvelinus fontinalis": "Brook Trout",
    "Salvelinus namaycush": "Lake Trout",
    "Oncorhynchus mykiss": "Rainbow Trout",
    "Oncorhynchus clarkii": "Cutthroat Trout",
    "Oncorhynchus tshawytscha": "Chinook Salmon",
    "Oncorhynchus kisutch": "Coho Salmon",
    "Oncorhynchus nerka": "Sockeye Salmon",
    "Oncorhynchus gorbuscha": "Pink Salmon",
    "Oncorhynchus keta": "Chum Salmon",
    "Coregonus clupeaformis": "Lake Whitefish",
    "Lota lota": "Burbot",
    "Stizostedion vitreum": "Walleye",
    "Morone saxatilis": "Striped Bass",
    "Morone chrysops": "White Bass",
    "Morone mississippiensis": "Yellow Bass",
    "Pomoxis annularis": "White Crappie",
    "Pomoxis nigromaculatus": "Black Crappie",
    "Lepomis macrochirus": "Bluegill",
    "Lepomis cyanellus": "Green Sunfish",
    "Lepomis gibbosus": "Pumpkinseed",
    "Lepomis microlophus": "Redear Sunfish",
    "Lepomis auritus": "Redbreast Sunfish",
    "Ambloplites rupestris": "Rock Bass",
    "Aplodinotus grunniens": "Freshwater Drum",
    "Ictalurus punctatus": "Channel Catfish",
    "Ictalurus furcatus": "Blue Catfish",
    "Pylodictis olivaris": "Flathead Catfish",
    "Ameiurus melas": "Black Bullhead",
    "Ameiurus natalis": "Yellow Bullhead",
    "Catostomus commersonii": "White Sucker",
    "Moxostoma macrolepidotum": "Shorthead Redhorse",
    "Hypentelium nigricans": "Northern Hog Sucker",
    "Acipenser fulvescens": "Lake Sturgeon",
    "Acipenser oxyrinchus": "Atlantic Sturgeon",
    "Acipenser transmontanus": "White Sturgeon",
    "Polyodon spathula": "Paddlefish",
    "Amia calva": "Bowfin",
    "Lepisosteus oculatus": "Spotted Gar",
    "Lepisosteus osseus": "Longnose Gar",
    "Lepisosteus platostomus": "Shortnose Gar",
    "Atractosteus spatula": "Alligator Gar",
    "Culaea inconstans": "Brook Stickleback",
    "Fundulus diaphanus": "Banded Killifish",
    "Luxilus cornutus": "Common Shiner",
    "Notropis atherinoides": "Emerald Shiner",
    "Semotilus atromaculatus": "Creek Chub",
    "Rhinichthys cataractae": "Longnose Dace",
    "Cottus bairdii": "Mottled Sculpin",
    "Roccus americanus": "White Perch",
    "Stizostedion canadense": "Sauger",
    "Carpiodes cyprinus": "Quillback",
    "Moxostoma erythrurum": "Golden Redhorse",
    "Moxostoma anisurum": "Silver Redhorse",
    "Carassius auratus": "Goldfish",
    "Cyprinus carpio": "Common Carp",
}

IUCN_LABELS = {
    "LC": ("Least Concern", "#4a7c59"),
    "NT": ("Near Threatened", "#b08d2e"),
    "VU": ("Vulnerable", "#c06a2c"),
    "EN": ("Endangered", "#b03030"),
    "CR": ("Critically Endangered", "#8b1a1a"),
    "EW": ("Extinct in the Wild", "#555555"),
    "EX": ("Extinct", "#222222"),
    "DD": ("Data Deficient", "#777777"),
    "NE": ("Not Evaluated", "#999999"),
}

INVASIVE_WATCH = {
    "Sus scrofa", "Cyprinus carpio", "Myocastor coypus",
    "Alectoris chukar", "Perdix perdix", "Phasianus colchicus",
    "Carassius auratus", "Lepomis cyanellus", "Oryctolagus cuniculus",
    "Lepus europaeus", "Salmo trutta", "Sander lucioperca",
    "Apocynum cannabinoides", "Lythrum salicaria", "Phragmites australis",
    "Alliaria petiolata", "Rosa multiflora", "Elaeagnus umbellata",
    "Pueraria montana", "Microstegium vimineum", "Fallopia japonica",
    "Reynoutria japonica", "Cirsium arvense", "Carduus nutans",
    "Euphorbia esula", "Bromus tectorum", "Taeniatherum caput-medusae",
    "Centaurea stoebe", "Centaurea solstitialis", "Isatis tinctoria",
    "Ventenata dubia", "Cynoglossum officinale", "Linaria dalmatica",
}


def log(msg: str) -> None:
    print(f"[wilddeed] {msg}", file=sys.stderr, flush=True)


# ────────────────────────── geocoding ──────────────────────────

def geocode_census(address: str) -> dict:
    r = requests.get(
        CENSUS_URL,
        params={"address": address, "benchmark": "Public_AR_Current", "format": "json"},
        timeout=30,
    )
    r.raise_for_status()
    matches = r.json().get("result", {}).get("addressMatches", [])
    if not matches:
        return {}
    m = matches[0]
    return {
        "lat": m["coordinates"]["y"],
        "lng": m["coordinates"]["x"],
        "matched_address": m["matchedAddress"],
        "components": m.get("addressComponents", {}),
        "all_matches": [
            {"lat": x["coordinates"]["y"], "lng": x["coordinates"]["x"],
             "address": x["matchedAddress"]}
            for x in matches[:5]
        ],
    }


# ────────────────────────── GBIF ──────────────────────────

def circle_polygon(lat: float, lng: float, radius_km: float, points: int = 8) -> str:
    """Approximate a circle with a closed polygon (GBIF geometry param)."""
    pts = []
    for i in range(points):
        t = 2 * math.pi * i / points
        p_lng = lng + radius_km / (111.32 * math.cos(math.radians(lat))) * math.cos(t)
        p_lat = lat + radius_km / 110.574 * math.sin(t)
        pts.append(f"{p_lng:.4f} {p_lat:.4f}")
    pts.append(pts[0])  # close the ring
    return f"POLYGON(({', '.join(pts)}))"


def gbif_search(lat: float, lng: float, radius_km: int, min_year: int,
                max_records: int = MAX_GBIF_RECORDS) -> dict:
    """Fetch occurrence records within radius via geometry polygon (decimal*
    radius params behave inconsistently; WKT polygon is reliable)."""
    params = {
        "geometry": circle_polygon(lat, lng, radius_km),
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "occurrenceStatus": "PRESENT",
        "year": f"{min_year},{date.today().year}",
        "limit": 300,
        "offset": 0,
    }
    records = []
    total = None
    for page in range(10):  # up to 3000
        params["offset"] = page * 300
        r = requests.get(f"{GBIF_BASE}/occurrence/search", params=params, timeout=60)
        r.raise_for_status()
        d = r.json()
        if total is None:
            total = d.get("count", 0)
            log(f"GBIF: {total} records within {radius_km} km (≥{min_year})")
        records.extend(d.get("results", []))
        if d.get("endOfRecords") or len(records) >= max_records:
            break
        time.sleep(0.2)
    return {"total": total or 0, "records": records[:max_records]}


def normalize_records(records: list) -> list[dict]:
    """Group records by species; collapse synonyms via acceptedUsage."""
    species = {}
    for rec in records:
        cls = rec.get("classifications", {})
        # try backbone classification first
        usage = None
        for v in cls.values():
            if isinstance(v, dict) and v.get("usage"):
                usage = v
                break
        sci = rec.get("scientificName") or (usage or {}).get("name", "")
        if not sci:
            continue
        sci = sci.split(" (")[0].strip()
        # rank filter: species level only (dropssp/var for readability)
        key = rec.get("speciesKey") or rec.get("taxonKey")
        vern = rec.get("vernacularName") or ""
        year = None
        try:
            if rec.get("year"):
                year = int(rec["year"])
        except (ValueError, TypeError):
            pass
        month = rec.get("month")
        basis = rec.get("basisOfRecord", "")
        s = species.setdefault(key, {
            "speciesKey": key,
            "scientificName": sci,
            "vernacular": vern,
            "count": 0,
            "years": [],
            "months": [],
            "basis": Counter(),
        })
        s["count"] += 1
        if year:
            s["years"].append(year)
        if month:
            s["months"].append(month)
        s["basis"][basis] += 1
        if vern and not s["vernacular"]:
            s["vernacular"] = vern
    out = []
    for s in species.values():
        common = s["vernacular"] or GAME_SPECIES.get(s["scientificName"], "")
        # prefer game-species common name if vernacular missing
        out.append({
            "scientificName": s["scientificName"],
            "commonName": common,
            "count": s["count"],
            "lastSeen": max(s["years"]) if s["years"] else None,
            "firstSeen": min(s["years"]) if s["years"] else None,
            "months": sorted(Counter(s["months"]).items()),
            "iucn": None,
            "isGame": s["scientificName"] in GAME_SPECIES,
            "isInvasive": s["scientificName"] in INVASIVE_WATCH,
        })
    return out


def enrich_iucn(species_list: list, lat: float, lng: float) -> None:
    """Enrich with IUCN status using a facet query keyed by taxon (accurate + 1 call)."""
    # Query facet of iucnRedListCategory over same filter, keyed per-species is not
    # directly supported; instead fetch species-level from GBIF species match API.
    # Faster path: occurrence records often carry iucnRedListCategory already.
    pass  # handled in rank+enrich step below


def rank_flagships(species_list: list, top_n: int = 15) -> list:
    """Flagship set: top-N by count + all game + all threatened (IUCN filled later)."""
    ranked = sorted(species_list, key=lambda s: -s["count"])
    flagships = set()
    for s in ranked[:top_n]:
        flagships.add(id(s))
    for s in species_list:
        if s["isGame"] and s["count"] >= 1:
            flagships.add(id(s))
    # threatened added after IUCN enrichment
    return [s for s in species_list if id(s) in flagships]


# ────────────────────────── Venice LLM ──────────────────────────

def venice_chat(messages: list, model: str = LLM_MODEL, temperature: float = 0.7,
                max_tokens: int = 4000, response_format: dict | None = None) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format
    r = requests.post(
        f"{VENICE_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {VENICE_KEY}",
                 "Content-Type": "application/json"},
        json=payload, timeout=300,
    )
    r.raise_for_status()
    d = r.json()
    return d["choices"][0]["message"]["content"]


def venice_image(prompt: str, out_path: Path, model: str = IMG_MODEL,
                 ar: str = "16:9", resolution: str = "2K") -> Path:
    payload = {"model": model, "prompt": prompt, "aspect_ratio": ar,
               "resolution": resolution, "hide_watermark": True, "return_binary": False}
    r = requests.post(
        f"{VENICE_BASE}/image/generate",
        headers={"Authorization": f"Bearer {VENICE_KEY}",
                 "Content-Type": "application/json"},
        json=payload, timeout=420,
    )
    if r.status_code >= 400:
        log(f"image gen {model} failed ({r.status_code}), falling back")
        if model != IMG_MODEL_FALLBACK:
            return venice_image(prompt, out_path, IMG_MODEL_FALLBACK, ar, resolution)
        r.raise_for_status()
    d = r.json()
    imgs = d["images"]
    img_b64 = imgs[0]["data"] if isinstance(imgs[0], dict) else imgs[0]
    raw = base64.b64decode(img_b64)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if raw[:4] == b"RIFF":  # WebP → convert to PNG for WeasyPrint
        import io
        from PIL import Image
        Image.open(io.BytesIO(raw)).convert("RGB").save(out_path, "PNG")
    else:
        out_path.write_bytes(raw)
    log(f"cover art → {out_path}")
    return out_path


# ────────────────────────── narrative (deterministic + LLM) ──────────────────────────

NARRATIVE_PROMPT = """You are the "Estate Naturalist" for WildDeed, writing a wildlife dossier for a rural land parcel in the United States. You write in polished, precise plain English — the register of a well-read field naturalist writing for a land buyer who is smart but not a biologist. Never hype. Never invent.

HARD CONSTRAINTS:
- Only name species that appear in the DATA below. If a species is not in the data, it does not exist on this parcel. Do not name any other species, genus, or habitat type by common or scientific name.
- You may use general habitat terms (forest, wetland, grassland, river, lake) and describe seasonality from the month data.
- Use each species' commonName if present, otherwise scientificName.
- No em dashes. No marketing clichés. No superlatives without evidence ("the finest", "world-class").
- Length discipline: exec summary 3-4 sentences; each flagship paragraph 3-5 sentences.

DATA (JSON):
{data}

Write the following sections, each wrapped in the exact tags shown:
<summary>
3-4 sentence plain-English verdict of this parcel's wildlife profile. Mention the most notable species and the overall character of the data.
</summary>
<habitat>
2 short paragraphs on habitat and landscape context inferred from the species mix and observation counts. Reference specific taxa groups as evidence.
</habitat>
<profiles>
For each species in the flagship list, write one paragraph (3-5 sentences) covering: who it is, what its observation record here shows (count, recency, seasonality), and one interesting, factual note about its natural history that is relevant to a land buyer. Separate paragraphs with a blank line. Order: most observations first.
</profiles>
<game>
2 paragraphs on the game and harvest opportunity, grounded in the game-species data. If no game species appear in the data, say so plainly and explain what that means (absence of records is not absence of animals).
</game>
<conservation>
1-2 paragraphs on conservation notes: threatened or endangered species nearby (from data), invasive-species signals, and any data-quality caveats.
</conservation>
<seasonal>
1 paragraph on seasonal patterns drawn from the month histogram: when this parcel's wildlife record is most active, and what that suggests about visiting.
</seasonal>"""


def build_llm_data(payload: dict) -> str:
    slim = {
        "location": payload["location"],
        "recordStats": payload["stats"],
        "species": [
            {k: s[k] for k in ("scientificName", "commonName", "count", "lastSeen",
                                "isGame", "isInvasive")}
            | {"iucn": s.get("iucn"), "peakMonths": peak_months(s)}
            for s in payload["narrative_set"]
        ],
        "gameSpecies": [s["commonName"] or s["scientificName"]
                        for s in payload["narrative_set"] if s["isGame"]],
        "threatenedSpecies": [s["commonName"] or s["scientificName"]
                              for s in payload["narrative_set"] if s.get("iucn") in ("VU", "EN", "CR")],
        "invasiveSpecies": [s["commonName"] or s["scientificName"]
                            for s in payload["narrative_set"] if s["isInvasive"]],
    }
    return json.dumps(slim, indent=1)


def peak_months(s: dict) -> list:
    return [m for m, c in s["months"] if c >= max((c for _, c in s["months"]), default=0) * 0.5] if s["months"] else []


def parse_tagged(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.S)
    return m.group(1).strip() if m else ""


def validate_narrative(narr: dict, payload: dict) -> list:
    """Every species name in the narrative must exist in source data."""
    allowed = set()
    for s in payload["flagships"]:
        allowed.add(s["commonName"].lower() if s["commonName"] else "")
        allowed.add(s["scientificName"].lower())
        allowed.discard("")
    violations = []
    all_text = " ".join(str(v) for v in narr.values())
    # find capitalized species-like names not in allowed set
    candidates = re.findall(r"\b([A-Z][a-z]+(?:\s+[a-z]+)?)\b", all_text)
    stopwords = set("""the a an and or but in on at to of for with from by is are was were be been
    this that these those it its their there here what which who whom when where why how
    data record records species parcel land report wildlife habitat forest wetland grassland
    year years month months winter spring summer fall autumn january february march april
    may june july august september october november december iucn gbif wilddeed estate naturalist
    section summary habitat profiles game conservation seasonal notes red list endangered
    threatened invasive introduced native population populations observation observations
    county state province united states america north american white-tailed tailed mule
    whitetail ecoregion undeveloped rural agricultural agriculture farm farms field fields
    no not none zero absent absence lacking missing few sparse thin rich strong robust
    heavily moderately most more less least fewer than them they these those
    others other another some any all every each both either neither
    first second third fourth fifth last latest early late peak season seasonal
    eastern western southern northern central upper lower great plains prairie
    atlantic pacific gulf coast coastal interior highlands mountains valley valleys
    river rivers creek creeks stream streams lake lakes pond ponds marsh marshes swamp swamps
    wetlands wetland forested open closed canopy understory ground cover soils soil
    deer elk moose bison pronghorn turkey waterfowl ducks geese swan swans
    predators bear bears lion lions bobcat bobcats lynx coyote coyotes wolf wolves fox foxes
    fish fishing fisheries bass trout pike walleye panfish catfish sucker suckers minnow minnows
    birds bird avian raptors raptor hawk hawks eagle eagles owl owls songbirds songbird
    mammals mammal reptiles reptile amphibians amphibian frogs frog toads toad salamanders salamander
    turtles turtle snakes snake lizards lizard insects insect bees bee butterflies butterfly
    plants plant trees tree shrubs shrub wildflowers wildflower grasses grass forbs forb
    family genera genus group groups type types kind kinds
    morning evening dusk dawn night day midday afternoon
    evidence record-based publicly available reported documented observed sighted seen heard
    whose whom she he his her hers ours yours mine ours
    due because since although though however therefore thus hence moreover furthermore
    overall generally typically usually commonly rarely seldom occasionally frequently
    large small medium sized size big little tiny huge enormous giant
    young old new recent historical historic current present past future
    property tract acre acreage acres parcel boundary boundaries area areas region regional
    buyer buyers seller sellers broker brokerage listing listings market marketing
    note notes noting noted see seeing seen observe observing observation
    protected unprotected managed unmanaged conserved conservation priorities priority
    levels level status statuses category categories list listed listing lists
    fisher martens marten wolverine wolverines badger badgers skunk skunks otter otters
    mink minks beaver beavers muskrat muskrats raccoon raccoons opossum opossums
    armadillo armadillos nutria hares hare rabbit rabbits squirrel squirrels chipmunk chipmunks
    groundhog groundhogs marmot marmots prairie dogs dog mice mouse rat rats voles vole
    shrew shrews mole moles bat bats whale whales dolphin dolphins
    white-tail whitetails bucks does fawn fawns tom toms gobblers hens
    bulls cows calf calves
    """.split())
    for cand in candidates:
        cl = cand.lower()
        if cl in stopwords or cl in allowed:
            continue
        # two-word names where second word lowercase (species-like: "white oak")
        if len(cand.split()) >= 2 and cand.split()[1][0].islower():
            violations.append(cand)
        # known species common-name words not in data (deer-like, bird-like)
    return violations


# ────────────────────────── PDF ──────────────────────────

CSS = """
@page {
  size: letter;
  margin: 0.75in 0.7in 0.85in 0.7in;
  @bottom-center {
    content: "WildDeed Dossier · " counter(page) " / " counter(pages);
    font-family: 'Georgia', serif;
    font-size: 8pt; color: #8a7f6f;
  }
}
* { box-sizing: border-box; }
body { font-family: 'Georgia', 'Times New Roman', serif; color: #2a241c; font-size: 10.5pt; line-height: 1.55; }
.cover { page: cover; text-align: left; padding-top: 2.2in; }
@page cover { margin: 0; }
.cover-img { position: absolute; top: 0; left: 0; width: 8.5in; height: 4.6in; object-fit: cover; }
.cover-body { position: absolute; top: 4.35in; left: 0.75in; right: 0.75in; }
.cover-kicker { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 9pt; letter-spacing: 0.35em; text-transform: uppercase; color: #8a7f6f; margin-bottom: 0.5in; }
.cover h1 { font-size: 30pt; font-weight: normal; margin: 0 0 0.1in 0; line-height: 1.15; }
.cover .subtitle { font-size: 13pt; color: #4a4238; font-style: italic; margin-bottom: 0.35in; }
.cover .meta { font-size: 10pt; color: #6b6154; line-height: 1.7; }
.cover .brand { position: absolute; bottom: 0.5in; left: 0.75in; font-family: 'Helvetica Neue', Arial, sans-serif; font-weight: bold; letter-spacing: 0.18em; font-size: 11pt; color: #2a241c; }
.cover .brand small { font-weight: normal; letter-spacing: 0.08em; color: #8a7f6f; }
h2 { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 14pt; font-weight: 600; letter-spacing: 0.02em; color: #1f3d2b; margin: 0.45in 0 0.14in 0; padding-bottom: 3pt; border-bottom: 1.5pt solid #1f3d2b; }
h2.first { margin-top: 0; }
h3 { font-family: 'Helvetica Neue', Arial, sans-serif;  font-size: 11pt; margin: 0.18in 0 0.05in 0; }
p { margin: 0 0 0.12in 0; text-align: justify; }
.species-table { width: 100%; border-collapse: collapse; margin: 0.12in 0 0.2in 0; font-size: 9pt; }
.species-table th { font-family: 'Helvetica Neue', Arial, sans-serif; text-align: left; font-size: 8pt; letter-spacing: 0.06em; text-transform: uppercase; color: #6b6154; padding: 4pt 6pt; border-bottom: 1pt solid #2a241c; }
.species-table td { padding: 4.5pt 6pt; border-bottom: 0.5pt solid #d8d0c2; vertical-align: top; }
.badge { display: inline-block; font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 7pt; font-weight: 700; letter-spacing: 0.05em; padding: 1.5pt 6pt; border-radius: 8pt; color: #fff; }
.badge-lc { background: #4a7c59; } .badge-nt { background: #b08d2e; } .badge-vu { background: #c06a2c; }
.badge-en { background: #b03030; } .badge-cr { background: #8b1a1a; } .badge-dd { background: #777; }
.badge-game { background: #1f3d2b; }
.badge-inv { background: #6b4a1e; }
.season-bar { display: flex; height: 16pt; margin: 6pt 0 2pt 0; }
.season-cell { flex: 1; background: #e8e2d4; position: relative; }
.season-cell.on { background: #1f3d2b; }
.season-labels { display: flex; font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 6.5pt; color: #6b6154; margin-bottom: 8pt; }
.season-labels span { flex: 1; text-align: center; }
.stat-grid { display: flex; gap: 0.18in; margin: 0.15in 0 0.25in 0; }
.stat { flex: 1; border-left: 2pt solid #1f3d2b; padding-left: 8pt; }
.stat .n { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 17pt; font-weight: 700; color: #1f3d2b; }
.stat .l { font-size: 8pt; color: #6b6154; text-transform: uppercase; letter-spacing: 0.05em; }
.disclaimer { margin-top: 0.3in; padding: 10pt; background: #f4efe4; border: 0.5pt solid #d8d0c2; font-size: 8.5pt; color: #4a4238; }
.disclaimer p { text-align: left; margin: 0; }
.footnote { font-size: 8pt; color: #8a7f6f; margin-top: 4pt; }
.page-break { page-break-before: always; }
"""

HTML_SHELL = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title} — WildDeed Dossier</title></head>
<body>
<div class="cover">
  <img class="cover-img" src="{cover}" />
  <div class="cover-body">
    <div class="cover-kicker">Wildlife Dossier · Confidential Prepared for the Buyer's File</div>
    <h1>{title}</h1>
    <div class="subtitle">An independent wildlife record for {address}</div>
    <div class="meta">
      Prepared {today}<br/>
      {n_species} species documented · {n_records} public occurrence records<br/>
      Search radius {radius} km · Records from {min_year}–{max_year}
    </div>
  </div>
  <div class="brand">WILDDEED <small>· A NATURALIST'S BACKGROUND CHECK FOR LAND</small></div>
</div>

<h2 class="first">Executive Summary</h2>
{summary}

<h2>Habitat &amp; Landscape Context</h2>
{habitat}

<h2>Flagship Species</h2>
{species_table}
{profiles}

<div class="page-break"></div>
<h2>Game &amp; Harvest Species</h2>
{game}

<h2>Conservation Notes</h2>
{conservation}

<h2>Seasonal Activity</h2>
{season_bar}
{seasonal}

<h2>Data Appendix &amp; Disclaimer</h2>
<div class="stat-grid">
  <div class="stat"><div class="n">{n_species}</div><div class="l">Species</div></div>
  <div class="stat"><div class="n">{n_records}</div><div class="l">Records</div></div>
  <div class="stat"><div class="n">{radius} km</div><div class="l">Radius</div></div>
  <div class="stat"><div class="n">{min_year}–{max_year}</div><div class="l">Record years</div></div>
</div>
<div class="disclaimer">
<p><strong>Data sources.</strong> Global Biodiversity Information Facility (GBIF) occurrence records ({n_records} records, {min_year}–{max_year}, {radius} km radius) and IUCN Red List categories distributed through GBIF. Observation counts reflect public recording effort, not population size. Species absent from this record are not necessarily absent from the parcel.</p>
<p style="margin-top:6pt"><strong>Disclaimer.</strong> This dossier is generated from public biodiversity records. It is not a biological survey and not a guarantee of species presence. For land-use decisions requiring biological certainty, consult a licensed biologist.</p>
</div>
<p class="footnote">WildDeed · wilddeed.com · Prepared {today} · Report ID {report_id}</p>
</body></html>"""


def render_species_table(flagships: list) -> str:
    rows = []
    for s in flagships[:20]:
        label, color = IUCN_LABELS.get(s.get("iucn") or "NE", ("Not Evaluated", "#999"))
        badge = f'<span class="badge badge-{(s.get("iucn") or "NE").lower()}">{label}</span>' if s.get("iucn") else ""
        game = '<span class="badge badge-game">GAME</span>' if s["isGame"] else ""
        inv = '<span class="badge badge-inv">INVASIVE</span>' if s["isInvasive"] else ""
        name = s["commonName"] or s["scientificName"]
        sci = f'<br/><span style="font-style:italic; color:#8a7f6f; font-size:8pt">{s["scientificName"]}</span>'
        rows.append(
            f'<tr><td><strong>{name}</strong>{sci}</td>'
            f'<td style="text-align:right">{s["count"]}</td>'
            f'<td style="text-align:right">{s["lastSeen"] or "—"}</td>'
            f'<td>{badge} {game} {inv}</td></tr>'
        )
    return (
        '<table class="species-table"><tr><th>Species</th><th style="text-align:right">Obs</th>'
        '<th style="text-align:right">Last</th><th>Status</th></tr>' + "".join(rows) + "</table>"
    )


def render_season_bar(payload: dict) -> str:
    months = Counter()
    for s in payload["flagships"]:
        for m, c in s["months"]:
            months[m] += c
    peak = max(months.values()) if months else 0
    cells = ""
    labels = ""
    names = ["J","F","M","A","M","J","J","A","S","O","N","D"]
    for i in range(1, 13):
        active = months.get(i, 0) >= max(peak * 0.5, 1)
        cells += f'<div class="season-cell{" on" if active else ""}"></div>'
        labels += f'<span>{names[i-1]}</span>'
    return f'<div class="season-bar">{cells}</div><div class="season-labels">{labels}</div>'


def paragraphs_html(text: str) -> str:
    return "".join(f"<p>{p.strip()}</p>" for p in text.split("\n\n") if p.strip())


def render_pdf(payload: dict, narr: dict, cover_path: Path, out_pdf: Path) -> Path:
    from weasyprint import HTML
    html = HTML_SHELL.format(
        title=payload["title"],
        cover=cover_path.as_uri() if cover_path else "",
        address=payload["location"]["matched_address"],
        today=date.today().strftime("%B %d, %Y"),
        n_species=len(payload["species_all"]),
        n_records=payload["stats"]["totalRecords"],
        radius=payload["radius_km"],
        min_year=payload["stats"]["minYear"],
        max_year=payload["stats"]["maxYear"],
        summary=paragraphs_html(narr.get("summary", "")),
        habitat=paragraphs_html(narr.get("habitat", "")),
        species_table=render_species_table(payload["flagships"]),
        profiles=paragraphs_html(narr.get("profiles", "")),
        game=paragraphs_html(narr.get("game", "")),
        conservation=paragraphs_html(narr.get("conservation", "")),
        seasonal=paragraphs_html(narr.get("seasonal", "")),
        season_bar=render_season_bar(payload),
        report_id=payload["report_id"],
    )
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(out_pdf.parent)).write_pdf(out_pdf)
    return out_pdf


# ────────────────────────── orchestration ──────────────────────────

def generate_report(address: str = None, lat: float = None, lng: float = None,
                    radius_km: int = DEFAULT_RADIUS_KM, out_dir: str = None,
                    skip_image: bool = False, title: str = None,
                    on_progress=None) -> dict:
    """on_progress, when given, is called as on_progress(stage_key, human_message)
    at each pipeline stage so callers (the API layer) can expose live status."""
    def progress(key, msg=""):
        if on_progress:
            try:
                on_progress(key, msg)
            except Exception:
                pass

    import os
    global VENICE_KEY
    VENICE_KEY = VENICE_KEY or os.environ.get("VENICE_API_KEY")
    if not VENICE_KEY:
        raise SystemExit("VENICE_API_KEY not set")

    t0 = time.time()
    # 1. geocode
    if address and (lat is None or lng is None):
        log(f"geocoding: {address}")
        progress("geocoding", "resolving the address")
        geo = geocode_census(address)
        if not geo:
            raise SystemExit(f"Could not geocode address: {address}")
        lat, lng = geo["lat"], geo["lng"]
        matched = geo["matched_address"]
    else:
        matched = address or f"{lat:.4f}, {lng:.4f}"
    log(f"location: {matched} ({lat:.4f}, {lng:.4f})")

    # 2. GBIF
    progress("gbif", f"querying GBIF within {radius_km} km")
    min_year = date.today().year - DEFAULT_YEARS
    gbif = gbif_search(lat, lng, radius_km, min_year)
    if not gbif["records"]:
        log("zero records; expanding radius once")
        radius_km *= 2
        gbif = gbif_search(lat, lng, radius_km, min_year)

    # 3. normalize
    species = normalize_records(gbif["records"])
    species.sort(key=lambda s: -s["count"])
    log(f"normalized to {len(species)} species")
    progress("identify", f"{gbif['total']:,} records · {len(species)} species found")

    # IUCN from records (single pass — cheap and accurate for present taxa)
    iucn_by_sci = {}
    for rec in gbif["records"]:
        i = rec.get("iucnRedListCategory")
        sci = rec.get("scientificName", "").split(" (")[0]
        if i and sci:
            iucn_by_sci[sci] = i
    for s in species:
        s["iucn"] = iucn_by_sci.get(s["scientificName"])

    # 4. rank
    progress("rank", "ranking the notable species")
    flagships = rank_flagships(species)
    # add threatened
    for s in species:
        if s.get("iucn") in ("VU", "EN", "CR", "NT"):
            if id(s) not in [id(f) for f in flagships]:
                flagships.append(s)
    flagships.sort(key=lambda s: -s["count"])
    # cap the narrative set (LLM context discipline); keep full set for the table
    narrative_set = flagships[:15]
    log(f"flagship set: {len(flagships)} species ({len(narrative_set)} in narrative)")

    years_all = [s["lastSeen"] for s in species if s["lastSeen"]]
    payload = {
        "report_id": uuid.uuid4().hex[:8],
        "title": title or "The Wildlife Record of This Land",
        "location": {"lat": lat, "lng": lng, "matched_address": matched},
        "radius_km": radius_km,
        "stats": {
            "totalRecords": gbif["total"],
            "nSpecies": len(species),
            "minYear": min_year,
            "maxYear": max(years_all) if years_all else date.today().year,
            "dataDensity": "dense" if gbif["total"] > 500 else ("moderate" if gbif["total"] > 100 else "thin"),
        },
        "species_all": species,
        "flagships": flagships,
        "narrative_set": narrative_set,
    }

    # 5. LLM narrative
    log("writing narrative (Venice LLM)...")
    progress("narrative", "writing the naturalist's narrative")
    data_str = build_llm_data(payload)
    raw = venice_chat([{"role": "user",
                        "content": NARRATIVE_PROMPT.replace("{data}", data_str)}],
                      max_tokens=8000)
    narr = {tag: parse_tagged(raw, tag)
            for tag in ("summary", "habitat", "profiles", "game", "conservation", "seasonal")}
    missing = [k for k, v in narr.items() if not v]
    if missing:
        log(f"WARNING: LLM missing tags: {missing}")
        log(f"raw response head: {raw[:500]}")
    violations = validate_narrative(narr, payload)
    if violations:
        log(f"name-validation flagged {len(violations)} candidates: {violations[:8]}")

    # 6. cover art
    cover_path = None
    if not skip_image:
        progress("cover", "painting the cover plate")
        sig = flagships[0] if flagships else None
        sig_name = (sig["commonName"] or sig["scientificName"]) if sig else "North American woodland"
        try:
            out_dir_path = Path(out_dir) if out_dir else Path("reports")
            cover_path = venice_image(COVER_PROMPT.format(species=sig_name),
                                      out_dir_path / f"cover-{payload['report_id']}.png")
        except Exception as e:
            log(f"cover art failed: {e}")

    # 7. PDF
    progress("pdf", "binding the dossier")
    out_dir_path = Path(out_dir) if out_dir else Path("reports")
    out_pdf = out_dir_path / f"wilddeed-{payload['report_id']}.pdf"
    render_pdf(payload, narr, cover_path, out_pdf)
    log(f"PDF → {out_pdf}  ({time.time()-t0:.1f}s total)")

    return {"pdf": str(out_pdf), "cover": str(cover_path) if cover_path else None,
            "narrative": narr, "payload": payload, "violations": violations}


COVER_PROMPT = """Painterly naturalist illustration in the style of a vintage field guide plate: {species} in its native North American habitat, rendered in soft gouache and colored pencil with fine naturalist detail, muted earthy palette of deep forest green, warm ochre, and cream, subtle paper texture, no text, no watermark, no border, composition with generous negative space in the lower third, museum-quality wildlife art"""


def main():
    ap = argparse.ArgumentParser(description="WildDeed wildlife dossier generator")
    ap.add_argument("--address", help="US street address or city, state")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lng", type=float)
    ap.add_argument("--radius", type=int, default=DEFAULT_RADIUS_KM)
    ap.add_argument("--out", default="reports")
    ap.add_argument("--title", default=None)
    ap.add_argument("--skip-image", action="store_true")
    args = ap.parse_args()
    if not args.address and (args.lat is None or args.lng is None):
        ap.error("need --address or --lat/--lng")

    result = generate_report(
        address=args.address, lat=args.lat, lng=args.lng,
        radius_km=args.radius, out_dir=args.out, skip_image=args.skip_image,
        title=args.title,
    )
    print(json.dumps({"pdf": result["pdf"], "cover": result["cover"],
                      "violations": result["violations"]}, indent=2))


if __name__ == "__main__":
    main()
