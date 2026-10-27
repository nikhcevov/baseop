from uuid import uuid4


class AccountUUID(str):
    def __new__(cls, value: str):
        if not isinstance(value, str) or len(value) != 8:
            raise ValueError("Invalid value")
        return super().__new__(cls, value)


def accout_uuid() -> AccountUUID:
    """Generate short UUID"""
    return AccountUUID(f"{uuid4()}"[:8])
