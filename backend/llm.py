import asyncio
import json
import time
import aiohttp
import httpx
import litellm
from pathlib import Path
from config import (
    GROQ_API_KEY,
    OPENROUTER_API_KEY,
    GITHUB_TOKEN,
    MODEL_TRANSLATION_INPUT,
    MODEL_TRANSLATION_FINAL,
)

litellm.set_verbose = False

# ── GitHub Copilot token (shared with Weinrot credentials) ──────────────────
_COPILOT_CREDENTIALS = Path("/root/weinrot/data/credentials")
_COPILOT_TOKEN_FILE = _COPILOT_CREDENTIALS / "github-copilot.token.json"
_COPILOT_AUTH_FILE  = _COPILOT_CREDENTIALS / "auth-profiles.json"
_COPILOT_REFRESH_URL = "https://api.github.com/copilot_internal/v2/token"
_COPILOT_API_BASE    = "https://api.individual.githubcopilot.com"

class _CopilotToken:
    def __init__(self):
        self._token = None
        self._expires_at = 0.0
        self._api_base = _COPILOT_API_BASE
        self._lock = asyncio.Lock()

    def _load_cached(self) -> bool:
        try:
            if _COPILOT_TOKEN_FILE.exists():
                data = json.loads(_COPILOT_TOKEN_FILE.read_text())
                token = data.get("token")
                exp = data.get("expiresAt", 0)
                if exp > 1e12:
                    exp = exp / 1000
                if time.time() < exp - 60:
                    self._token = token
                    self._expires_at = exp
                    return True
        except Exception:
            pass
        return False

    def _oauth_token(self):
        try:
            data = json.loads(_COPILOT_AUTH_FILE.read_text())
            return data["profiles"]["github-copilot:github"]["token"]
        except Exception:
            return None

    async def _refresh(self) -> str:
        oauth = self._oauth_token()
        if not oauth:
            raise RuntimeError("No GitHub OAuth token for Copilot refresh")
        headers = {
            "Authorization": f"Bearer {oauth}",
            "Editor-Version": "Neovim/0.6.1",
            "Editor-Plugin-Version": "copilot.vim/1.16.0",
            "User-Agent": "GithubCopilot/1.155.0",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(_COPILOT_REFRESH_URL, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
        token = data["token"]
        exp = data.get("expires_at", time.time() + 3600)
        self._token = token
        self._expires_at = exp
        if data.get("endpoints", {}).get("api"):
            self._api_base = data["endpoints"]["api"]
        # update cache
        try:
            _COPILOT_TOKEN_FILE.write_text(json.dumps({
                "token": token,
                "expiresAt": int(exp * 1000),
                "updatedAt": int(time.time() * 1000),
            }, indent=2))
        except Exception:
            pass
        return token

    async def get(self) -> str:
        async with self._lock:
            if self._token and time.time() < self._expires_at - 60:
                return self._token
            if self._load_cached():
                return self._token
            return await self._refresh()

    def api_base(self) -> str:
        return self._api_base

_copilot = _CopilotToken()

async def _copilot_chat(model_name: str, messages: list, max_tokens: int, temperature: float) -> str:
    """Call GitHub Copilot API directly (bypasses litellm)."""
    token = await _copilot.get()
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Editor-Version": "vscode/1.85.0",
        "Editor-Plugin-Version": "copilot-chat/0.14.0",
        "Copilot-Integration-Id": "vscode-chat",
    }
    url = f"{_copilot.api_base()}/chat/completions"
    timeout = aiohttp.ClientTimeout(total=90)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
    return data["choices"][0]["message"]["content"] or ""
# ─────────────────────────────────────────────────────────────────────────────


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

    # Copilot route: bypass litellm entirely
    if model_id.startswith("copilot/"):
        model_name = model_id[len("copilot/"):]
        last_error = None
        for attempt in range(3):
            try:
                return await _copilot_chat(model_name, messages, max_tokens, temperature)
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "429" in err_str or "rate" in err_str.lower():
                    await asyncio.sleep(2 ** (attempt + 1))
                    continue
                return f"[{agent_name} unavailable: {err_str[:200]}]"
        return f"[{agent_name} unavailable: rate limit — {str(last_error)[:200]}]"

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
    try:
        return await asyncio.wait_for(
            llm_call(
                model_id=model_id,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7,
                agent_name=agent.get("name", "Agent"),
            ),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        return f"[{agent.get('name', 'Agent')} timed out after 120s]"


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
