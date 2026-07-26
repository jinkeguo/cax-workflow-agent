from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .result import ToolResult

APPLICATIONS = {"solidworks", "hypermesh", "abaqus"}
MAX_ERROR_TEXT = 20_000
MAX_CANDIDATES = 20
MAX_REGISTRY_BYTES = 1_000_000

OFFICIAL_DOMAINS = {
    "solidworks": (
        "help.solidworks.com",
        "www.3ds.com",
    ),
    "hypermesh": (
        "help.altair.com",
        "2025.help.altair.com",
        "community.altair.com",
    ),
    "abaqus": (
        "docs.software.vt.edu",
        "www.3ds.com",
    ),
}

COMMUNITY_DOMAINS = {
    "solidworks": ("my.solidworks.com", "3dswym.3dexperience.3ds.com"),
    "hypermesh": ("community.altair.com",),
    "abaqus": ("3dswym.3dexperience.3ds.com",),
}

SEARCH_SCOPES = {
    "solidworks": (
        "site:help.solidworks.com",
        "site:3ds.com/support",
        "site:my.solidworks.com",
    ),
    "hypermesh": (
        "site:help.altair.com/hwdesktop",
        "site:2025.help.altair.com/2025/hwdesktop",
        "site:community.altair.com",
    ),
    "abaqus": (
        "site:docs.software.vt.edu/abaqusv2025",
        "site:docs.software.vt.edu/abaqusv2024",
        "site:3ds.com/support",
    ),
}

STOPWORDS = {
    "error",
    "warning",
    "failed",
    "failure",
    "the",
    "and",
    "for",
    "from",
    "with",
    "this",
    "that",
    "was",
    "were",
    "has",
    "have",
    "not",
    "exit",
    "exited",
}

RISK_TERMS = re.compile(
    r"\b(material|modulus|strength|load|pressure|force|boundary|constraint|"
    r"contact|friction|cohesive|damage|geometry|thickness|section|stabilization)\b",
    re.IGNORECASE,
)


def _normalized_application(application: str) -> str:
    normalized = application.strip().lower()
    if normalized not in APPLICATIONS:
        raise ValueError(f"application must be one of {sorted(APPLICATIONS)}")
    return normalized


def _focused_signature(error_text: str) -> str:
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in error_text.splitlines()
        if line.strip()
    ]
    preferred = [
        line for line in lines
        if re.search(r"error|warning|fail|invalid|unable|not found|exception", line, re.I)
    ]
    selected = preferred[0] if preferred else (lines[0] if lines else "")
    return selected[:500]


def _fingerprint(application: str, stage: str | None, signature: str) -> str:
    payload = f"{application}\n{stage or ''}\n{signature.lower()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _keywords(text: str, limit: int = 12) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_./@-]{2,}", text.lower())
    seen: set[str] = set()
    result = []
    for word in words:
        normalized = word.strip("./")
        if normalized in STOPWORDS or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def prepare_failure_research(
    application: str,
    error_text: str,
    stage: str | None = None,
) -> ToolResult:
    started = time.monotonic()
    try:
        normalized = _normalized_application(application)
        if not error_text.strip():
            raise ValueError("error_text is required")
        if len(error_text) > MAX_ERROR_TEXT:
            raise ValueError(
                f"error_text exceeds {MAX_ERROR_TEXT} characters; provide a focused excerpt"
            )
        signature = _focused_signature(error_text)
        fingerprint = _fingerprint(normalized, stage, signature)
        quoted = signature.replace('"', "'")[:240]
        queries = [
            f'{scope} "{quoted}" {normalized}'
            for scope in SEARCH_SCOPES[normalized]
        ]
        queries.append(
            f'"{quoted}" {normalized} troubleshooting solution'
        )
        return ToolResult(
            status="succeeded",
            checks={
                "application": normalized,
                "stage": stage,
                "error_signature": signature,
                "fingerprint_sha256": fingerprint,
                "keywords": _keywords(error_text),
                "search_queries": queries,
                "preferred_domains": list(OFFICIAL_DOMAINS[normalized]),
                "research_contract": [
                    "Search official vendor documentation first.",
                    "Extract only the passage that directly explains the signature or recovery.",
                    "Keep the source URL, title, product version, and access date.",
                    "Treat forum or blog advice as a hypothesis until reproduced locally.",
                    "Do not change engineering intent while testing a proposed recovery.",
                ],
            },
            application={
                "name": "CAX Workflow failure research planner",
                "version": "0.1.0",
            },
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )


def _source_authority(application: str, url: str) -> tuple[int, str]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return 0, "invalid"
    host = parsed.hostname.lower()
    if any(host == domain or host.endswith(f".{domain}") for domain in OFFICIAL_DOMAINS[application]):
        if any(host == domain or host.endswith(f".{domain}") for domain in COMMUNITY_DOMAINS[application]):
            return 3, "official-community"
        return 4, "official-documentation"
    if any(
        host == domain or host.endswith(f".{domain}")
        for domains in OFFICIAL_DOMAINS.values()
        for domain in domains
    ):
        return 2, "other-vendor-documentation"
    return 1, "independent"


def _candidate_relevance(error_text: str, candidate: dict[str, Any]) -> float:
    error_terms = set(_keywords(error_text, limit=30))
    candidate_text = " ".join(
        str(candidate.get(key, ""))
        for key in ("title", "excerpt", "cause", "solution")
    )
    candidate_terms = set(_keywords(candidate_text, limit=80))
    if not error_terms:
        return 0.0
    return round(len(error_terms & candidate_terms) / len(error_terms), 3)


def evaluate_failure_research(
    application: str,
    error_text: str,
    candidates: list[dict[str, Any]],
    stage: str | None = None,
) -> ToolResult:
    started = time.monotonic()
    try:
        normalized = _normalized_application(application)
        if not error_text.strip():
            raise ValueError("error_text is required")
        if not candidates:
            raise ValueError("at least one research candidate is required")
        if len(candidates) > MAX_CANDIDATES:
            raise ValueError(f"no more than {MAX_CANDIDATES} candidates are allowed")

        ranked: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            url = str(candidate.get("url", "")).strip()
            title = str(candidate.get("title", "")).strip()
            excerpt = str(candidate.get("excerpt", "")).strip()
            actions = candidate.get("recommended_actions") or []
            if not url or not title or not excerpt:
                raise ValueError(
                    f"candidate {index} requires url, title, and excerpt"
                )
            if not isinstance(actions, list):
                raise ValueError(
                    f"candidate {index} recommended_actions must be an array"
                )
            authority, source_type = _source_authority(normalized, url)
            relevance = _candidate_relevance(error_text, candidate)
            ranked.append(
                {
                    "url": url,
                    "title": title[:300],
                    "excerpt": excerpt[:1000],
                    "cause": str(candidate.get("cause", "")).strip()[:1000],
                    "recommended_actions": [str(action)[:500] for action in actions],
                    "product_version": str(candidate.get("product_version", "")).strip()[:100],
                    "authority_score": authority,
                    "source_type": source_type,
                    "relevance_score": relevance,
                    "combined_score": round(authority + relevance, 3),
                }
            )
        ranked.sort(
            key=lambda item: (
                -item["combined_score"],
                -item["authority_score"],
                item["title"],
            )
        )
        usable = [
            item for item in ranked
            if item["authority_score"] > 0 and item["relevance_score"] > 0
        ]
        if not usable:
            return ToolResult(
                status="needs_input",
                checks={"ranked_sources": ranked},
                warnings=[
                    "No candidate has both a valid HTTPS source and direct keyword relevance."
                ],
                error="Provide a more directly relevant source excerpt.",
                elapsed_seconds=time.monotonic() - started,
            )

        best = usable[0]
        signature = _focused_signature(error_text)
        fingerprint = _fingerprint(normalized, stage, signature)
        actions = best["recommended_actions"]
        approval_required = any(RISK_TERMS.search(action) for action in actions)
        candidate_rule = {
            "code": f"web-{normalized}-{fingerprint[:12]}",
            "application": normalized,
            "stage": stage,
            "title": best["title"],
            "cause": best["cause"] or best["excerpt"],
            "signature_terms": [signature],
            "match_mode": "all",
            "severity": "high",
            "recommended_actions": actions,
            "recovery": "guided",
            "recommended_tool": None,
            "approval_required": approval_required,
            "knowledge_status": "candidate-unverified",
            "sources": [
                {
                    "url": item["url"],
                    "title": item["title"],
                    "product_version": item["product_version"],
                    "source_type": item["source_type"],
                    "authority_score": item["authority_score"],
                    "relevance_score": item["relevance_score"],
                }
                for item in usable[:5]
            ],
        }
        warnings = []
        if best["authority_score"] < 4:
            warnings.append(
                "The leading source is not official product documentation; require independent confirmation."
            )
        if not actions:
            warnings.append(
                "The leading source explains the failure but provides no bounded recovery action."
            )
        return ToolResult(
            status="succeeded",
            checks={
                "ranked_sources": ranked,
                "candidate_rule": candidate_rule,
                "promotion_requirements": [
                    "Reproduce the failure on a preserved input artifact.",
                    "Apply one bounded recovery action.",
                    "Rerun the smallest relevant validation or solver gate.",
                    "Record before/after evidence and confirm engineering intent is unchanged.",
                ],
            },
            warnings=warnings,
            application={
                "name": "CAX Workflow evidence evaluator",
                "version": "0.1.0",
            },
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record_verified_failure_rule(
    registry_path: str,
    candidate_rule: dict[str, Any],
    verification_evidence: list[str],
    idempotency_key: str,
    confirm_write: bool = False,
    expected_registry_sha256: str | None = None,
) -> ToolResult:
    started = time.monotonic()
    try:
        path = Path(registry_path).expanduser().resolve()
        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if not verification_evidence:
            raise ValueError("verification_evidence is required")
        required = {
            "code",
            "application",
            "title",
            "cause",
            "signature_terms",
            "recommended_actions",
            "sources",
        }
        missing = sorted(required - set(candidate_rule))
        if missing:
            raise ValueError(f"candidate_rule is missing: {', '.join(missing)}")
        _normalized_application(str(candidate_rule["application"]))
        if candidate_rule.get("knowledge_status") != "candidate-unverified":
            raise ValueError("candidate_rule must have knowledge_status=candidate-unverified")
        if not candidate_rule["sources"]:
            raise ValueError("candidate_rule must retain at least one source")

        registry = {"version": 1, "rules": []}
        current_sha = None
        if path.exists():
            if path.stat().st_size > MAX_REGISTRY_BYTES:
                raise ValueError("registry exceeds the supported size")
            current_sha = _file_sha256(path)
            if expected_registry_sha256 and current_sha != expected_registry_sha256:
                raise ValueError("registry hash changed since preview")
            registry = json.loads(path.read_text(encoding="utf-8"))
        rules = registry.setdefault("rules", [])
        for existing in rules:
            if existing.get("idempotency_key") == idempotency_key:
                return ToolResult(
                    status="succeeded",
                    artifacts=[{"path": str(path), "role": "failure-rule-registry"}],
                    checks={
                        "idempotent_replay": True,
                        "rule_code": existing.get("code"),
                        "registry_sha256": current_sha,
                    },
                    elapsed_seconds=time.monotonic() - started,
                )
            if existing.get("code") == candidate_rule["code"]:
                raise ValueError(
                    f"rule code already exists with another idempotency key: {candidate_rule['code']}"
                )

        verified_rule = dict(candidate_rule)
        verified_rule["knowledge_status"] = "verified"
        verified_rule["verification_evidence"] = [str(item) for item in verification_evidence]
        verified_rule["idempotency_key"] = idempotency_key
        preview_registry = {
            "version": 1,
            "rules": [*rules, verified_rule],
        }
        if not confirm_write:
            return ToolResult(
                status="needs_confirmation",
                checks={
                    "operation": "append_verified_failure_rule",
                    "target": str(path),
                    "current_registry_sha256": current_sha,
                    "rule_code": verified_rule["code"],
                    "preview": verified_rule,
                },
                warnings=[
                    "Set confirm_write=true after reviewing the rule, sources, and verification evidence."
                ],
                elapsed_seconds=time.monotonic() - started,
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{idempotency_key[:12]}.tmp")
        temporary.write_text(
            json.dumps(preview_registry, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return ToolResult(
            status="succeeded",
            artifacts=[{"path": str(path), "role": "failure-rule-registry"}],
            checks={
                "idempotent_replay": False,
                "rule_code": verified_rule["code"],
                "registry_sha256": _file_sha256(path),
                "rule_count": len(preview_registry["rules"]),
            },
            elapsed_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        return ToolResult(
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )
