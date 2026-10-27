from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from math import isfinite
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


class AccountFrozenError(Exception):
    pass


class AccountClosedError(Exception):
    pass


class InvalidOperationError(Exception):
    pass


class InsufficientFundsError(Exception):
    pass


class AbstractAccount(ABC):
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
    def get_account_info(self) -> str: ...


def verify_strict_numeric(value) -> bool:
    numeric = isinstance(value, (int, float))
    is_bool = isinstance(value, bool)
    if numeric and not is_bool:
        finite = isfinite(value)
        return finite
    return False


class BankAccount(AbstractAccount):
    def __init__(
        self,
        user: User,
        balance: float = 0,
        account_status: AccountStatus = AccountStatus.Active,
        currency: AccountCurrency = AccountCurrency.RUB,
    ) -> None:
        self._account_id = account_uuid()

        if not isinstance(user, User):
            raise TypeError("User has invalid type")
        self._user = user

        if balance < 0:
            raise ValueError("Balance must be non negative")
        if not verify_strict_numeric(balance):
            raise ValueError("Balance must be valid number")
        self._balance = balance

        if not isinstance(account_status, AccountStatus):
            raise TypeError("Account status has invalid type")
        self._account_status = account_status

        if not isinstance(currency, AccountCurrency):
            raise TypeError("Account currency has invalid type")
        self._currency = currency

    def __str__(self) -> str:
        last_acc_digits = str(self._account_id)[-4:]

        return f"""
        Account type: BankAccount
        Client: {self._user}
        Last 4 dig.: {last_acc_digits}
        Status: {self._account_status}
        Balance: {self._balance} {self._currency}
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

    def _validate_account_status(self):
        if self._account_status == AccountStatus.Closed:
            raise AccountClosedError("Account is closed, operation denied.")
        if self._account_status == AccountStatus.Frozen:
            raise AccountFrozenError("Account is frozen, operation denied.")

    def _validate_amount_value(self, amount):
        if not verify_strict_numeric(amount):
            raise InvalidOperationError("Amount must be valid value.")
        if amount <= 0:
            raise InvalidOperationError("Amount must be positive value.")

    def deposit(self, amount: float) -> None:
        self._validate_account_status()
        self._validate_amount_value(amount)
        self._balance += amount

    def withdraw(self, amount: float) -> None:
        self._validate_account_status()
        self._validate_amount_value(amount)

        remaining_balance = self._balance - amount
        if remaining_balance < 0:
            raise InsufficientFundsError("Withdrawal amount is larger than balance.")

        self._balance = remaining_balance

    def get_account_info(self) -> str:
        return f"account: {self._account_id};\nuser: {self._user};\nbalance: {self._balance}\n; status: {self._account_status}; currency: {self._currency}"
