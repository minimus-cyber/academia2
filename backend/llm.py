import asyncio
import httpx
import litellm
from config import (
    GROQ_API_KEY,
    OPENROUTER_API_KEY,
    GITHUB_TOKEN,
    MODEL_TRANSLATION_INPUT,
    MODEL_TRANSLATION_FINAL,
)

litellm.set_verbose = False


async def llm_call(
    model_id: str,
    messages: list,
    max_tokens: int = 800,
    temperature: float = 0.7,
    json_mode: bool = False,
    agent_name: str = "Agent",
) -> str:
    """
    Routes LLM call based on model_id prefix.
    Retries up to 3 times on rate-limit errors with exponential backoff.
    """
    kwargs: dict = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    if model_id.startswith("groq/"):
        kwargs["model"] = model_id
        kwargs["api_key"] = GROQ_API_KEY

    elif model_id.startswith("openrouter/"):
        kwargs["model"] = model_id
        kwargs["api_key"] = OPENROUTER_API_KEY
        kwargs["api_base"] = "https://openrouter.ai/api/v1"

    elif model_id.startswith("github/"):
        model_name = model_id[len("github/"):]
        kwargs["model"] = "openai/" + model_name
        kwargs["api_key"] = GITHUB_TOKEN
        kwargs["api_base"] = "https://models.inference.ai.azure.com"

    else:
        # Fallback: pass as-is and hope litellm knows what to do
        kwargs["model"] = model_id

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = await litellm.acompletion(**kwargs)
            content = response.choices[0].message.content
            return content or ""
        except Exception as e:
            last_error = e
            err_str = str(e)
            if "429" in err_str or "RateLimitError" in err_str or "rate_limit" in err_str.lower():
                wait = 2 ** (attempt + 1)
                await asyncio.sleep(wait)
                continue
            # Non-rate-limit error: return error message immediately
            return f"[{agent_name} unavailable: {err_str[:200]}]"

    return f"[{agent_name} unavailable: rate limit after 3 retries — {str(last_error)[:200]}]"


WEINROT_AGENT_ID = "senior-weinrot"
WEINROT_API_URL = "http://localhost:8081/message"


async def _call_weinrot(user_prompt: str, system_prompt: str) -> str:
    """
    Routes a DAO prompt to the real Weinrot agent (Nexus, port 8081)
    instead of calling an LLM. Weinrot answers in Italian by default;
    we ask it to reply in English for Academia's canonical language.
    """
    full_text = (
        "[ACADEMIA INTERMUNDIA — internal DAO channel]\n"
        f"Context: {system_prompt}\n\n"
        f"Please reply in English.\n\n"
        f"{user_prompt}"
    )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                WEINROT_API_URL,
                json={
                    "sender": "academia-dao",
                    "session_id": "academia",
                    "text": full_text,
                    "contact_type": "known",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()
    except Exception as e:
        return f"[James Weinrot unavailable: {str(e)[:200]}]"


async def llm_call_agent(
    agent: dict,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 800,
) -> str:
    """
    Convenience wrapper that builds standard system+user message pair
    and calls llm_call with the agent's model_id.
    If the agent is senior-weinrot, proxies to the real Weinrot service.
    Returns empty string if agent has no model (e.g. the professor).
    """
    # Real Weinrot agent — proxy instead of simulating
    if agent.get("id") == WEINROT_AGENT_ID:
        return await _call_weinrot(user_prompt, system_prompt)

    model_id = agent.get("model_id")
    if not model_id:
        return ""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return await llm_call(
        model_id=model_id,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.7,
        agent_name=agent.get("name", "Agent"),
    )


async def translate_to_english(text: str) -> str:
    """Translates Italian professor input to English using the fast Groq model."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are a precise translator. "
                "Translate the following Italian text to English. "
                "Return only the translation, nothing else."
            ),
        },
        {"role": "user", "content": text},
    ]
    result = await llm_call(
        model_id=MODEL_TRANSLATION_INPUT,
        messages=messages,
        max_tokens=400,
        temperature=0.2,
        agent_name="Translator",
    )
    return result.strip()


async def translate_to_italian(text: str) -> str:
    """Translates English academic content to Italian using the 70b Groq model."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert academic translator. "
                "Translate the following English academic text to Italian. "
                "Preserve all HTML formatting, citations, section headers, and technical terms. "
                "Return only the translation."
            ),
        },
        {"role": "user", "content": text},
    ]
    result = await llm_call(
        model_id=MODEL_TRANSLATION_FINAL,
        messages=messages,
        max_tokens=4096,
        temperature=0.3,
        agent_name="Translator-IT",
    )
    return result.strip()
