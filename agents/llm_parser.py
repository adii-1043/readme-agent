"""Normalize LangChain message content and parse judge outputs."""

from __future__ import annotations

import re

WRITER_AIMESSAGE_PREFIX = "Writer Generation: "


def bind_output_tokens(model, max_output_tokens: int):
    """
    Provider-agnostic output token binding.
    - Groq-style models accept `max_tokens`.
    - Google GenAI models accept `max_output_tokens`.
    """
    module = getattr(getattr(model, "__class__", None), "__module__", "") or ""
    name = getattr(getattr(model, "__class__", None), "__name__", "") or ""

    # LangChain Google GenAI chat models validate config later, so binding `max_tokens`
    # doesn't error until invoke(). We must choose the right parameter up-front.
    if "langchain_google_genai" in module or "google_genai" in module or "Gemini" in name:
        return model.bind(max_output_tokens=max_output_tokens)

    return model.bind(max_tokens=max_output_tokens)


def string_from_llm_content(content: str | list | None) -> str:
    """Groq/LC may return str or a list of text blocks; always produce a single str."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text" and "text" in block:
                    parts.append(str(block["text"]))
                elif "text" in block:
                    parts.append(str(block["text"]))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def parse_judge_status(response: str) -> tuple[bool, str]:
    """
    Use the first line that looks like 'status: approved|disapproved' only.
    Avoids matching 'approved' inside 'disapproved' or inside pasted README text
    when we scan line-by-line (README headers won't match ^status:).
    """
    text = string_from_llm_content(response).strip()
    status_re = re.compile(r"^\s*status:\s*(approved|disapproved)\s*$", re.IGNORECASE)
    for line in text.splitlines():
        m = status_re.match(line)
        if m:
            return m.group(1).lower() == "approved", text
    return False, text


def sanitize_readme_draft(raw: str) -> str:
    """Remove model echoes of our AIMessage prefix and trailing judge-style lines."""
    text = string_from_llm_content(raw).strip()
    while text.startswith(WRITER_AIMESSAGE_PREFIX):
        text = text[len(WRITER_AIMESSAGE_PREFIX) :].strip()

    # If the writer echoed the judge label, drop that preamble.
    if text.lower().startswith("judge feedback:"):
        text = text[len("Judge Feedback:") :].lstrip()

    lines = text.splitlines()
    status_re = re.compile(r"^\s*status:\s*(approved|disapproved)\s*$", re.IGNORECASE)
    feedback_start = re.compile(r"^\s*feedback:\s*", re.IGNORECASE)
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            continue
        if status_re.match(lines[-1]) or feedback_start.match(lines[-1]):
            lines.pop()
            continue
        if re.fullmatch(r"=+", last) and len(last) >= 20:
            lines.pop()
            continue
        break
    return "\n".join(lines).strip()


def strip_writer_prefix_stored(content: str) -> str:
    """Undo one or more 'Writer Generation: ' prefixes on stored AIMessage content."""
    text = string_from_llm_content(content).strip()
    while text.startswith(WRITER_AIMESSAGE_PREFIX):
        text = text[len(WRITER_AIMESSAGE_PREFIX) :].strip()
    return text

