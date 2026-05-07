# MediAI — Groq LLM Client
# Wraps the Groq API for all LLM calls in the system

import os
import json
import re
from dotenv import load_dotenv
from groq import Groq

load_dotenv()  # loads .env

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# GROQ_API_KEY = os.getenv("GROQ_API_KEY", GROQ_API_KEY)
MODEL = "openai/gpt-oss-120b"   # Groq's fast 70B model

_client = None


def get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def chat(system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
    """Single-turn chat with Groq LLM."""
    client = get_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def chat_json(system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> dict:
    """Chat and parse JSON response. Falls back to empty dict on parse failure."""
    raw = chat(system_prompt, user_prompt + "\n\nRespond ONLY with valid JSON. No markdown, no backticks.", max_tokens)
    # Strip possible ```json fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract the first JSON object/array
        match = re.search(r'(\{.*\}|\[.*\])', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        return {}
