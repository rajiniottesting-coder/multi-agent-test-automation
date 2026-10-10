"""Agent 0's analysis: seeds -> candidates -> short list -> ranked report.

Pure functions over the impact graph (core/impact_graph.py): no tracker, no
repository host, no model calls. agents/agent0_impact.py does the I/O and the
two model calls (ChangeSeeds, ImpactAssessment) and hands their results here.

Stages (design section 7):
  2  seeds        code_change_seeds (two repository roots), drift_seeds
                  (nightly inventory report), validate_requirement_seeds
                  (the model's ChangeSeeds, checked against the inventory)
  3  layer 1      structural_candidates: scenarios the graph links to a seed
  4  layer 2      semantic_candidates: scenarios on the story's Components the
                  graph did not reach; shortlist() applies the cap rule
  5  layer 3      checked_assessments: the model's tiers, with any reason that
                  cites no checkable evidence dropped
  6  rank         rank(): deterministic weighted score and tier
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# Structural evidence strength (stage 3): a direct link scores higher.
DIRECT_ELEMENT = 1.0          # a changed element the scenario uses
PAGE_METHOD = 0.9             # a changed method of a page the scenario calls
SHARED_METHOD = 0.5           # a changed shared-base method: reaches nearly everything
PAGE_ONLY = 0.4               # the scenario visits a changed / unreachable page
TIER_SCORE = {"must-update": 1.0, "review": 0.5, "unaffected": 0.0}


@dataclass
class Seeds:
    elements: set = field(default_factory=set)       # {(page, key)}
    methods: set = field(default_factory=set)        # {(class, method)}
    pages: set = field(default_factory=set)          # {page}
    components: set = field(default_factory=set)
    behaviours: list = field(default_factory=list)
    dropped: list = field(default_factory=list)      # invented keys, reported

    def empty(self) -> bool:
        return not (self.elements or self.methods or self.pages or self.components)


@dataclass
class Candidate:
    id: str
    ref: str                          # scenario identity (test case key or file::title)
    test_case_key: Optional[str]
    file: str
    title: str
    steps: list
    layer: int                        # 1 structural, 2 semantic
    structural: float = 0.0
    component: float = 0.0
    semantic: float = 0.0
    paths: list = field(default_factory=list)       # [{"id": "P1", "text": ...}]
    owner: Optional[str] = None
    blocked_by: list = field(default_factory=list)  # in-flight stories (D4)


# ─────────────────────────────────────────────────────────────
# Stage 0 - content hash
# ─────────────────────────────────────────────────────────────

def content_hash(*parts) -> str:
    text = json.dumps(parts, sort_keys=True, default=sorted)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────
# Stage 2 - seeds
# ─────────────────────────────────────────────────────────────

def _inventory(root: Path) -> dict:
    from core.impact_graph import _load_inventory
    return _load_inventory(Path(root), None)


def _methods_of(root: Path) -> dict:
    """{(class, method): (normalised source, argument names)} for pages/*.py."""
    out = {}
    pages = Path(root) / "pages"
    for path in sorted(pages.glob("*.py")) if pages.is_dir() else []:
        if path.name.startswith("_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        body = ast.dump(ast.Module(body=item.body, type_ignores=[]))
                        args = tuple(a.arg for a in item.args.args)
                        out[(node.name, item.name)] = (body, args)
    return out


def code_change_seeds(base_root: Path, head_root: Path) -> Seeds:
    """Seeds from a code change, without a model: page methods whose body or
    signature changed or that were removed, and inventory elements whose
    selector changed or that were removed. Added things impact no existing test."""
    seeds = Seeds()
    base_m, head_m = _methods_of(base_root), _methods_of(head_root)
    for ref, (body, args) in base_m.items():
        if ref not in head_m or head_m[ref] != (body, args):
            seeds.methods.add(ref)
    base_i, head_i = _inventory(base_root), _inventory(head_root)
    for page, spec in base_i.items():
        head_elements = (head_i.get(page) or {}).get("elements", {})
        if page not in head_i:
            seeds.pages.add(page)
        for key, value in (spec.get("elements") or {}).items():
            if key not in head_elements or head_elements[key] != value:
                seeds.elements.add((page, key))
    return seeds


def drift_seeds(report: dict) -> Seeds:
    """Seeds from scripts/check_inventory_staleness.py --json output."""
    seeds = Seeds()
    for page, diff in (report.get("pages") or {}).items():
        for item in (diff.get("missing") or []) + (diff.get("ambiguous") or []):
            element = item.get("element") if isinstance(item, dict) else item
            if element:
                seeds.elements.add((page, element))
    seeds.pages.update(report.get("unreachable_pages") or [])
    return seeds


def validate_requirement_seeds(change, graph, story_components: Iterable[str]) -> Seeds:
    """The model's ChangeSeeds, checked: an element key that does not exist in
    the inventory is dropped and reported, exactly as the generation gate
    rejects invented keys. A bare key resolves to every page that has it."""
    seeds = Seeds(behaviours=list(change.behaviours),
                  components=set(story_components) | set(change.components))
    by_key: dict = {}
    for page, key in graph.inventory_elements:
        by_key.setdefault(key, set()).add(page)
    for raw in change.element_keys:
        raw = raw.strip()
        if ":" in raw:
            page, key = raw.split(":", 1)
            if (page.strip(), key.strip()) in graph.inventory_elements:
                seeds.elements.add((page.strip(), key.strip()))
                continue
        elif raw in by_key:
            seeds.elements.update((p, raw) for p in by_key[raw])
            continue
        seeds.dropped.append(raw)
    return seeds


# ─────────────────────────────────────────────────────────────
# Stage 3 - layer 1
# ─────────────────────────────────────────────────────────────

def _receivers(graph, cls: str) -> set:
    return {c for c in graph._bases if cls in graph._mro(c)} | {cls}


def structural_candidates(graph, seeds: Seeds) -> list:
    out = []
    for s in graph.scenarios:
        paths, score = [], 0.0
        for page, key in sorted(seeds.elements & s.elements):
            users = sorted(f"{c}.{m}" for c, m in s.methods | s.shared_methods
                           if _reads(graph, c, m, key))
            paths.append(f"element {page}:{key} <- {', '.join(users) or 'a page method'} <- scenario")
            score = max(score, DIRECT_ELEMENT)
        for cls, name in sorted(seeds.methods):
            recv = _receivers(graph, cls)
            if any(m == name and c in recv for c, m in s.methods):
                paths.append(f"method {cls}.{name} <- step definition <- scenario")
                score = max(score, PAGE_METHOD)
            elif any(m == name and c in recv for c, m in s.shared_methods):
                paths.append(f"shared method {cls}.{name} <- page method <- scenario")
                score = max(score, SHARED_METHOD)
        for page in sorted(seeds.pages & set(s.pages)):
            paths.append(f"page {page} <- scenario")
            score = max(score, PAGE_ONLY)
        if paths:
            out.append(_candidate(s, 1, score, paths))
    return out


def _def_of(graph, cls: str, name: str):
    for c in graph._mro(cls):
        if (c, name) in graph.page_methods:
            return (c, name)
    return None


def _reads(graph, cls: str, name: str, key: str) -> bool:
    """Whether page method cls.name reads element `key` (evidence text only).

    An unresolved method is False here and that drops nothing: a scenario's
    elements come only from methods the graph resolved, so it cannot be the
    one that matched, and the graph already recorded it in `gaps`
    (unknown_method / unknown_page_class) when it was built."""
    found = _def_of(graph, cls, name)
    return found is not None and key in graph.page_methods[found].keys


def _candidate(s, layer: int, structural: float, paths: list) -> Candidate:
    return Candidate(id="", ref=s.ref, test_case_key=s.jira_key, file=s.file, title=s.title,
                     steps=[f"{k} {p}" for k, p in s.steps], layer=layer,
                     structural=structural, owner=s.owner,
                     paths=[{"id": f"P{i + 1}", "text": t} for i, t in enumerate(paths)])


# ─────────────────────────────────────────────────────────────
# Stage 4 - layer 2 and the short-list rule
# ─────────────────────────────────────────────────────────────

def semantic_candidates(graph, components: Iterable[str], exclude: set) -> tuple:
    """(candidates, no_component). With no Component, the whole suite."""
    components = [c for c in components if c]
    if components:
        pool = {s.ref: s for c in components for s in graph.scenarios_in_component(c)}
        scenarios = list(pool.values())
    else:
        scenarios = list(graph.scenarios)
    return ([_candidate(s, 2, 0.0, []) for s in scenarios if s.ref not in exclude],
            not components)


def relevance(story_text: str, cand: Candidate) -> float:
    from agents.agent2_coder import _title_similarity
    return _title_similarity(story_text, cand.title + " " + " ".join(cand.steps))


def shortlist(layer1: list, layer2: list, story_text: str, max_candidates: int) -> tuple:
    """(judged, not_judged). Layer 1 is always judged; layer 2 fills the
    remaining places, most relevant first (no model, same order every time);
    the rest is reported, never hidden."""
    for c in layer1 + layer2:
        c.semantic = relevance(story_text, c)
    ranked2 = sorted(layer2, key=lambda c: (-c.semantic, c.ref))
    room = max(0, max_candidates - len(layer1))
    judged = list(layer1) + ranked2[:room]
    for n, c in enumerate(judged, 1):
        c.id = f"C{n}"
    return judged, ranked2[room:]


def chunks(items: list, size: int) -> list:
    size = max(1, size)
    return [items[i:i + size] for i in range(0, len(items), size)] or [[]]


# ─────────────────────────────────────────────────────────────
# Stage 5 - layer 3 evidence check
# ─────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().strip('"').lower())


def checked_assessments(assessment, candidates: list) -> tuple:
    """({candidate id: (tier, reason, evidence)}, [dropped notes]).

    An assessment counts only if it names a supplied candidate and cites at
    least one checkable piece of evidence: a path id given for it, or a step
    quoted verbatim from its scenario. The model cannot add a candidate."""
    by_id = {c.id: c for c in candidates}
    kept, dropped = {}, []
    for a in assessment.assessments:
        cand = by_id.get(a.candidate_id)
        if cand is None:
            dropped.append(f"{a.candidate_id}: not a supplied candidate")
            continue
        path_ids = {p["id"] for p in cand.paths}
        steps = {_norm(st) for st in cand.steps} | {_norm(st.split(" ", 1)[-1]) for st in cand.steps}
        valid = [e for e in a.evidence_refs if e in path_ids or _norm(e) in steps]
        if not valid:
            dropped.append(f"{a.candidate_id}: reason cites no checkable evidence")
            continue
        kept[a.candidate_id] = (a.tier, a.reason, valid)
    return kept, dropped


# ─────────────────────────────────────────────────────────────
# Stage 6 - rank
# ─────────────────────────────────────────────────────────────

def component_match(cand: Candidate, graph, components: Iterable[str]) -> float:
    wanted = {c.strip().lower() for c in components if c}
    if not wanted:
        return 0.0
    s = next((x for x in graph.scenarios if x.ref == cand.ref), None)
    return 1.0 if s and {c.lower() for c in s.components} & wanted else 0.0


def rank(candidates: list, judgements: dict, weights: dict, thresholds: dict,
         signals: Iterable[str] = ("structural", "component", "semantic", "adjudicated")) -> list:
    """Deterministic score and tier per candidate, highest first.

    Signals a trigger cannot produce (a code change has no semantic or
    adjudicated signal) are left out and the remaining weights renormalised,
    so a direct structural hit still reaches must-update."""
    signals = list(signals)
    total = sum(weights[s] for s in signals) or 1.0
    rows = []
    for c in candidates:
        tier_j, reason, evidence = judgements.get(c.id, (None, "", []))
        values = {"structural": c.structural, "component": c.component,
                  "semantic": c.semantic,
                  "adjudicated": TIER_SCORE.get(tier_j, 0.0) if tier_j else 0.0}
        score = round(sum(weights[s] * values[s] for s in signals) / total, 3)
        if tier_j == "unaffected":
            tier = "unaffected"          # the model saw the scenario and cleared it
        elif score >= thresholds["must_update"]:
            tier = "must-update"
        elif score >= thresholds["review"]:
            tier = "review"
        else:
            tier = "unaffected"
        rows.append({"id": c.id, "ref": c.ref, "key": c.test_case_key, "file": c.file,
                     "title": c.title, "owner": c.owner, "layer": c.layer, "score": score,
                     "tier": tier, "reason": reason,
                     "evidence": "; ".join(p["text"] for p in c.paths) or reason,
                     "blocked_by": list(c.blocked_by)})
    return sorted(rows, key=lambda r: (-r["score"], r["ref"]))


# ─────────────────────────────────────────────────────────────
# The report, as stored and compared (D4)
# ─────────────────────────────────────────────────────────────

REPORT_OPEN, REPORT_CLOSE = "{code:json}", "{code}"


def report_dict(change_ref: str, chash: str, graph_sha: str, ranked: list,
                not_judged: list, no_component: bool, seeds: Seeds, dropped: list) -> dict:
    return {"change_ref": change_ref, "content_hash": chash, "graph_sha": graph_sha,
            "ranked": [r for r in ranked if r["tier"] != "unaffected"],
            "unaffected": [r for r in ranked if r["tier"] == "unaffected"],
            "not_judged": [{"ref": c.ref, "key": c.test_case_key, "file": c.file,
                            "title": c.title} for c in not_judged],
            "no_component": no_component,
            "seeds": {"elements": sorted(f"{p}:{k}" for p, k in seeds.elements),
                      "methods": sorted(f"{c}.{m}" for c, m in seeds.methods),
                      "pages": sorted(seeds.pages), "dropped": seeds.dropped},
            "dropped_assessments": dropped}


def embed(report: dict) -> str:
    return REPORT_OPEN + "\n" + json.dumps(report, indent=1) + "\n" + REPORT_CLOSE


def extract(text: str) -> Optional[dict]:
    m = re.search(r"\{code:json\}\n(.*?)\n\{code\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    return data if isinstance(data, dict) and "content_hash" in data else None


def delta(previous: dict, current: dict) -> dict:
    """What changed between two reports: additions, removals, tier changes."""
    old = {r["ref"]: r for r in previous.get("ranked", [])}
    new = {r["ref"]: r for r in current.get("ranked", [])}
    return {"added": [new[k] for k in sorted(set(new) - set(old))],
            "removed": [old[k] for k in sorted(set(old) - set(new))],
            "tier_changed": [{"ref": k, "from": old[k]["tier"], "to": new[k]["tier"]}
                             for k in sorted(set(old) & set(new))
                             if old[k]["tier"] != new[k]["tier"]]}


def outcome(predicted: Iterable[str], actual: Iterable[str]) -> dict:
    """Recall and precision of a prediction against what really changed."""
    p, a = set(predicted), set(actual)
    hit = p & a
    return {"predicted": sorted(p), "actual": sorted(a),
            "recall": round(len(hit) / len(a), 3) if a else None,
            "precision": round(len(hit) / len(p), 3) if p else None}
