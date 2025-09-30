from __future__ import annotations

from typing import Any, List, Optional, Mapping, Sequence
import logging
from pydantic import BaseModel, Field


class Status(BaseModel):
    type: str = Field(alias="type")

    def is_up(self) -> bool:
        return self.type.upper() == "UP"


class RealmName(BaseModel):
    en_US: Optional[str] = None


class RealmSummary(BaseModel):
    id: Optional[int] = None
    slug: Optional[str] = None
    # Blizzard sometimes returns name as a localized object, other times directly as a string.
    name: Optional[RealmName | str] = None

    def label(self) -> Optional[str]:
        if self.slug:
            return self.slug
        if isinstance(self.name, RealmName):
            if self.name.en_US:
                return self.name.en_US
        elif isinstance(self.name, str):
            # Use raw string (already localized) when provided directly
            return self.name
        return None


class ConnectedRealm(BaseModel):
    status: Optional[Status] = None
    realms: List[RealmSummary] = Field(default_factory=list)  # type: ignore[type-arg]

    def realm_labels(self) -> List[str]:
        out: List[str] = []
        for r in self.realms:
            lbl = r.label()
            if lbl:
                out.append(lbl)
        return out

    def is_up(self) -> bool:
        return self.status.is_up() if self.status else False


def parse_connected_realms(data: Sequence[Mapping[str, Any]]) -> list[ConnectedRealm]:
    """Parse raw connected realm dictionaries into ConnectedRealm models.

    Any item that fails validation is skipped (a warning is logged) so a single
    malformed realm does not break the entire polling loop.
    """
    out: list[ConnectedRealm] = []
    log = logging.getLogger(__name__)
    for idx, item in enumerate(data):
        try:
            out.append(ConnectedRealm.model_validate(dict(item)))
        except Exception:
            log.warning("Failed to parse connected realm index %s", idx, exc_info=True)
            continue
    return out
