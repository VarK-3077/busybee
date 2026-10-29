"""Message, usage, and completion models shared by every provider and caller."""

from enum import StrEnum

from pydantic import BaseModel, Field


class Role(StrEnum):
    """The three roles an LLM conversation can contain."""

    system = "system"
    user = "user"
    assistant = "assistant"


class Message(BaseModel):
    """One turn in a conversation sent to a provider."""

    role: Role
    content: str


class Usage(BaseModel):
    """Token counts reported by a provider for one completion."""

    input_tokens: int = 0
    output_tokens: int = 0


class Completion(BaseModel):
    """The text, usage, model, and latency returned by one provider call."""

    text: str
    usage: Usage = Field(default_factory=Usage)
    model: str = ""
    latency_s: float = 0.0
    finish_reason: str | None = None
