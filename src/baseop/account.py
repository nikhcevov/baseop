from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from baseop.uuid import AccountUUID, accout_uuid


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


class AbstractAccount:
    account_id: AccountUUID
    user: User
    balance: float
    account_status: AccountStatus

    def deposit(self, amount: float) -> None: ...
    def withdraw(self, amount: float) -> None: ...
    def get_account_info(self) -> str: ...


class BankAccount(AbstractAccount):
    def __init__(
        self,
        user: User,
        balance: float = 0,
        account_status: AccountStatus = AccountStatus.Active,
        currency: AccountCurrency = AccountCurrency.RUB,
    ) -> None:
        self.account_id = accout_uuid()
        self.user = user
        self.balance = balance
        self.account_status = account_status
        self.currency = currency

    def __str__(self) -> str:
        last_acc_digits = str(self.account_id)[-4:]

        return f"""
        Account type: BankAccount
        Client: {self.user}
        Last 4 dig.: {last_acc_digits}
        Status: {self.account_status}
        Balance: {self.balance} {self.currency}
        """

    def _validate_account_status(self):
        if self.account_status == AccountStatus.Closed:
            raise AccountClosedError("Account is closed, operation denied.")
        if self.account_status == AccountStatus.Frozen:
            raise AccountFrozenError("Account is frozen, operation denied.")

    def _validate_amount_value(self, amount):
        if not isinstance(amount, float):
            raise InvalidOperationError("Amount is invalid value.")
        if amount < 0:
            raise InvalidOperationError("Amount is not positive value.")

    def deposit(self, amount: float) -> None:
        self._validate_account_status()
        self._validate_amount_value(amount)
        self.balance += amount

    def withdraw(self, amount: float) -> None:
        self._validate_account_status()
        self._validate_amount_value(amount)

        remaining_balance = self.balance - amount
        if remaining_balance < 0:
            raise InsufficientFundsError("Withdrawal amount is larger than balance.")

        self.balance = remaining_balance

    def get_account_info(self) -> str:
        return f"account: {self.account_id};\nuser: {self.user};\nbalance: {self.balance}\n; status: {self.account_status}; currency: {self.currency}"
