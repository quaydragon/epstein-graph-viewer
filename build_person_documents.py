#!/usr/bin/env python3
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

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

    name = re.sub(r"^[\W_]+|[\W_]+$", "", raw)
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


def parse_args():
    p = argparse.ArgumentParser(description="Build person -> source documents index")
    p.add_argument("--results-dir", default="epstein-docs/results")
    p.add_argument("--output", default="network_output/person_documents.json")
    return p.parse_args()


def main():
    args = parse_args()
    results_dir = Path(args.results_dir)
    out_path = Path(args.output)

    if not results_dir.exists():
        raise SystemExit(f"results dir not found: {results_dir}")

    person_docs = defaultdict(dict)
    total_docs = 0

    for fp in results_dir.rglob("*.json"):
        total_docs += 1
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue

        people = data.get("entities", {}).get("people", [])
        if not isinstance(people, list):
            continue

        doc_name = fp.name
        doc_id = doc_name[:-5] if doc_name.endswith(".json") else doc_name
        rel = fp.relative_to(results_dir.parent).as_posix()  # e.g. results/IMAGES.../X.json

        seen = set()
        for person in people:
            if not isinstance(person, str):
                continue
            n = normalize_name(person)
            if not n or n in seen:
                continue
            seen.add(n)
            person_docs[n][doc_id] = rel

    out = {}
    for person, docs in person_docs.items():
        ordered = sorted(docs.items())
        out[person] = {
            "count": len(ordered),
            "docs": [{"doc_id": d, "path": p} for d, p in ordered],
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=True), encoding="utf-8")

    print(f"Indexed people: {len(out)}")
    print(f"Scanned JSON docs: {total_docs}")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
