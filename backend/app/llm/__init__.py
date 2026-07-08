"""LLM abstraction — LiteLLM over Groq. The model is swappable; the kernel is
the trust layer, so the model choice never affects correctness of the record."""
from app.llm.client import LLMClient, get_llm  # noqa: F401
