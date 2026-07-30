"""
LLM client — wraps any OpenAI-compatible LLM API with retries and structured output.

Uses langchain-openai's ChatOpenAI, which works with ANY endpoint that
implements the OpenAI /v1/chat/completions spec (OpenAI, Azure, Anthropic
proxies, self-hosted models, custom API gateways, etc.).

Configuration is via three environment variables:
    OPENAI_API_KEY   — API key / bearer token
    OPENAI_API_BASE  — base URL (e.g., https://api.openai.com/v1)
    LLM_MODEL        — model identifier (e.g., gpt-4o, claude-opus-4-6)

Retry Strategy:
- The underlying httpx transport retries on transient errors.
  We do NOT add another retry layer on top — that would multiply API
  calls and burn through quota.
- For rate-limit (429) we fail FAST with a clear message instead of
  retrying, because quota retries don't help.

Token Cap:
- We cap max_tokens to a sane default. Some models can otherwise
  generate very large outputs, and when reviewing a low-content PR they
  may enter repetition loops, fill the budget with duplicated content,
  then get truncated mid-field — which fails Pydantic validation
  downstream.
"""
import json
import os
import logging
import re
from typing import Type, TypeVar
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Default cap on the LLM's output length. 4096 tokens ≈ 16,000 characters,
# which is plenty for a structured review report (~20 issues max). Prevents
# runaway generation when the model enters a repetition loop on low-content PRs.
DEFAULT_MAX_OUTPUT_TOKENS = 4096

# Larger cap for raw-text code generation. Step definition files for complex
# stories (15+ scenarios with @when/@then decorators each) can legitimately be
# 600+ lines. Splitting these would break the existing file-per-feature
# convention.
#
# This cap is intentionally generous — most modern LLMs support 16K+ output
# tokens. If your model has a lower limit, reduce this value accordingly.
def _code_gen_max_output_tokens(model_name: str) -> int:
    """Return a sensible max-tokens cap for code generation.

    Override via LLM_CODE_GEN_MAX_TOKENS env var if your model needs
    a different budget.
    """
    override = os.getenv("LLM_CODE_GEN_MAX_TOKENS")
    if override:
        return int(override)
    return 16384  # generous default; works for most modern LLMs

# Kept for backwards compat with older imports; prefer the helper above.
CODE_GENERATION_MAX_OUTPUT_TOKENS = 16384


