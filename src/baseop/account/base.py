from abc import ABC, abstractmethod
from enum import StrEnum
from math import isfinite
from typing import ClassVar, TypedDict, TypeGuard

from baseop.client import Client
from baseop.uuid import AccountId, create_account_id


class AccountStatus(StrEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class AccountInfo(TypedDict):
    account_id: AccountId
    account_status: AccountStatus
    balance: float
    user: Client


class AccountFrozenError(Exception):
    pass


class AccountClosedError(Exception):
    pass


class InvalidOperationError(Exception):
    pass


class InsufficientFundsError(Exception):
    pass


def is_account_id(value: object) -> TypeGuard[str]:
    """AccountId is inert outside pydantic, so plain classes verify it manually."""
    return isinstance(value, str) and len(value) == 8


def verify_strict_numeric(value: object) -> TypeGuard[int | float]:
    """Function verifies a value is strictly finite numeric value"""
    numeric = isinstance(value, (int, float))
    is_bool = isinstance(value, bool)
    if not numeric or is_bool:
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False


class AbstractAccount(ABC):
    _TRANSITIONS: ClassVar[dict[AccountStatus, set[AccountStatus]]] = {
        AccountStatus.ACTIVE: set({AccountStatus.FROZEN, AccountStatus.CLOSED}),
        AccountStatus.FROZEN: set({AccountStatus.ACTIVE, AccountStatus.CLOSED}),
        AccountStatus.CLOSED: set(),
    }

    def __init__(
        self,
        user: Client,
        account_id: AccountId | None = None,
        balance: float = 0,
        account_status: AccountStatus = AccountStatus.ACTIVE,
    ) -> None:
        self._account_id = account_id if account_id is not None else create_account_id()
        if not is_account_id(self._account_id):
            raise TypeError("Account id has invalid type")

        if not isinstance(user, Client):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("User has invalid type")
        self._user = user

        if not verify_strict_numeric(balance):
            raise ValueError("Balance must be valid number")
        if balance < 0:
            raise ValueError("Balance must be non negative")
        self._balance = float(balance)

        if not isinstance(account_status, AccountStatus):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("Account status has invalid type")
        self._account_status = account_status

    def _validate_account_status(self):
        if self._account_status == AccountStatus.CLOSED:
            raise AccountClosedError("Account is closed, operation denied.")
        if self._account_status == AccountStatus.FROZEN:
            raise AccountFrozenError("Account is frozen, operation denied.")

    def _validate_amount_value(self, amount: object):
        if not verify_strict_numeric(amount):
            raise InvalidOperationError("Amount must be valid value.")
        if amount <= 0:
            raise InvalidOperationError("Amount must be positive value.")

    def freeze(self) -> None:
        if AccountStatus.FROZEN not in self._TRANSITIONS[self.account_status]:
            raise InvalidOperationError("Account freeze unavailable")
        self._account_status = AccountStatus.FROZEN

    def unfreeze(self) -> None:
        if AccountStatus.ACTIVE not in self._TRANSITIONS[self.account_status]:
            raise InvalidOperationError("Account unfreeze unavailable")
        self._account_status = AccountStatus.ACTIVE

    def close(self) -> None:
        if AccountStatus.CLOSED not in self._TRANSITIONS[self.account_status]:
            raise InvalidOperationError("Account close unavailable")
        self._account_status = AccountStatus.CLOSED

    @property
    def account_id(self) -> AccountId:
        return self._account_id

    @property
    def user(self) -> Client:
        return self._user

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def account_status(self) -> AccountStatus:
        return self._account_status

    @property
    @abstractmethod
    def total_value(self) -> float:
        """Returns total account value, calculated from all account assets"""
        ...

    def _add_to_balance(self, amount: float) -> None:
        """Shared deposit mechanics for account types."""
        self._validate_account_status()
        self._validate_amount_value(amount)

        try:
            balance_after_deposit = float(self._balance) + float(amount)
        except OverflowError:
            raise InvalidOperationError("Resulting balance is too large")

        if not isfinite(balance_after_deposit):
            raise InvalidOperationError("Resulting balance is too large")

        self._balance = balance_after_deposit

    def _subtract_from_balance(self, amount: float) -> None:
        """Shared withdrawal mechanics for account types."""
        self._validate_account_status()
        self._validate_amount_value(amount)

        remaining_balance = self._balance - amount
        if remaining_balance < 0:
            raise InsufficientFundsError("Withdrawal amount is larger than balance.")

        self._balance = float(remaining_balance)

    def _account_info(self) -> AccountInfo:
        """Shared part of the account info for concrete account types."""
        return {
            "account_id": self._account_id,
            "account_status": self._account_status,
            "balance": self._balance,
            "user": self._user,
        }

    @abstractmethod
    def deposit(self, amount: float) -> None: ...

    @abstractmethod
    def withdraw(self, amount: float) -> None: ...

    @abstractmethod
    def get_account_info(self) -> AccountInfo: ...
