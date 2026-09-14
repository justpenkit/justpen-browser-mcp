"""Strict, single-condition postconditions for browser actions."""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WaitBase(BaseModel):
    """Common observation deadline."""

    model_config = ConfigDict(extra="forbid")
    timeout_ms: int = Field(default=10000, ge=1, strict=True)


class ResponseWait(WaitBase):
    """Match a newly started request's response exactly."""

    kind: Literal["response"]
    url: str = Field(min_length=1)
    method: str | None = None
    status: int | None = Field(default=None, ge=100, le=599, strict=True)

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str | None) -> str | None:
        """Accept ASCII HTTP tokens and normalize their casing."""
        if value is None:
            return None
        if re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", value) is None:
            raise ValueError("method must be a nonempty ASCII HTTP token")
        return value.upper()


class UrlWait(WaitBase):
    """Match a subsequent navigation in the chosen frame."""

    kind: Literal["url"]
    url: str = Field(min_length=1)


class ElementWait(WaitBase):
    """Wait for an element state after the action."""

    kind: Literal["element"]
    selector: str = Field(min_length=1)
    state: Literal["attached", "detached", "visible", "hidden"] = "visible"


class TextWait(WaitBase):
    """Wait for visible text to appear or disappear after the action."""

    kind: Literal["text"]
    text: str = Field(min_length=1)
    state: Literal["visible", "hidden"] = "visible"


class PopupWait(WaitBase):
    """Observe a popup opened by the selected page."""

    kind: Literal["popup"]


class DownloadWait(WaitBase):
    """Observe a download emitted by the selected page."""

    kind: Literal["download"]


WaitForSpec = Annotated[
    ResponseWait | UrlWait | ElementWait | TextWait | PopupWait | DownloadWait,
    Field(discriminator="kind"),
]
