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


class LLMClient:
    """Provider-agnostic LLM wrapper with quota-aware error handling.

    Works with any OpenAI-compatible API endpoint. Configure via env vars:
        OPENAI_API_KEY   — API key / bearer token
        OPENAI_API_BASE  — base URL of the API
        LLM_MODEL        — model identifier
    """

    def __init__(self, temperature: float = 0.2, max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS):
        model_name = os.getenv("LLM_MODEL", "claude-opus-4-6")
        self.model_name = model_name
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
            SystemMessage(content=system_prompt),
            HumanMessage(content=augmented_prompt),
        ]

        logger.info(f"Calling LLM (model={self.model_name}, schema={output_schema.__name__})...")
        response = self._call_with_quota_check(self.llm.invoke, messages)

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

    def invoke_text(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call the LLM and return raw text. Used for content generation
        where structured output is fragile (e.g., entire source files
        with triple-quoted docstrings).

        Uses a larger output token limit than structured calls because
        code files are long and truncated output produces invalid Python
        that fails downstream validation.

        Raises:
            QuotaExhaustedError: if API quota is hit
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
            SystemMessage(content=system_prompt),
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

        # Always log token usage — cheap, useful regardless
        try:
            usage = getattr(response, "usage_metadata", None) or {}
            if usage:
                logger.info(
                    "Token usage: input=%s output=%s thoughts=%s total=%s",
                    usage.get("input_tokens", "?"),
                    usage.get("output_tokens", "?"),
                    usage.get("output_token_details", {}).get("reasoning", "?")
                        if isinstance(usage.get("output_token_details"), dict) else "?",
                    usage.get("total_tokens", "?"),
                )
        except Exception as e:
            logger.debug(f"Could not extract usage_metadata: {e}")

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