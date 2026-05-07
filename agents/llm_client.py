"""
LLM client — wraps Gemini with retries and structured output support.

IMPORTANT: This file is for langchain-google-genai >= 4.0.0.
That version uses Gemini's native json_schema mode (constrained decoding),
which is significantly more reliable than the old function_calling approach.

Retry Strategy (IMPORTANT for free-tier users):
- The underlying google-genai SDK ALREADY retries on transient errors
  (5 attempts with exponential backoff). We do NOT add another retry layer
  on top — that would multiply API calls and burn through daily quota.
- For rate-limit (429 / RESOURCE_EXHAUSTED) we fail FAST with a clear
  message instead of retrying, because daily quota retries don't help.

Token Cap (Day 5 fix for "repetition collapse"):
- We cap max_output_tokens to a sane default. Gemini 2.5 models can otherwise
  generate up to 8K+ tokens, and when reviewing a low-content PR they may
  enter repetition loops, fill the budget with duplicated content, then get
  truncated mid-field — which fails Pydantic validation downstream.
"""
import os
import logging
from typing import Type, TypeVar
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel

# google-genai 1.x error hierarchy:
#   APIError (parent)
#     ├── ClientError (4xx — includes 429 quota)
#     └── ServerError (5xx — transient server issues)
from google.genai.errors import APIError, ClientError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Default cap on the LLM's output length. 4096 tokens ≈ 16,000 characters,
# which is plenty for a structured review report (~20 issues max). Prevents
# runaway generation when the model enters a repetition loop on low-content PRs.
DEFAULT_MAX_OUTPUT_TOKENS = 4096

# Larger cap for raw-text code generation. Step definition files for complex
# stories (15+ scenarios with @when/@then decorators each) can legitimately be
# 600+ lines. Splitting these would break the existing file-per-feature
# convention. 8192 tokens ≈ 32,000 characters; covers worst-case real files.
CODE_GENERATION_MAX_OUTPUT_TOKENS = 8192


def _is_quota_error(exc: Exception) -> bool:
    """Detect rate-limit / quota errors (429 RESOURCE_EXHAUSTED)."""
    msg = str(exc)
    return "RESOURCE_EXHAUSTED" in msg or "429" in msg or "quota" in msg.lower()


class QuotaExhaustedError(RuntimeError):
    """Raised when Gemini API daily/per-minute quota is hit. Surfaced fast
    instead of retrying, because retrying within the same minute won't help
    with daily quotas."""
    pass


class LLMClient:
    """Wrapper around Gemini with quota-aware error handling."""

    def __init__(self, temperature: float = 0.2, max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS):
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.model_name = model_name
        # temperature=0 → deterministic; small temp adds slight creativity
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        logger.info(
            f"LLM initialized: {model_name} (temp={temperature}, max_output_tokens={max_output_tokens})"
        )

    def _call_with_quota_check(self, callable_fn, *args, **kwargs):
        """Wrap any LLM call to convert quota errors into a clear, fast failure."""
        try:
            return callable_fn(*args, **kwargs)
        except Exception as e:
            if _is_quota_error(e):
                raise QuotaExhaustedError(
                    f"Gemini API quota exhausted for model '{self.model_name}'. "
                    f"Free tier is 20 requests/day per model. Options: "
                    f"(1) wait ~24h for quota reset, "
                    f"(2) switch GEMINI_MODEL in .env to a different model "
                    f"(e.g., 'gemini-2.5-flash-lite' has its own separate quota), "
                    f"(3) enable billing at https://aistudio.google.com/apikey for higher limits. "
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

        Uses Gemini's native json_schema mode (constrained decoding) — the model's
        token generation is constrained at the API level so the output is guaranteed
        to match the schema. This is far more reliable than function_calling mode.

        Raises:
            QuotaExhaustedError: if API daily/per-minute quota is hit
            ValueError: if LLM returns None despite quota being fine
        """
        # Explicitly request json_schema method (it's the default in 4.x but being
        # explicit makes the intent clear and survives library upgrades).
        structured_llm = self.llm.with_structured_output(output_schema, method="json_schema")

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        logger.info(f"Calling LLM (model={self.model_name}, schema={output_schema.__name__})...")
        result = self._call_with_quota_check(structured_llm.invoke, messages)

        if result is None:
            raise ValueError(
                f"LLM returned None — could not produce valid {output_schema.__name__}. "
                f"With json_schema mode this typically means: (1) safety filter blocked "
                f"the response, or (2) the schema contains features Gemini doesn't support."
            )

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
        if not hasattr(self, "_text_llm"):
            self._text_llm = ChatGoogleGenerativeAI(
                model=self.model_name,
                temperature=0.2,
                max_output_tokens=CODE_GENERATION_MAX_OUTPUT_TOKENS,
            )
            logger.info(
                f"Code generation LLM ready: {self.model_name} "
                f"(max_output_tokens={CODE_GENERATION_MAX_OUTPUT_TOKENS})"
            )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        logger.info(
            f"Calling LLM (text mode, model={self.model_name}, "
            f"max_output_tokens={CODE_GENERATION_MAX_OUTPUT_TOKENS})..."
        )
        response = self._call_with_quota_check(self._text_llm.invoke, messages)
        return response.content