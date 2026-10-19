"""
Layer 1 Refinement: Real-Time LLM Service with Groq Rate-Limit Guard.
File: backend/app/pipeline/llm_service.py
"""

import os
import json
from typing import Dict, Any
from groq import Groq


def call_realtime_llm(payload: Dict[str, Any], api_key: str = None) -> Dict[str, Any]:
    """
    Calls Groq Cloud API in real-time with max_tokens=600 to satisfy Groq's 1000 OTPM limit.
    Includes automatic fallback to alternative Groq models if rate limit is hit.
    """
    groq_api_key = api_key or os.getenv("GROQ_API_KEY")

    if not groq_api_key:
        raise ValueError(
            "CRITICAL: GROQ_API_KEY is not set! Set GROQ_API_KEY in backend/.env"
        )

    # Models to try in order (Qwen -> Llama 3.3 70B fallback)
    models_to_try = [
        "qwen/qwen3.8-27b",
        "qwen-2.5-coder-32b",
        "llama-3.3-70b-versatile"
    ]

    client = Groq(api_key=groq_api_key.strip())
    last_exception = None

    for model_name in models_to_try:
        try:
            response = client.chat.completions.create(
                model=model_name,
                max_tokens=600,  # Kept under 1000 OTPM to respect Groq free tier limit
                temperature=0.1,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": payload["system_prompt"]},
                    {"role": "user", "content": payload["user_prompt"]}
                ]
            )

            raw_text = response.choices[0].message.content.strip()

            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]

            return json.loads(raw_text.strip())

        except Exception as e:
            last_exception = e
            # If rate limited, try next model in fallback list
            if "rate_limit_exceeded" in str(e).lower() or "429" in str(e):
                continue
            else:
                break

    raise RuntimeError(f"Groq API Call Failed: {str(last_exception)}") from last_exception