def _is_quota_error(exc: Exception) -> bool:
    """Detect rate-limit / quota errors (HTTP 429 or provider-specific)."""
    msg = str(exc).lower()
    return "429" in msg or "rate" in msg or "quota" in msg or "resource_exhausted" in msg


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ```) if the model wrapped its output.

    Models frequently wrap JSON output in markdown fences even when told
    not to. This strips them so json.loads / Pydantic can parse the content.
    """
    stripped = text.strip()
    match = re.match(r"^```(?:json|JSON)?\s*\n?(.*?)\n?\s*```$", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


def _extract_json_object(text: str) -> str:
    """Extract a JSON object from text that may contain preamble/postamble.

    The model might return:
        'Here is the JSON:\\n{"key": "val"}\\nLet me know if ...'
    We find the outermost { ... } and return just that.
    Falls back to the cleaned text if no braces found.
    """
    cleaned = _strip_markdown_fences(text)

    # Find the first { and the last matching }
    start = cleaned.find("{")
    if start != -1:
        end = cleaned.rfind("}")
        if end != -1 and end > start:
            return cleaned[start:end + 1]

    # Fallback: return cleaned text and let Pydantic report the parse error
    return cleaned


class QuotaExhaustedError(RuntimeError):
    """Raised when the LLM API rate limit or quota is hit. Surfaced fast
    instead of retrying, because retrying within the same minute won't help
    with quota-based limits."""
    pass


class OutputTruncatedError(RuntimeError):
    """Raised when the model stopped because it hit the output token cap.

    Surfaced fast for the same reason as QuotaExhaustedError: this is a budget
    breach, not a model mistake, so retrying under the same cap truncates at
    the same place. Two downstream symptoms it replaces:

      - a structured call would raise a Pydantic ValidationError about a field
        that was simply cut in half, naming the wrong cause
      - a text call would emit invalid Python, fail the validators, and burn
        every repair attempt against the identical cap

    The message names the exact knob to raise, so a re-run is a deliberate
    decision rather than guesswork.
    """
    pass


# ─────────────────────────────────────────────────────────────
# Token usage & cost tracking
#
# Every LLM call records its token usage here. Totals accumulate for
# the lifetime of the process (= one agent run in CI), giving real
# per-story cost numbers in the Actions logs instead of estimates.
#
# Pricing is configured via two OPTIONAL env vars (USD per 1M tokens):
#     LLM_PRICE_INPUT_PER_1M   e.g. "3.00"
#     LLM_PRICE_OUTPUT_PER_1M  e.g. "15.00"
# When unset, token counts are still logged; cost shows as "n/a".
# ─────────────────────────────────────────────────────────────

class _UsageTracker:
    """Accumulates token usage across all LLM calls in this process."""

    def __init__(self):
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls_without_usage = 0  # endpoint didn't report usage

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    def add_unreported(self) -> None:
        self.calls += 1
        self.calls_without_usage += 1

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def reset(self) -> None:
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls_without_usage = 0

    @staticmethod
    def _prices() -> tuple:
        """Return (price_in, price_out) in USD per 1M tokens, or (None, None)."""
        try:
            p_in = os.getenv("LLM_PRICE_INPUT_PER_1M")
            p_out = os.getenv("LLM_PRICE_OUTPUT_PER_1M")
            if p_in and p_out:
                return float(p_in), float(p_out)
        except ValueError:
            logger.warning(
                "LLM_PRICE_INPUT_PER_1M / LLM_PRICE_OUTPUT_PER_1M are set but "
                "not numeric — cost will show as n/a."
            )
        return None, None

    def input_cost_usd(self):
        """Input-side cost in USD, or None if pricing env vars are unset."""
        p_in, _ = self._prices()
        if p_in is None:
            return None
        return (self.input_tokens / 1_000_000) * p_in

    def output_cost_usd(self):
        """Output-side cost in USD, or None if pricing env vars are unset."""
        _, p_out = self._prices()
        if p_out is None:
            return None
        return (self.output_tokens / 1_000_000) * p_out

    def cost_usd(self):
        """Total estimated cost in USD, or None if pricing env vars are unset."""
        i, o = self.input_cost_usd(), self.output_cost_usd()
        if i is None or o is None:
            return None
        return i + o

    def cost_str(self) -> str:
        cost = self.cost_usd()
        if cost is None:
            return "n/a (set LLM_PRICE_INPUT_PER_1M / LLM_PRICE_OUTPUT_PER_1M)"
        return f"${cost:.4f}"

    def summary(self) -> dict:
        """Machine-readable snapshot (used by tests and agent result dicts)."""
        return {
            "llm_calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "input_cost_usd": self.input_cost_usd(),
            "output_cost_usd": self.output_cost_usd(),
            "estimated_cost_usd": self.cost_usd(),
            "calls_without_usage": self.calls_without_usage,
        }


_tracker = _UsageTracker()


# finish_reason values meaning "stopped because the output budget ran out".
# OpenAI-compatible endpoints report "length"; some gateways pass through
# Anthropic's "max_tokens". Compared lower-cased.
_TRUNCATION_FINISH_REASONS = {"length", "max_tokens"}


def _finish_reason(response) -> "str | None":
    """Best-effort finish_reason from a LangChain response. Never raises.

    Returns None when the endpoint does not report one — a missing reason must
    never fail a run that actually succeeded.
    """
    try:
        meta = getattr(response, "response_metadata", None) or {}
        for key in ("finish_reason", "stop_reason"):
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
    except Exception:
        pass
    return None


def _check_output_not_truncated(response, *, label: str, cap: int, knob: str) -> None:
    """Raise OutputTruncatedError if the model stopped at the output cap.

    Called AFTER _record_usage (so a truncated call still appears in the cost
    ledger — it was paid for) and BEFORE any parsing, so the operator sees the
    budget breach rather than a downstream symptom.

    Silent when finish_reason is absent or is any other value.
    """
    reason = _finish_reason(response)
    if reason not in _TRUNCATION_FINISH_REASONS:
        return

    produced = None
    try:
        produced = (getattr(response, "usage_metadata", None) or {}).get("output_tokens")
    except Exception:
        pass
    produced_str = f"{produced:,}" if isinstance(produced, int) else "not reported"

    logger.error("=" * 66)
    logger.error("OUTPUT TRUNCATED [%s]", label)
    logger.error("=" * 66)
    logger.error("The model stopped because the output token budget ran out.")
    logger.error("  finish_reason   : %r", reason)
    logger.error("  output cap      : %s tokens", f"{cap:,}")
    logger.error("  tokens produced : %s", produced_str)
    logger.error("Nothing was parsed and nothing was written.")
    logger.error("")
    logger.error("TO RE-RUN WITH MORE ROOM: %s", knob)
    logger.error("")
    logger.error(
        "BEFORE RAISING THE CAP: scan the log above for repeated content. A "
        "repetition loop fills any budget you give it, so a larger cap would "
        "only cost more and truncate later. Raise the cap only if the output "
        "was genuinely large and non-repetitive."
    )
    logger.error("=" * 66)

    raise OutputTruncatedError(
        f"{label}: output truncated at the {cap:,}-token cap "
        f"(finish_reason={reason!r}, produced={produced_str}). "
        f"Nothing was parsed or written. To re-run with more room: {knob}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Prompt caching
# ─────────────────────────────────────────────────────────────────────────────
#
# Providers that support it will cache a prompt PREFIX and bill later reads at
# a fraction of the input rate. The saving only exists when the cached span is
# byte-identical across calls, so a caller must pass genuinely static text as
# `system_prompt` and everything variable as `user_prompt`.
#
# Set LLM_PROMPT_CACHE=0 to disable — useful for A/B measurement, or if a
# gateway rejects the content-block form.
#
# Wire format below is the one verified against this project's gateway by
# scripts/gateway_probe.py: a breakpoint on a system content block.

_CACHE_DISABLED_VALUES = {"0", "false", "no", "off"}


def _prompt_cache_enabled() -> bool:
    """True unless LLM_PROMPT_CACHE is explicitly switched off."""
    return os.getenv("LLM_PROMPT_CACHE", "1").strip().lower() \
        not in _CACHE_DISABLED_VALUES


def _system_message(system_prompt: str, cache_prefix: bool):
    """Build the SystemMessage, with a cache breakpoint when asked for.

    Falls back to a plain string whenever caching is off, the caller did not
    request it, or the prompt is empty — so a provider that has never heard of
    cache_control sees exactly what it saw before this feature existed.
    """
    if not (cache_prefix and _prompt_cache_enabled() and system_prompt.strip()):
        return SystemMessage(content=system_prompt)
    return SystemMessage(content=[{
        "type": "text",
        "text": system_prompt,
        "cache_control": {"type": "ephemeral"},
    }])


def _cache_fields(response) -> tuple:
    """(created, read) cached-token counts. Returns (None, None) if absent.

    Providers disagree on naming, so both known spellings are checked. Never
    raises: cache reporting must not break a run.
    """
    try:
        usage = getattr(response, "usage_metadata", None) or {}
        details = usage.get("input_token_details") or {}
        created = details.get("cache_creation") or usage.get("cache_creation_input_tokens")
        read = details.get("cache_read") or usage.get("cache_read_input_tokens")
        return created, read
    except Exception:
        return None, None


def _record_usage(response, label: str) -> None:
    """Extract usage from a LangChain response and log call + running totals.

    Never raises — usage tracking must not break a run.
    """
    try:
        usage = getattr(response, "usage_metadata", None) or {}
        inp = usage.get("input_tokens")
        out = usage.get("output_tokens")
        if inp is None or out is None:
            _tracker.add_unreported()
            logger.info(
                "LLM usage [%s]: endpoint did not report token usage "
                "(run totals so far: %d calls, %d tokens)",
                label, _tracker.calls, _tracker.total_tokens,
            )
            return
        _tracker.add(int(inp), int(out))
        logger.info(
            "LLM usage [%s]: in=%d out=%d | run totals: calls=%d in=%d out=%d cost=%s",
            label, inp, out,
            _tracker.calls, _tracker.input_tokens, _tracker.output_tokens,
            _tracker.cost_str(),
        )
        created, read = _cache_fields(response)
        if created or read:
            # Reads bill at a fraction of the input rate; writes at a small
            # premium. Logged separately because the cost ledger prices every
            # input token the same and would otherwise overstate a cached run.
            logger.info(
                "LLM cache [%s]: written=%s read=%s",
                label,
                f"{created:,}" if created else "0",
                f"{read:,}" if read else "0",
            )
    except Exception as e:
        logger.debug(f"Usage tracking failed (non-fatal): {e}")


def get_usage_summary() -> dict:
    """Current accumulated usage for this process. See _UsageTracker.summary()."""
    return _tracker.summary()


def reset_usage() -> None:
    """Reset accumulated usage. Call between stories in scan mode so each
    story's summary reflects only its own calls."""
    _tracker.reset()


def log_usage_summary(context: str) -> dict:
    """Log token-usage and cost as two separate lines; return the summary dict.

    Example log output:
        LLM TOKEN USAGE [story SCRUM-20]: 5 calls, 48,213 input + 9,877 output = 58,090 total tokens
        LLM COST [story SCRUM-20]: $0.2928 total (input $0.1446 + output $0.1482)
    """
    s = _tracker.summary()
    # Token usage and cost are logged as SEPARATE lines: tokens are exact
    # (reported by the API); cost is derived from configured pricing.
    logger.info(
        "LLM TOKEN USAGE [%s]: %d calls, %s input + %s output = %s total tokens",
        context, s["llm_calls"],
        f"{s['input_tokens']:,}", f"{s['output_tokens']:,}", f"{s['total_tokens']:,}",
    )
    if s["estimated_cost_usd"] is not None:
        logger.info(
            "LLM COST [%s]: $%.4f total (input $%.4f + output $%.4f)",
            context, s["estimated_cost_usd"],
            s["input_cost_usd"], s["output_cost_usd"],
        )
    else:
        logger.info(
            "LLM COST [%s]: n/a — set LLM_PRICE_INPUT_PER_1M / "
            "LLM_PRICE_OUTPUT_PER_1M repo variables for cost numbers",
            context,
        )
    if s["calls_without_usage"]:
        logger.info(
            "  (%d call(s) did not report usage — totals are a lower bound)",
            s["calls_without_usage"],
        )
    return s


class LLMClient:
    """Provider-agnostic LLM wrapper with quota-aware error handling.

    Works with any OpenAI-compatible API endpoint. Configure via env vars:
        OPENAI_API_KEY   — API key / bearer token
        OPENAI_API_BASE  — base URL of the API
        LLM_MODEL        — model identifier
    """

    def __init__(self, temperature: float = 0.2, max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS):
        model_name = os.getenv("LLM_MODEL", "claude-opus-4-8")
        self.model_name = model_name
        # Retained so a truncation message can quote the cap it breached.
        self.max_output_tokens = max_output_tokens
        api_key = os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("OPENAI_API_BASE")
        # temperature=0 → deterministic; small temp adds slight creativity
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            max_tokens=max_output_tokens,
            api_key=api_key,
            base_url=api_base,
        )
        logger.info(
            f"LLM initialized: {model_name} (temp={temperature}, max_tokens={max_output_tokens})"
        )

    def _call_with_quota_check(self, callable_fn, *args, **kwargs):
        """Wrap any LLM call to convert quota errors into a clear, fast failure."""
        try:
            return callable_fn(*args, **kwargs)
        except Exception as e:
            if _is_quota_error(e):
                raise QuotaExhaustedError(
                    f"LLM API rate limit / quota exhausted for model '{self.model_name}'. "
                    f"Options: (1) wait for rate limit reset, "
                    f"(2) switch LLM_MODEL in .env to a different model, "
                    f"(3) check your API plan limits with your provider. "
                    f"Original error: {e}"
                ) from e
            raise  # Non-quota error, propagate as-is

    def invoke_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: Type[T],
        cache_prefix: bool = False,
    ) -> T:
        """
        Call the LLM and parse output into the given Pydantic schema.

        Injects the full JSON schema into the prompt so the model sees the
        exact field names, types, and nesting it must produce. Parses the
        raw JSON response with Pydantic directly — no reliance on provider-
        specific tool-calling or response_format features.

        This approach is provider-agnostic and works with any OpenAI-
        compatible endpoint regardless of structured output support.

        Raises:
            QuotaExhaustedError: if API rate limit / quota is hit
            OutputTruncatedError: if the model hit the output token cap
            ValueError: if LLM returns empty or unparseable output
        """
        # Generate the JSON schema from the Pydantic model so the LLM sees
        # the exact field names, types, nesting, and descriptions.
        schema_dict = output_schema.model_json_schema()
        schema_json = json.dumps(schema_dict, indent=2)

        # Append an explicit instruction + schema to the user prompt.
        augmented_prompt = (
            f"{user_prompt}\n\n"
            f"─── OUTPUT FORMAT (MANDATORY) ───\n"
            f"You MUST respond with ONLY a single valid JSON object (not a JSON array, "
            f"not markdown, not explanation text) that conforms to this JSON schema:\n\n"
            f"{schema_json}\n\n"
            f"Return ONLY the raw JSON object. No markdown fencing, no commentary."
        )

        messages = [
            _system_message(system_prompt, cache_prefix),
            HumanMessage(content=augmented_prompt),
        ]

        logger.info(f"Calling LLM (model={self.model_name}, schema={output_schema.__name__})...")
        response = self._call_with_quota_check(self.llm.invoke, messages)
        _record_usage(response, f"structured:{output_schema.__name__}")
        _check_output_not_truncated(
            response,
            label=f"structured:{output_schema.__name__}",
            cap=self.max_output_tokens,
            knob=(
                f"raise max_output_tokens in the LLMClient(...) call for this "
                f"agent (currently {self.max_output_tokens:,})"
            ),
        )

        raw_content = response.content or ""
        if not raw_content.strip():
            raise ValueError(
                f"LLM returned empty content — could not produce {output_schema.__name__}. "
                f"This typically means a safety filter blocked the response."
            )

        # Extract JSON from response (handles markdown fences, preamble, etc.)
        json_str = _extract_json_object(raw_content)

        try:
            result = output_schema.model_validate_json(json_str)
        except Exception as e:
            # Log the raw content for debugging, then raise a clear error
            logger.error(
                "Failed to parse LLM output as %s. Raw content (first 1000 chars): %s",
                output_schema.__name__,
                raw_content[:1000],
            )
            raise ValueError(
                f"LLM returned invalid JSON for {output_schema.__name__}: {e}"
            ) from e

        logger.info(f"LLM returned {type(result).__name__} successfully")
        return result

    def invoke_text(self, system_prompt: str, user_prompt: str,
                    cache_prefix: bool = False) -> str:
        """
        Call the LLM and return raw text. Used for content generation
        where structured output is fragile (e.g., entire source files
        with triple-quoted docstrings).

        Uses a larger output token limit than structured calls because
        code files are long and truncated output produces invalid Python
        that fails downstream validation.

        Raises:
            QuotaExhaustedError: if API quota is hit
            OutputTruncatedError: if the model hit the output token cap
        """
        # Use a dedicated LLM instance with a higher token budget for code.
        # Cached on first call so we don't reconstruct on every invocation.
        cap = _code_gen_max_output_tokens(self.model_name)
        if not hasattr(self, "_text_llm"):
            self._text_llm = ChatOpenAI(
                model=self.model_name,
                temperature=0.2,
                max_tokens=cap,
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("OPENAI_API_BASE"),
            )
            logger.info(
                f"Code generation LLM ready: {self.model_name} "
                f"(max_tokens={cap})"
            )

        messages = [
            _system_message(system_prompt, cache_prefix),
            HumanMessage(content=user_prompt),
        ]
        logger.info(
            f"Calling LLM (text mode, model={self.model_name}, "
            f"max_tokens={cap})..."
        )
        response = self._call_with_quota_check(self._text_llm.invoke, messages)

        # ─────────────────────────────────────────────────────────────
        # DIAGNOSTIC LOGGING: when content is suspiciously short, dump
        # everything we can about WHY the model returned empty output.
        # This is read-only — does NOT change return value or raise. The
        # downstream empty-content guard in agent2_coder still fires.
        # ─────────────────────────────────────────────────────────────
        content = response.content or ""

        # Record token usage in the run-level tracker (logs per-call + totals)
        _record_usage(response, "text:code-gen")
        _check_output_not_truncated(
            response,
            label="text:code-gen",
            cap=cap,
            knob=(
                f"set LLM_CODE_GEN_MAX_TOKENS above {cap:,} "
                f"(env var — no code change, no redeploy)"
            ),
        )

        # Suspicious-output diagnostic dump
        if len(content.strip()) < 30:
            logger.error(
                "─── DIAGNOSTIC: LLM returned suspiciously short content ───"
            )
            logger.error("Content length: %d chars", len(content))
            logger.error("Content (repr, first 200 chars): %r", content[:200])

            # response_metadata holds finish_reason and provider-specific fields
            try:
                meta = getattr(response, "response_metadata", None) or {}
                # Log everything — we don't know in advance which key matters
                for key, value in meta.items():
                    val_str = str(value)
                    # Truncate huge values to keep log readable
                    if len(val_str) > 500:
                        val_str = val_str[:500] + f"... ({len(val_str)} total chars)"
                    logger.error("response_metadata[%r] = %s", key, val_str)
                if not meta:
                    logger.error("response_metadata is empty or missing")
            except Exception as e:
                logger.error("Could not extract response_metadata: %s", e)

            # additional_kwargs sometimes carries the real payload when
            # content is empty (LangChain quirk with some providers)
            try:
                extras = getattr(response, "additional_kwargs", None) or {}
                if extras:
                    for key, value in extras.items():
                        val_str = str(value)
                        if len(val_str) > 500:
                            val_str = val_str[:500] + f"... ({len(val_str)} total chars)"
                        logger.error("additional_kwargs[%r] = %s", key, val_str)
                else:
                    logger.error("additional_kwargs is empty or missing")
            except Exception as e:
                logger.error("Could not extract additional_kwargs: %s", e)

            # Full response repr as last-resort fallback
            try:
                full_repr = repr(response)
                if len(full_repr) > 2000:
                    full_repr = full_repr[:2000] + f"... ({len(full_repr)} total chars)"
                logger.error("Full response repr: %s", full_repr)
            except Exception as e:
                logger.error("Could not repr response: %s", e)

            logger.error("─── END DIAGNOSTIC ───")

        return content