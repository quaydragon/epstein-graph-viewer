#!/usr/bin/env python3
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import build_person_roles as roles


SEVERITY = {
    "murder": 100,
    "cannibalism": 90,
    "rape": 75,
    "sex_trafficking": 65,
    "politics": 15,
    "science": 10,
    "philanthropy": 10,
}


def clean_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    text = re.sub(r"^Case\s+\S+\s+Document\s+\S+\s+Filed\s+\S+\s+Page\s+\S+\s*", "", text, flags=re.IGNORECASE)
    return text[:420]


def snippet(text: str, limit: int = 170) -> str:
    text = clean_sentence(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def score_sentence(sentence: str, crimes: set[str]) -> int:
    score = sum(SEVERITY.get(c, 0) for c in crimes)
    score += min(len(sentence) // 80, 5)
    return score


def load_role_map(path: Path):
    role_map = {}
    if not path.exists():
        return role_map
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            person = (row.get("person") or "").strip()
            if person:
                role_map[roles.normalize(person)] = row
    return role_map


def load_category_map(path: Path):
    category_map = {}
    if not path.exists():
        return category_map
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            person = (row.get("person") or "").strip()
            if person:
                category_map[roles.normalize(person)] = row
    return category_map


def role_label(role_row):
    if not role_row:
        return "unknown"
    for key in ("victim", "perpetrator", "complicit", "witness", "lawyer"):
        if (role_row.get(key) or "0") == "1":
            return key
    return "unknown"


def category_label(key: str) -> str:
    return {
        "sex_trafficking": "sex trafficking",
        "rape": "rape",
        "murder": "murder",
        "cannibalism": "cannibalism",
        "politics": "politics",
        "science": "science",
        "philanthropy": "philanthropy",
    }.get(key, key.replace("_", " "))


def fallback_summary(person: str, role_row, category_row):
    role = role_label(role_row)
    if role == "victim":
        return (
            f"Linked documents primarily place {person} in victim-related contexts. "
            "This is a document-derived heuristic summary, not an adjudicated finding."
        )
    if role == "lawyer":
        return (
            f"Linked documents primarily place {person} in legal or court-related contexts. "
            "This is a document-derived heuristic summary, not an adjudicated finding."
        )

    return (
        f"No strong allegation-context paragraph is currently available for {person} from the extracted text in this corpus. "
        "This is a document-derived heuristic summary, not an adjudicated finding."
    )


def build_summary(person: str, role_row, category_row, items: list[dict]):
    if not items:
        return fallback_summary(person, role_row, category_row)

    crime_counts = Counter()
    for item in items:
        for crime in item["crimes"]:
            crime_counts[crime] += 1
    ranked = sorted(crime_counts.items(), key=lambda item: (-SEVERITY.get(item[0], 0), -item[1], item[0]))
    crime_text = ", ".join(category_label(key) for key, _ in ranked[:3])

    seen_sentences = set()
    top_items = []
    for item in sorted(items, key=lambda item: (-item["score"], item["doc_id"])):
        sentence_key = item["sentence"]
        if sentence_key in seen_sentences:
            continue
        seen_sentences.add(sentence_key)
        top_items.append(item)
        if len(top_items) >= 3:
            break
    excerpt_text = " ".join(snippet(item["sentence"]) for item in top_items if item["sentence"])

    return (
        f"In linked documents, {person} appears in allegation contexts involving {crime_text}. "
        f"The most severe linked passages include: {excerpt_text} "
        "This is a document-derived heuristic summary, not an adjudicated finding."
    )


def parse_args():
    p = argparse.ArgumentParser(description="Build per-person allegation summary paragraphs from linked documents.")
    p.add_argument("--results-dir", default="epstein-docs/results")
    p.add_argument("--roles", default="network_output/person_roles.csv")
    p.add_argument("--categories", default="network_output/person_categories.csv")
    p.add_argument("--output", default="network_output/person_summaries.json")
    return p.parse_args()


def main():
    args = parse_args()
    results_dir = Path(args.results_dir)
    roles_path = Path(args.roles)
    categories_path = Path(args.categories)
    out_path = Path(args.output)

    surname_alias_lookup = roles.build_surname_alias_lookup(Path("network_output/nodes.csv"))
    canonical_name_lookup = roles.build_canonical_name_lookup(Path("network_output/nodes.csv"))
    role_map = load_role_map(roles_path)
    category_map = load_category_map(categories_path)
    person_items = defaultdict(list)

    for fp in results_dir.rglob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue

        text = data.get("full_text") or ""
        if not isinstance(text, str) or not text.strip():
            continue

        names = set()
        for person in data.get("entities", {}).get("people", []) or []:
            if not isinstance(person, str):
                continue
            normalized = roles.normalize_entity_name(person, surname_alias_lookup=surname_alias_lookup)
            if normalized:
                names.add(canonical_name_lookup.get(roles.normalize(normalized), normalized))
        names.update(roles.extract_titled_surname_aliases(text, surname_alias_lookup))

        if not names:
            continue

        for sent in roles.split_sentences(text):
            sent_lower = sent.lower()
            crimes = roles.crime_categories_in_text(sent)
            if not crimes or not roles.has_accusation_marker(sent_lower):
                continue
            sentence_score = score_sentence(sent, crimes)
            clean = clean_sentence(sent)
            if not clean:
                continue

            for name in names:
                if not roles.person_mentioned_in_sentence(name, sent_lower):
                    continue
                person_items[name].append(
                    {
                        "doc_id": fp.stem,
                        "sentence": clean,
                        "crimes": sorted(crimes),
                        "score": sentence_score,
                    }
                )

    output = {}
    people = set(person_items) | {row_key for row_key in (canonical_name_lookup.values())}
    for person in people:
        role_row = role_map.get(roles.normalize(person))
        category_row = category_map.get(roles.normalize(person))
        items = person_items.get(person, [])
        summary = build_summary(person, role_row, category_row, items)
        output[person] = {
            "summary": summary,
            "role": role_label(role_row),
            "top_examples": [
                {"doc_id": item["doc_id"], "sentence": snippet(item["sentence"]), "crimes": item["crimes"]}
                for item in sorted(items, key=lambda item: (-item["score"], item["doc_id"]))[:3]
            ],
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=True), encoding="utf-8")
    print(f"Wrote {len(output)} summaries to {out_path}")


if __name__ == "__main__":
    main()
