"""Apply reviewed, preconditioned source corrections to the data projection.

These patches change data only. A changed upstream projection must be reviewed
again rather than silently accepting a correction against different input.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path


def digest(value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def apply_patches(data, pdf_sha256):
    reports = []
    directory = Path(__file__).resolve().parents[1] / "corrections"
    for path in sorted(directory.glob("*.json")):
        policy = json.loads(path.read_text(encoding="utf-8"))
        if policy["official_pdf_sha256"] != pdf_sha256:
            raise ValueError(f"Official source changed: {path.name}")
        for patch in policy["records"]:
            candidates = data[patch["file"]][patch["kind"]]
            matches = [record for record in candidates if all(record.get(k) == v for k, v in patch["identity"].items())]
            if len(matches) != 1:
                raise ValueError(f"Ambiguous correction: {path.name}: {patch['identity']}")
            record = matches[0]
            if digest(record) != patch["projected_record_sha256"]:
                raise ValueError(f"Correction input changed: {path.name}: {patch['identity']}")
            for edit in patch["edits"]:
                parts = edit["path"].strip("/").split("/")
                parent = record
                for key in parts[:-1]:
                    parent = parent[int(key)] if isinstance(parent, list) else parent[key]
                key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
                if edit.get("remove"):
                    del parent[key]
                else:
                    parent[key] = copy.deepcopy(edit["value"])
            reports.append({"file": patch["file"], "kind": patch["kind"],
                            "identity": patch["identity"], "official_pages": patch["official_pages"],
                            "policy": path.name, "source_evidence": patch["evidence"],
                            "patch_result_sha256": digest(record)})
    return reports
