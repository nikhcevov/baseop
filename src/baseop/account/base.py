from abc import ABC, abstractmethod
from enum import Enum
from math import isfinite
from typing import TypedDict, TypeGuard

from baseop.user import User
from baseop.uuid import AccountUUID, account_uuid


class AccountStatus(Enum):
    Active = 1
    Frozen = 2
    Closed = 3


class AccountInfo(TypedDict):
    account_id: AccountUUID
    account_status: AccountStatus
    balance: float
    user: User


class AccountFrozenError(Exception):
    pass


class AccountClosedError(Exception):
    pass


class InvalidOperationError(Exception):
    pass


class InsufficientFundsError(Exception):
    pass


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
    def __init__(
        self,
        user: User,
        account_id: AccountUUID | None = None,
        balance: float = 0,
        account_status: AccountStatus = AccountStatus.Active,
    ) -> None:
        self._account_id = account_id if account_id is not None else account_uuid()
        if not isinstance(self._account_id, AccountUUID):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("Account id has invalid type")

        if not isinstance(user, User):  # pyright: ignore[reportUnnecessaryIsInstance]
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
        if self._account_status == AccountStatus.Closed:
            raise AccountClosedError("Account is closed, operation denied.")
        if self._account_status == AccountStatus.Frozen:
            raise AccountFrozenError("Account is frozen, operation denied.")

    def _validate_amount_value(self, amount: object):
        if not verify_strict_numeric(amount):
            raise InvalidOperationError("Amount must be valid value.")
        if amount <= 0:
            raise InvalidOperationError("Amount must be positive value.")

    @property
    def account_id(self) -> AccountUUID:
        return self._account_id

    @property
    def user(self) -> User:
        return self._user

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def account_status(self) -> AccountStatus:
        return self._account_status

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
