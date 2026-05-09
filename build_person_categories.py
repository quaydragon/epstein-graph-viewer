#!/usr/bin/env python3
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

CATEGORIES = {
    "sex_trafficking": {
        "label": "Sex Trafficking",
        "color": "#f28c28",
        "keywords": [
            "sex trafficking",
            "trafficking",
            "sex trade",
            "commercial sex",
            "prostitution ring",
            "trafficked",
        ],
    },
    "rape": {
        "label": "Rape",
        "color": "#ffe34d",
        "keywords": ["rape", "raped", "sexual assault", "assaulted"],
    },
    "murder": {
        "label": "Murder",
        "color": "#d62828",
        "keywords": ["murder", "homicide", "killed", "killing"],
    },
    "cannibalism": {
        "label": "Cannibalism",
        "color": "#111111",
        "keywords": ["cannibal", "cannibalism"],
    },
    "politics": {
        "label": "Politics",
        "color": "#7b2cbf",
        "keywords": [
            "president",
            "senator",
            "congress",
            "committee",
            "campaign",
            "governor",
            "white house",
            "political",
        ],
    },
    "victim": {
        "label": "Victim",
        "color": "#1f6fd6",
        # Victim is role-driven (from person_roles.csv), not keyword-driven.
        "keywords": [],
    },
    "science": {
        "label": "Science",
        "color": "#2a9d8f",
        "keywords": [
            "science",
            "scientist",
            "research",
            "laboratory",
            "lab",
            "biological",
            "physics",
            "mathematics",
        ],
    },
    "philanthropy": {
        "label": "Philanthropy",
        "color": "#ff66b3",
        "keywords": [
            "philanthropy",
            "philanthropic",
            "charity",
            "foundation",
            "donation",
            "donor",
            "nonprofit",
        ],
    },
    "lawyer": {
        "label": "Lawyer",
        "color": "#00bcd4",
        # Lawyer is role-driven (from person_roles.csv), not keyword-driven.
        "keywords": [],
    },
}

CRIME_CATEGORIES = {"sex_trafficking", "rape", "murder", "cannibalism"}
NAME_NOISE = {"mr", "mrs", "ms", "dr", "jr", "sr", "ii", "iii", "iv"}


def is_redacted_placeholder(name: str) -> bool:
    n = name.lower()
    if "[redacted]" in n or "redacted" in n:
        return True
    if "jane doe" in n or "john doe" in n:
        return True
    if "victim" in n or re.search(r"\bdoe\b", n):
        return True
    return False


def normalize_name(name: str) -> str:
    raw = re.sub(r"\s+", " ", name.strip())
    if not raw:
        return ""

    if is_redacted_placeholder(raw):
        placeholder = raw.replace("[", "").replace("]", "")
        placeholder = re.sub(r"\s+", " ", placeholder).strip(" \t-_,;:")
        return placeholder.title() if placeholder else ""

    name = raw
    name = re.sub(r"^[\W_]+|[\W_]+$", "", name)
    parts = [p for p in re.split(r"\s+", name) if p]
    cleaned = []
    for part in parts:
        p = re.sub(r"[^A-Za-z\-']", "", part)
        if not p:
            continue
        if p.lower().rstrip(".") in NAME_NOISE:
            continue
        cleaned.append(p)

    if len(cleaned) < 2:
        return ""

    return " ".join(cleaned).title()


def text_has_keyword(text: str, keyword: str) -> bool:
    pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
    return re.search(pattern, text) is not None


def categories_in_text(text: str):
    t = text.lower()
    found = set()
    for key, cfg in CATEGORIES.items():
        if key in {"victim", "lawyer"}:
            continue
        for kw in cfg["keywords"]:
            if text_has_keyword(t, kw):
                found.add(key)
                break
    return found


def load_role_sets(path: Path):
    victims = set()
    lawyers = set()
    bad_actors = set()
    if not path.exists():
        return victims, lawyers, bad_actors
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            person = (r.get("person") or "").strip()
            is_victim = (r.get("victim") or "0").strip() == "1"
            is_lawyer = (r.get("lawyer") or "0").strip() == "1"
            is_perp = (r.get("perpetrator") or "0").strip() == "1"
            is_complicit = (r.get("complicit") or "0").strip() == "1"
            is_witness = (r.get("witness") or "0").strip() == "1"
            if person and is_victim:
                victims.add(person)
            if person and is_lawyer:
                lawyers.add(person)
            if person and (is_perp or is_complicit or is_witness):
                bad_actors.add(person)
    return victims, lawyers, bad_actors


def process_file(path: Path):
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return [], set()

    people = data.get("entities", {}).get("people", [])
    if not isinstance(people, list):
        people = []

    text = data.get("full_text") or ""
    if not isinstance(text, str):
        text = ""

    cats = categories_in_text(text)

    names = []
    seen = set()
    for person in people:
        if not isinstance(person, str):
            continue
        n = normalize_name(person)
        if not n:
            continue
        if n in seen:
            continue
        seen.add(n)
        names.append(n)

    return names, cats


def parse_args():
    p = argparse.ArgumentParser(description="Build per-person category counts from epstein-docs JSON corpus")
    p.add_argument("--results-dir", default="epstein-docs/results")
    p.add_argument("--output", default="network_output/person_categories.csv")
    p.add_argument("--roles", default="network_output/person_roles.csv")
    return p.parse_args()


def main():
    args = parse_args()
    results_dir = Path(args.results_dir)
    out_path = Path(args.output)
    roles_path = Path(args.roles)

    if not results_dir.exists():
        raise SystemExit(f"Results directory not found: {results_dir}")

    person_counts = defaultdict(Counter)
    person_doc_count = Counter()
    victim_role_set, lawyer_role_set, bad_actor_role_set = load_role_sets(roles_path)

    json_files = list(results_dir.rglob("*.json"))
    docs_with_people = 0
    docs_with_cats = 0

    for fp in json_files:
        names, cats = process_file(fp)
        if names:
            docs_with_people += 1
        if cats:
            docs_with_cats += 1
        if not names:
            continue

        for n in names:
            person_doc_count[n] += 1
            for c in cats:
                if c in CRIME_CATEGORIES and n not in bad_actor_role_set:
                    continue
                person_counts[n][c] += 1
            if n in victim_role_set:
                person_counts[n]["victim"] += 1
            if n in lawyer_role_set:
                person_counts[n]["lawyer"] += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["person", "doc_count"] + list(CATEGORIES.keys())
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for person, doc_count in person_doc_count.most_common():
            row = [person, doc_count]
            counts = person_counts[person]
            for c in CATEGORIES.keys():
                row.append(counts.get(c, 0))
            w.writerow(row)

    print("Category build complete")
    print(f"JSON files scanned: {len(json_files)}")
    print(f"Docs with people: {docs_with_people}")
    print(f"Docs with >=1 category keyword: {docs_with_cats}")
    print(f"People written: {len(person_doc_count)}")
    print(f"Role-based victims loaded: {len(victim_role_set)}")
    print(f"Role-based lawyers loaded: {len(lawyer_role_set)}")
    print(f"Bad-actor role set loaded: {len(bad_actor_role_set)}")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
