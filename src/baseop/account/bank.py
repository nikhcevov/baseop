from enum import Enum
from math import isfinite

from baseop.user import User
from baseop.uuid import AccountUUID

from .base import (
    AbstractAccount,
    AccountInfo,
    AccountStatus,
    InsufficientFundsError,
    InvalidOperationError,
)


class AccountCurrency(Enum):
    RUB = 1
    USD = 2
    EUR = 3
    KZT = 4
    CNY = 5


class BankAccountInfo(AccountInfo):
    currency: AccountCurrency


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
