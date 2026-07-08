"""Agent layer (LangGraph + Groq via LiteLLM).

Agents PROPOSE. Every proposal is verified by the deterministic Verification
Kernel before it can enter the compliance record. There is no rule-based
fallback: the cognition runs on Groq, the trust runs on the kernel.
"""
