from enum import Enum

from baseop.user import User
from baseop.uuid import AccountUUID

from .base import (
    AbstractAccount,
    AccountInfo,
    AccountStatus,
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
        self._add_to_balance(amount)

    def withdraw(self, amount: float) -> None:
        self._subtract_from_balance(amount)

    def get_account_info(self) -> BankAccountInfo:
        base_values = self._account_info()

        return {
            **base_values,
            "currency": self._currency,
        }
