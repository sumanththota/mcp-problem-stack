"""Request shape mirrors OpenAI's chat-completions API, since that's the
shape OpenRouter expects.
"""

from __future__ import annotations

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = True
