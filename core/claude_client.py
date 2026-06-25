"""Thin wrapper around the Anthropic API, with rate-limit resilience.

One place that talks to Claude. Calls retry on 429 (rate limit) with a
backoff wait, so a transient cap self-heals instead of bubbling an error
into the digest. Loads ANTHROPIC_API_KEY from .secrets/.env.
"""

import base64
import time
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

import config

load_dotenv(config.ENV_PATH)
_client = Anthropic()


def _is_rate_limit(e: Exception) -> bool:
    name = type(e).__name__.lower()
    if "ratelimit" in name:
        return True
    return "rate_limit" in str(e).lower() or "429" in str(e)


def _create_with_retry(**kwargs):
    """Call messages.create, retrying on rate-limit with backoff."""
    last = None
    for attempt in range(1, config.RETRY_MAX_ATTEMPTS + 1):
        try:
            return _client.messages.create(**kwargs)
        except Exception as e:
            last = e
            if _is_rate_limit(e) and attempt < config.RETRY_MAX_ATTEMPTS:
                wait = config.RETRY_BASE_WAIT_SECONDS * attempt
                print(f"        rate-limited; waiting {wait}s "
                      f"(attempt {attempt}/{config.RETRY_MAX_ATTEMPTS})")
                time.sleep(wait)
                continue
            raise
    raise last


def ask_text(prompt: str, max_tokens: int = None) -> str:
    resp = _create_with_retry(
        model=config.MODEL,
        max_tokens=max_tokens or config.MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return _first_text(resp)


def ask_with_pdf(pdf_path: Path, prompt: str, max_tokens: int = None) -> str:
    pdf_b64 = base64.standard_b64encode(Path(pdf_path).read_bytes()).decode("utf-8")
    content = [
        {"type": "document",
         "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
        {"type": "text", "text": prompt},
    ]
    resp = _create_with_retry(
        model=config.MODEL,
        max_tokens=max_tokens or config.MAX_TOKENS,
        messages=[{"role": "user", "content": content}],
    )
    return _first_text(resp)


def ask_with_web_search(prompt: str, max_searches: int = 3,
                        max_tokens: int = None) -> str:
    resp = _create_with_retry(
        model=config.MODEL,
        max_tokens=max_tokens or config.MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
        tools=[{"type": "web_search_20250305", "name": "web_search",
                "max_uses": max_searches}],
    )
    # Web-search replies split the answer into multiple text blocks around
    # the search tool-calls. Join with "" (not "\n") so a single bullet
    # fragmented across blocks reconstructs intact instead of gaining stray
    # newlines (which left a "- " stranded on its own line).
    return "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()


def _first_text(resp) -> str:
    for b in resp.content:
        if getattr(b, "type", None) == "text":
            return b.text.strip()
    return ""
