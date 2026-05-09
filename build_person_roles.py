#!/usr/bin/env python3
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROLE_COLUMNS = ["victim", "perpetrator", "complicit", "witness", "lawyer"]
ALLEGATIONS_AS_PERPETRATOR = True

MANUAL_OVERRIDES = {
    "Jeffrey Epstein": {"perpetrator"},
    "Ghislaine Maxwell": {"perpetrator"},
    # Core legal actors in the corpus
    "Alison J Nathan": {"lawyer"},
    "Maurene Comey": {"lawyer"},
    "Lara Pomerantz": {"lawyer"},
    "Andrew Rohrbach": {"lawyer"},
    "Christian R Everdell": {"lawyer"},
    "Bobbi C Sternheim": {"lawyer"},
    "Jeffrey S Pagliuca": {"lawyer"},
    "Laura A Menninger": {"lawyer"},
    "Damian Williams": {"lawyer"},
    "Judge Nathan": {"lawyer"},
    "Audrey Strauss": {"lawyer"},
    # Victim-role overrides to prevent allegation-based perp mislabeling
    "Virginia Roberts": {"victim"},
    "Virginia Giuffre": {"victim"},
    "Virginia Roberts Giuffre": {"victim"},
    "Virginia L Giuffre": {"victim"},
    "Annie Farmer": {"victim"},
}

CRIME_KEYWORDS = {
    "sex_trafficking": ["sex trafficking", "trafficking", "sex trade", "commercial sex", "trafficked"],
    "rape": ["rape", "raped", "sexual assault", "assaulted"],
    "murder": ["murder", "homicide", "killed", "killing", "infanticide"],
    "cannibalism": ["cannibal", "cannibalism", "cannibalized", "cannibalisation", "cannibalization"],
}

NAME_NOISE = {"mr", "mrs", "ms", "dr", "jr", "sr", "ii", "iii", "iv"}
ACCUSATION_MARKERS = {
    "alleged",
    "allegedly",
    "accused",
    "charged",
    "indicted",
    "committed",
    "commits",
    "raped",
    "murdered",
    "killed",
    "trafficked",
    "abused",
    "assaulted",
    "force",
    "forced",
    "perpetrator",
}

NON_PERSON_NAME_PATTERNS = [
    r"\b(count|counts)\s+(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b",
    r"\bsex trafficking\b",
    r"\bsex trafficking conspiracy\b",
    r"\blaw enforcement\b",
    r"\blaw enforcement sensitive\b",
    r"\blimited official use only\b",
    r"\btime of incident\b",
    r"\bperson type\b",
    r"\bthe government\b",
    r"\bcriminal sexual activity\b",
    r"\bmann act\b",
    r"\bdistrict court\b",
    r"\bcourt of appeals\b",
]


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def victim_heuristic(name: str) -> bool:
    n = normalize(name)
    patterns = [
        r"\bvictim\b",
        r"\bminor victim\b",
        r"\bjane doe\b",
        r"\bjohn doe\b",
        r"\bdoe\s*(no\.?|number|#)?\s*\d*\b",
    ]
    return any(re.search(p, n) for p in patterns)


def lawyer_heuristic(name: str) -> bool:
    n = normalize(name)
    patterns = [
        r"\bjudge\b",
        r"\bjustice\b",
        r"\battorney\b",
        r"\bcounsel\b",
        r"\bprosecutor\b",
        r"\bdefense\b",
        r"\bau(sa|s)\b",
        r"\besq\b",
    ]
    return any(re.search(p, n) for p in patterns)


def is_redacted_placeholder(name: str) -> bool:
    n = name.lower()
    if "[redacted]" in n or "redacted" in n:
        return True
    if "jane doe" in n or "john doe" in n:
        return True
    if "victim" in n or re.search(r"\bdoe\b", n):
        return True
    return False


def is_likely_non_person_name(name: str) -> bool:
    n = normalize(name)
    if not n:
        return True
    for p in NON_PERSON_NAME_PATTERNS:
        if re.search(p, n):
            return True
    return False


def build_surname_alias_lookup(nodes_path: Path):
    """
    Build a map of surname -> most frequent canonical full name from nodes.csv.
    This lets 'Mr. Epstein' or plain 'Epstein' resolve to 'Jeffrey Epstein'.
    """
    best_name_by_surname = {}
    best_score_by_surname = defaultdict(int)

    with nodes_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = (r.get("label") or r.get("id") or "").strip()
            if not name:
                continue

            parts = [p for p in re.split(r"\s+", name) if p]
            if len(parts) < 2:
                continue

            surname = re.sub(r"[^A-Za-z\-']", "", parts[-1]).lower()
            if not surname or len(surname) < 4:
                continue
            if surname in NAME_NOISE:
                continue

            score_raw = (r.get("document_frequency") or "0").strip()
            try:
                score = int(score_raw)
            except Exception:
                score = 0

            if score >= best_score_by_surname[surname]:
                best_score_by_surname[surname] = score
                best_name_by_surname[surname] = name

    return best_name_by_surname


def build_canonical_name_lookup(nodes_path: Path):
    canonical = {}
    with nodes_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = (r.get("label") or r.get("id") or "").strip()
            if not name:
                continue
            canonical[normalize(name)] = name
    return canonical


def normalize_entity_name(name: str, surname_alias_lookup=None) -> str:
    raw = re.sub(r"\s+", " ", name.strip())
    if not raw:
        return ""

    if is_redacted_placeholder(raw):
        placeholder = raw.replace("[", "").replace("]", "")
        placeholder = re.sub(r"\s+", " ", placeholder).strip(" \t-_,;:")
        return placeholder.title() if placeholder else ""

    v = re.sub(r"^[\W_]+|[\W_]+$", "", raw)
    parts = [p for p in re.split(r"\s+", v) if p]
    cleaned = []
    for part in parts:
        p = re.sub(r"[^A-Za-z\-']", "", part)
        if not p:
            continue
        if p.lower().rstrip(".") in NAME_NOISE:
            continue
        cleaned.append(p)

    if not cleaned:
        return ""

    joined = " ".join(cleaned)
    if is_likely_non_person_name(joined):
        return ""

    if len(cleaned) >= 2:
        return joined.title()

    # Single-token entities are usually discarded, but keep them if they map
    # to a known surname in the corpus.
    if surname_alias_lookup:
        alias = surname_alias_lookup.get(cleaned[0].lower())
        if alias:
            return alias
    return ""


def text_has_keyword(text: str, keyword: str) -> bool:
    pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
    return re.search(pattern, text) is not None


def crime_categories_in_text(text: str):
    t = (text or "").lower()
    found = set()
    for crime, kws in CRIME_KEYWORDS.items():
        for kw in kws:
            if text_has_keyword(t, kw):
                found.add(crime)
                break

    # Pattern-based cues for sexual exploitation scenarios that may not use exact keywords.
    pay_for_sex = re.search(r"\b(pay|paid|paying|payment)\b.{0,80}\b(sex|sexual|intercourse)\b", t) or re.search(
        r"\b(sex|sexual|intercourse)\b.{0,50}\b(pay|paid|paying|payment)\b", t
    )
    forced_sex = re.search(r"\b(force|forced|coerce|coerced)\b.{0,80}\b(sex|sexual|intercourse)\b", t) or re.search(
        r"\b(sex|sexual|intercourse)\b.{0,50}\b(force|forced|coerce|coerced)\b", t
    )
    pay_to_force = re.search(r"\b(pay|paid|paying|payment)\b.{0,80}\b(force|forced|coerce|coerced)\b", t) or re.search(
        r"\b(force|forced|coerce|coerced)\b.{0,80}\b(pay|paid|paying|payment)\b", t
    )
    minor_cue = re.search(r"\b(minor|underage|child|children|13|14|15|16|17)\b", t)
    if (pay_for_sex or forced_sex or pay_to_force) and minor_cue:
        found.add("sex_trafficking")
        found.add("rape")
    return found


def split_sentences(text: str):
    if not text:
        return []
    # Simple sentence splitter for noisy OCR text.
    parts = re.split(r"(?<=[\.\!\?\n])\s+", text)
    return [p.strip() for p in parts if p and p.strip()]


def has_accusation_marker(sentence_lower: str) -> bool:
    return any(m in sentence_lower for m in ACCUSATION_MARKERS)


def person_mentioned_in_sentence(person: str, sentence_lower: str) -> bool:
    p = person.lower()
    if p in sentence_lower:
        return True
    toks = p.split()
    if not toks:
        return False
    last = toks[-1]
    # Fall back to surname mention only for reasonably specific surnames.
    if len(last) >= 6 and re.search(rf"\b{re.escape(last)}\b", sentence_lower):
        return True
    return False


def extract_contact_known_blocks(text: str, surname_alias_lookup=None):
    """
    Extract structured form blocks:
      First Name: X
      ...
      Last Name: Y
      ...
      How is Contact Known: <statement...>
    Returns list[(person_name, statement)].
    """
    blocks = []
    if not text:
        return blocks
    pattern = re.compile(
        r"First Name:\s*(?P<first>[^\n\r]+).*?"
        r"Last Name:\s*(?P<last>[^\n\r]+).*?"
        r"How is Contact Known:\s*(?P<known>.*?)(?:\nType:|\nAddress:|\nCity:|\nZip:|$)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(text):
        first = re.sub(r"\s+", " ", (m.group("first") or "").strip())
        last = re.sub(r"\s+", " ", (m.group("last") or "").strip())
        person = normalize_entity_name(f"{first} {last}".strip(), surname_alias_lookup=surname_alias_lookup)
        known = re.sub(r"\s+", " ", (m.group("known") or "").strip())
        if person and known:
            blocks.append((person, known))
    return blocks


def extract_titled_surname_aliases(full_text: str, surname_alias_lookup):
    if not full_text or not surname_alias_lookup:
        return set()
    found = set()
    for m in re.finditer(r"\b(?:mr|mrs|ms|dr)\.?\s+([A-Za-z][A-Za-z\-']{2,})\b", full_text, flags=re.IGNORECASE):
        surname = (m.group(1) or "").lower()
        alias = surname_alias_lookup.get(surname)
        if alias:
            found.add(alias)
    return found


def extract_candidate_names_from_text(full_text: str, surname_alias_lookup, canonical_name_lookup):
    if not full_text:
        return set()

    found = set()
    found.update(extract_titled_surname_aliases(full_text, surname_alias_lookup))

    patterns = [
        r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z\-']+){1,3}\b",
        r"\b[A-Z]{2,}(?:\s+[A-Z]{2,}){1,3}\b",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, full_text):
            candidate = m.group(0).strip()
            n = normalize_entity_name(candidate, surname_alias_lookup=surname_alias_lookup)
            if not n:
                continue
            canonical = canonical_name_lookup.get(normalize(n))
            if canonical:
                found.add(canonical)

    return found


def process_text_for_crime_counts(full_text: str, extracted_names: set, person_crime_counts, surname_alias_lookup=None):
    if not full_text:
        return
    full_lower = full_text.lower()
    doc_minor_cue = re.search(r"\b(minor|underage|child|children|13|14|15|16|17)\b", full_lower) is not None

    if extracted_names:
        for sent in split_sentences(full_text):
            sent_lower = sent.lower()
            crimes = crime_categories_in_text(sent)
            if not crimes:
                continue
            if not has_accusation_marker(sent_lower):
                continue

            for n in extracted_names:
                if not person_mentioned_in_sentence(n, sent_lower):
                    continue
                for c in crimes:
                    person_crime_counts[n][c] += 1

    # Structured intake forms can use pronouns in accusation lines.
    # Bind "How is Contact Known" statements to the form person directly.
    for person, statement in extract_contact_known_blocks(full_text, surname_alias_lookup=surname_alias_lookup):
        statement_lower = statement.lower()
        crimes = crime_categories_in_text(statement)
        pay_to_force = re.search(
            r"\b(pay|paid|paying|payment)\b.{0,80}\b(force|forced|coerce|coerced)\b",
            statement_lower,
        ) or re.search(
            r"\b(force|forced|coerce|coerced)\b.{0,80}\b(pay|paid|paying|payment)\b",
            statement_lower,
        )
        if pay_to_force and doc_minor_cue:
            crimes.add("sex_trafficking")
            crimes.add("rape")
        if not crimes:
            continue
        if not has_accusation_marker(statement_lower):
            continue
        for c in crimes:
            # Strongly weight direct "How is Contact Known" accusation blocks.
            person_crime_counts[person][c] += 2


def build_crime_context_counts(
    results_dir: Path,
    surname_alias_lookup,
    canonical_name_lookup,
    extra_text_dir: Path | None = None,
):
    person_crime_counts = defaultdict(Counter)
    if not results_dir.exists():
        return person_crime_counts

    for fp in results_dir.rglob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue

        people = data.get("entities", {}).get("people", [])
        if not isinstance(people, list):
            continue
        full_text = data.get("full_text") or ""
        if not isinstance(full_text, str):
            full_text = ""

        names = set()
        for person in people:
            if not isinstance(person, str):
                continue
            n = normalize_entity_name(person, surname_alias_lookup=surname_alias_lookup)
            if n:
                names.add(canonical_name_lookup.get(normalize(n), n))

        names.update(extract_titled_surname_aliases(full_text, surname_alias_lookup))

        if not names:
            continue

        process_text_for_crime_counts(full_text, names, person_crime_counts, surname_alias_lookup=surname_alias_lookup)

    if extra_text_dir and extra_text_dir.exists():
        for fp in extra_text_dir.rglob("*.txt"):
            try:
                txt = fp.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            names = extract_candidate_names_from_text(txt, surname_alias_lookup, canonical_name_lookup)
            process_text_for_crime_counts(txt, names, person_crime_counts, surname_alias_lookup=surname_alias_lookup)

    return person_crime_counts


def parse_args():
    p = argparse.ArgumentParser(description="Build role labels per person for graph filtering")
    p.add_argument("--nodes", default="network_output/nodes.csv")
    p.add_argument("--output", default="network_output/person_roles.csv")
    p.add_argument("--results-dir", default="epstein-docs/results")
    p.add_argument("--extra-text-dir", default="source_docs")
    p.add_argument("--complicit-threshold", type=int, default=2)
    return p.parse_args()


def main():
    args = parse_args()
    nodes_path = Path(args.nodes)
    out_path = Path(args.output)
    results_dir = Path(args.results_dir)
    extra_text_dir = Path(args.extra_text_dir)

    if not nodes_path.exists():
        raise SystemExit(f"nodes.csv not found: {nodes_path}")

    surname_alias_lookup = build_surname_alias_lookup(nodes_path)
    canonical_name_lookup = build_canonical_name_lookup(nodes_path)
    crime_context_counts = build_crime_context_counts(
        results_dir,
        surname_alias_lookup=surname_alias_lookup,
        canonical_name_lookup=canonical_name_lookup,
        extra_text_dir=extra_text_dir,
    )

    rows = []
    with nodes_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = (r.get("label") or r.get("id") or "").strip()
            if not name:
                continue

            roles = set()
            sources = []

            if victim_heuristic(name):
                roles.add("victim")
                sources.append("heuristic:victim-pattern")
            if lawyer_heuristic(name):
                roles.add("lawyer")
                sources.append("heuristic:lawyer-pattern")

            for k, vals in MANUAL_OVERRIDES.items():
                if normalize(name) == normalize(k):
                    roles.update(vals)
                    sources.append("manual:override")

            if (
                "victim" not in roles
                and "lawyer" not in roles
                and "perpetrator" not in roles
                and "witness" not in roles
                and "complicit" not in roles
            ):
                crime_hits = sum(crime_context_counts.get(name, {}).values())
                if crime_hits >= args.complicit_threshold:
                    if ALLEGATIONS_AS_PERPETRATOR:
                        roles.add("perpetrator")
                        sources.append(f"heuristic:crime-context->perpetrator>={args.complicit_threshold}")
                    else:
                        roles.add("complicit")
                        sources.append(f"heuristic:crime-context->complicit>={args.complicit_threshold}")

            # Victim precedence: victims are not auto-labeled as perpetrators/complicit/witness.
            if "victim" in roles:
                roles.discard("perpetrator")
                roles.discard("complicit")
                roles.discard("witness")
                sources.append("rule:victim-precedence")

            if not roles:
                roles = {"unknown"}
                sources = ["default:unknown"]

            rows.append(
                {
                    "person": name,
                    "roles": "|".join(sorted(roles)),
                    "victim": "1" if "victim" in roles else "0",
                    "perpetrator": "1" if "perpetrator" in roles else "0",
                    "complicit": "1" if "complicit" in roles else "0",
                    "witness": "1" if "witness" in roles else "0",
                    "lawyer": "1" if "lawyer" in roles else "0",
                    "unknown": "1" if "unknown" in roles else "0",
                    "source": "|".join(sorted(set(sources))),
                }
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        fieldnames = ["person", "roles", "victim", "perpetrator", "complicit", "witness", "lawyer", "unknown", "source"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} people to {out_path}")


if __name__ == "__main__":
    main()
