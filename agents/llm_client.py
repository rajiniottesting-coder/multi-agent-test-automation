"""
LLM client — wraps Gemini with retries and structured output support.
"""
import os
import logging
from typing import Type, TypeVar
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core.exceptions import ResourceExhausted

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """Wrapper around Gemini with retry + structured output."""

    def __init__(self, temperature: float = 0.2):
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.model_name = model_name
        # temperature=0 → deterministic; small temp adds slight creativity
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=temperature)
        logger.info(f"LLM initialized: {model_name} (temp={temperature})")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_exception_type(ResourceExhausted),
        reraise=True,
    )
    def invoke_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: Type[T],
    ) -> T:
        """
        Call the LLM and parse output into the given Pydantic schema.
        Retries up to 3 times on rate-limit (429) with exponential backoff.
        """
        structured_llm = self.llm.with_structured_output(output_schema)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        logger.info(f"Calling LLM (model={self.model_name})...")
        result = structured_llm.invoke(messages)
        logger.info(f"LLM returned {type(result).__name__} successfully")
        return result