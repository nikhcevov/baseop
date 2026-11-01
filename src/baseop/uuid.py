from typing import Annotated
from uuid import uuid4

from pydantic import Field

AccountId = Annotated[str, Field(min_length=8, max_length=8)]


def create_account_id() -> AccountId:
    """Generate short Id"""
    return f"{uuid4()}"[:8]
