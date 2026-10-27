from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import TypedDict, TypeGuard
from uuid import UUID

from baseop.uuid import AccountUUID, account_uuid


@dataclass
class User:
    id: UUID
    name: str


class AccountStatus(Enum):
    Active = 1
    Frozen = 2
    Closed = 3


class AccountCurrency(Enum):
    RUB = 1
    USD = 2
    EUR = 3
    KZT = 4
    CNY = 5


class AccountInfo(TypedDict):
    account_id: AccountUUID
    account_status: AccountStatus
    balance: float
    user: User


class BankAccountInfo(AccountInfo):
    currency: AccountCurrency


class AccountFrozenError(Exception):
    pass


class AccountClosedError(Exception):
    pass


class InvalidOperationError(Exception):
    pass


class InsufficientFundsError(Exception):
    pass


def verify_strict_numeric(value: object) -> TypeGuard[int | float]:
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
    @abstractmethod
    def account_id(self) -> AccountUUID: ...

    @property
    @abstractmethod
    def user(self) -> User: ...

    @property
    @abstractmethod
    def balance(self) -> float: ...

    @property
    @abstractmethod
    def account_status(self) -> AccountStatus: ...

    @abstractmethod
    def deposit(self, amount: float) -> None: ...

    @abstractmethod
    def withdraw(self, amount: float) -> None: ...

    @abstractmethod
    def get_account_info(self) -> AccountInfo: ...


class BankAccount(AbstractAccount):
    def __init__(
        self,
        user: User,
        account_id: AccountUUID | None = None,
        balance: float = 0,
        account_status: AccountStatus = AccountStatus.Active,
        currency: AccountCurrency = AccountCurrency.RUB,
    ) -> None:
        super().__init__(user, account_id, balance, account_status)

        if not isinstance(currency, AccountCurrency):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("Account currency has invalid type")
        self._currency = currency

    def __str__(self) -> str:
        values = self.get_account_info()
        last_acc_digits = str(values["account_id"])[-4:]

        return f"""
        Account type: BankAccount
        Client: {values["user"].id}
        Last 4 dig.: {last_acc_digits}
        Status: {values["account_status"].name}
        Balance: {values["balance"]} {values["currency"].name}
        """

    @property
    def user(self) -> User:
        return self._user

    @property
    def account_id(self) -> AccountUUID:
        return self._account_id

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def account_status(self) -> AccountStatus:
        return self._account_status

    @property
    def currency(self) -> AccountCurrency:
        return self._currency

    def deposit(self, amount: float) -> None:
        self._validate_account_status()
        self._validate_amount_value(amount)

        try:
            balance_after_deposit = float(self._balance) + float(amount)
        except OverflowError:
            raise InvalidOperationError("Resulting balance is too large")

        if not isfinite(balance_after_deposit):
            raise InvalidOperationError("Resulting balance is too large")

        self._balance = balance_after_deposit

    def withdraw(self, amount: float) -> None:
        self._validate_account_status()
        self._validate_amount_value(amount)

        remaining_balance = self._balance - amount
        if remaining_balance < 0:
            raise InsufficientFundsError("Withdrawal amount is larger than balance.")

        self._balance = float(remaining_balance)

    def get_account_info(self) -> BankAccountInfo:
        return {
            "account_id": self._account_id,
            "account_status": self._account_status,
            "balance": self._balance,
            "currency": self._currency,
            "user": self._user,
        }
