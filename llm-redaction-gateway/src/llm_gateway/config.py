"""Reads OpenRouter configuration from the environment.

Both values are required, with no hardcoded fallback: guessing a model
slug here would silently pin the gateway to a model that may not exist,
or isn't actually free, on whoever's OpenRouter account is in use. Set
OPENROUTER_MODEL to a slug from https://openrouter.ai/models (filter for
the free tier) before running the gateway.
"""

from __future__ import annotations

import os

_DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class MissingConfigError(RuntimeError):
    pass


def openrouter_url() -> str:
    # Overridable so tests can point this at the controlled mock (ADR-0003)
    # instead of the real OpenRouter API. Unlike api_key()/model(), this one
    # has a real default -- there's nothing to guess wrong about which URL
    # OpenRouter itself lives at.
    return os.environ.get("OPENROUTER_URL", _DEFAULT_OPENROUTER_URL)


def api_key() -> str:
    value = os.environ.get("OPENROUTER_API_KEY")
    if not value:
        raise MissingConfigError(
            "OPENROUTER_API_KEY is not set. Export it to an OpenRouter API key."
        )
    return value


def model() -> str:
    value = os.environ.get("OPENROUTER_MODEL")
    if not value:
        raise MissingConfigError(
            "OPENROUTER_MODEL is not set. Export it to a model slug available "
            "on your OpenRouter account -- see https://openrouter.ai/models "
            "for current options. No default is guessed here."
        )
    return value
