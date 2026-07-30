#!/usr/bin/env python3
"""
Gateway probe — answers two Phase-2 questions without waiting on anyone.

  1. Which models does this gateway actually expose?   (backlog 1.2 — model routing)
  2. Is Anthropic prompt caching working through it?   (backlog 1.1 — prompt caching)

MANUAL TOOL. Not run by CI, not part of the test suite. It makes 3 live LLM
calls (~2,000 tokens total, well under $0.05).

Usage:
    python scripts/gateway_probe.py
    python scripts/gateway_probe.py --model claude-sonnet-4-5   # probe a specific model

Reads OPENAI_API_BASE / OPENAI_API_KEY / LLM_MODEL from the environment (.env).

FULL FLAG REFERENCE
-------------------
Every flag, its default and its purpose:

    python -m scripts.gateway_probe --help

That is the authoritative list - this docstring shows only the common
cases. --help also carries copy-pasteable examples.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ `requests` not installed. Run: pip install requests")
    sys.exit(1)

# Load .env if present (same convention as scripts/smoke_test.py)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

BASE = (os.getenv("OPENAI_API_BASE") or "").rstrip("/")
KEY = os.getenv("OPENAI_API_KEY") or ""
DEFAULT_MODEL = os.getenv("LLM_MODEL", "claude-opus-4-6")

# Anthropic's minimum cacheable prefix is 1024 tokens (2048 for Haiku-class).
# ~40 chars/sentence * 260 ≈ 10k chars ≈ 2.5k tokens — comfortably over.
FILLER = (
    "The quality engineering team maintains a comprehensive regression suite "
    "covering authentication, checkout, and reporting workflows. "
) * 130


def _headers() -> dict:
    return {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}


def check_env() -> None:
    missing = [n for n, v in [("OPENAI_API_BASE", BASE), ("OPENAI_API_KEY", KEY)] if not v]
    if missing:
        print(f"❌ Missing env var(s): {', '.join(missing)}")
        print("   Set them in .env (see .env.example) and re-run.")
        sys.exit(1)
    print(f"✅ Gateway: {BASE}")


# ─────────────────────────────────────────────────────────────
# 1. Model discovery  (backlog 1.2)
# ─────────────────────────────────────────────────────────────

def list_models() -> list[str]:
    print("\n" + "=" * 70)
    print("1. AVAILABLE MODELS  (for backlog 1.2 — model routing)")
    print("=" * 70)
    try:
        r = requests.get(f"{BASE}/models", headers=_headers(), timeout=30)
        r.raise_for_status()
        ids = sorted(m.get("id", "?") for m in r.json().get("data", []))
    except Exception as e:
        print(f"⚠️  Could not list models: {type(e).__name__}: {e}")
        print("   Some gateways disable /v1/models. Ask your admins for the model list.")
        return []

    if not ids:
        print("⚠️  Gateway returned an empty model list.")
        return []

    print(f"\n{len(ids)} model(s) exposed:\n")
    for mid in ids:
        marker = "  ← currently configured (LLM_MODEL)" if mid == DEFAULT_MODEL else ""
        print(f"   • {mid}{marker}")

    # Flag likely cheaper candidates for Agents 1 and 5.
    cheaper = [m for m in ids if any(k in m.lower() for k in ("sonnet", "haiku", "mini", "flash", "small"))]
    if cheaper:
        print("\n   Candidates for Agents 1 & 5 (test design / prose summary):")
        for m in cheaper:
            print(f"     → {m}")
        print("\n   Next: confirm pricing at models.litellm.ai, then set LLM_MODEL")
        print("   in agent1_analyst.yml and the Agent-5 env block of agent4_runner.yml.")
    else:
        print("\n   No obviously-cheaper tier detected. If only one model is exposed,")
        print("   backlog item 1.2 (model routing) is not actionable — close it.")
    return ids


# ─────────────────────────────────────────────────────────────
# 2. Prompt caching  (backlog 1.1)
# ─────────────────────────────────────────────────────────────

def _build_payload(model: str, variant: str) -> dict:
    """Build a request with the cache breakpoint placed per `variant`.

    Gateways differ in WHERE they honour cache_control, so we try more than one
    placement before concluding caching is unavailable:
      system  — breakpoint on a system content block (LiteLLM's documented form)
      user    — breakpoint on a user content block (maps most directly to the
                Anthropic API and survives some proxies that flatten `system`)
      none    — control run, no breakpoint at all
    """
    block = lambda text: {"type": "text", "text": text,
                          "cache_control": {"type": "ephemeral"}}

    if variant == "system":
        messages = [
            {"role": "system", "content": [block(FILLER)]},
            {"role": "user", "content": "Reply with the single word: ok"},
        ]
    elif variant == "user":
        messages = [
            {"role": "user", "content": [
                block(FILLER),
                {"type": "text", "text": "Reply with the single word: ok"},
            ]},
        ]
    else:
        messages = [
            {"role": "system", "content": FILLER},
            {"role": "user", "content": "Reply with the single word: ok"},
        ]

    return {"model": model, "max_tokens": 16, "messages": messages}


def _call(model: str, variant: str = "system") -> dict | None:
    """One chat completion with a large static prefix. Returns the usage dict."""
    payload = _build_payload(model, variant)
    try:
        r = requests.post(f"{BASE}/chat/completions", headers=_headers(),
                          data=json.dumps(payload), timeout=90)
        r.raise_for_status()
        return r.json().get("usage", {})
    except requests.HTTPError as e:
        body = e.response.text[:300] if e.response is not None else ""
        print(f"   ❌ HTTP {e.response.status_code if e.response else '?'}: {body}")
        return None
    except Exception as e:
        print(f"   ❌ {type(e).__name__}: {e}")
        return None


def _cache_fields(usage: dict) -> tuple[int, int]:
    """Extract (created, read) cache token counts across naming variants."""
    created = (usage.get("cache_creation_input_tokens")
               or usage.get("prompt_cache_creation_tokens") or 0)
    read = (usage.get("cache_read_input_tokens")
            or usage.get("prompt_cache_hit_tokens")
            or (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    return int(created), int(read)


def probe_caching(model: str) -> None:
    print("\n" + "=" * 70)
    print("2. PROMPT CACHING  (for backlog 1.1)")
    print("=" * 70)
    print(f"\nModel: {model}")
    print("Sending identical ~2.5k-token prefixes with a cache breakpoint.")
    print("Trying each supported breakpoint placement before concluding.\n")

    for variant in ("system", "user"):
        print(f"   ── Variant: cache_control on the {variant.upper()} message ──")

        u1 = _call(model, variant)
        if u1 is None:
            print("      Call failed for this variant — trying the next.\n")
            continue
        c1, r1 = _cache_fields(u1)
        print(f"      call 1  prompt_tokens={u1.get('prompt_tokens')}  "
              f"cache_created={c1}  cache_read={r1}")

        u2 = _call(model, variant)
        if u2 is None:
            print("      Second call failed — trying the next variant.\n")
            continue
        c2, r2 = _cache_fields(u2)
        print(f"      call 2  prompt_tokens={u2.get('prompt_tokens')}  "
              f"cache_created={c2}  cache_read={r2}\n")

        if r2 > 0:
            prompt_tokens = u2.get("prompt_tokens", 0) or 1
            pct = 100.0 * r2 / prompt_tokens
            print("-" * 70)
            print("   ✅ PROMPT CACHING WORKS — breakpoint on the "
                  f"{variant.upper()} message")
            print(f"      Call 2 read {r2:,} cached tokens ({pct:.0f}% of its input),")
            print("      billed at roughly 10% of normal input price.")
            print("\n      ACTION (backlog 1.1): place the cache_control breakpoint")
            print(f"      on the {variant} message in llm_client.py, after the static")
            print("      blocks (system prompt + references + inventory). Static content")
            print("      must come FIRST — caching matches on the PREFIX.")
            print("-" * 70)
            return

        if c1 > 0 or c2 > 0:
            print("      ⚠️  Cache was created but not read back — likely a TTL expiry")
            print("          or a differing prefix. Re-run to confirm.\n")

    print("-" * 70)
    print("   ❌ NO CACHING DETECTED on any breakpoint placement")
    print("      The gateway returns the cache fields in `usage` (so LiteLLM knows")
    print("      about caching) but reports zero activity — the cache_control field")
    print("      is being stripped before it reaches the provider, or caching is")
    print("      disabled in the gateway config.")
    print("\n      This is now an admin question. Backlog 1.1 stays blocked, but you")
    print("      have concrete evidence to send: a >1024-token prefix, a valid")
    print("      breakpoint on two placements, and all-zero cache counters.")
    print("-" * 70)


def main() -> None:
    ap = argparse.ArgumentParser(description="Probe the LLM gateway for models and caching support.")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="Model to probe for caching")
    ap.add_argument("--models-only", action="store_true", help="Skip the caching probe (no LLM calls)")
    args = ap.parse_args()

    print("=" * 70)
    print("GATEWAY PROBE")
    print("=" * 70)
    check_env()
    list_models()
    if not args.models_only:
        probe_caching(args.model)
    print("\nDone.\n")


if __name__ == "__main__":
    main()