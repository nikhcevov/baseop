from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from baseop.uuid import AccountId


class ClientStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"


Name = Annotated[str, Field(min_length=2, max_length=50)]
Contact = Annotated[str, Field(min_length=7, max_length=11)]


class Client(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID = Field(default_factory=uuid4)
    first_name: Name
    middle_name: Name | None = None
    last_name: Name
    status: ClientStatus = ClientStatus.ACTIVE
    suspicious: bool = False
    account_ids: list[AccountId] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)
    age: Annotated[int, Field(ge=18, strict=True)]
