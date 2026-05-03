import json
from typing import Any


def extract_json(raw_text: str) -> Any:
    """Extract the first valid JSON object or array from an LLM response."""
    if not raw_text:
        raise json.JSONDecodeError("Empty response", raw_text, 0)

    cleaned = (
        raw_text.replace("```json", "")
        .replace("```JSON", "")
        .replace("```", "")
        .strip()
    )

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
            return value
        except json.JSONDecodeError:
            continue

    raise json.JSONDecodeError("No JSON object or array found", cleaned, 0)


def extract_json_object(raw_text: str) -> dict:
    data = extract_json(raw_text)
    if isinstance(data, dict):
        return data
    return {}


def extract_json_list(raw_text: str) -> list[dict]:
    data = extract_json(raw_text)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []
