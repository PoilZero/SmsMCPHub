from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from smsmcphub.config import ProviderConfig
from smsmcphub.domain.models import IncomingMessage


class ProviderError(Exception):
    """Base class for errors that can be reported by an inbound adapter."""


class ProviderAuthenticationError(ProviderError):
    """The request failed provider authentication."""


class ProviderPayloadError(ProviderError):
    """The request body cannot be converted to a message."""


class ProviderAdapter(Protocol):
    name: str

    def verify_request(
        self, body: bytes, headers: Mapping[str, str], config: ProviderConfig
    ) -> None: ...

    def parse_messages(
        self, body: bytes, headers: Mapping[str, str], config: ProviderConfig
    ) -> list[IncomingMessage]: ...
