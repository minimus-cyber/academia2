import asyncio
from llm import translate_to_english, translate_to_italian


async def translate_input(text: str) -> str:
    """Translate Italian professor input to English."""
    return await translate_to_english(text)


async def translate_publication(text: str) -> str:
    """Translate English publication to Italian."""
    return await translate_to_italian(text)


async def batch_translate_sections(sections: list[dict]) -> list[dict]:
    """
    Translates a list of {"heading": str, "content": str} dicts to Italian.
    Uses asyncio.gather for parallel translation of all sections.
    Returns translated sections with the same structure.
    """
    async def _translate_section(section: dict) -> dict:
        heading_it, content_it = await asyncio.gather(
            translate_to_italian(section.get("heading", "")),
            translate_to_italian(section.get("content", "")),
        )
        return {"heading": heading_it, "content": content_it}

    translated = await asyncio.gather(
        *[_translate_section(s) for s in sections],
        return_exceptions=True,
    )
    results = []
    for original, result in zip(sections, translated):
        if isinstance(result, Exception):
            results.append(original)
        else:
            results.append(result)
    return results
