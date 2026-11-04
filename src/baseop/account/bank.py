from baseop.client import Client
from baseop.uuid import AccountId

from .base import (
    AbstractAccount,
    AccountCurrency,
    AccountInfo,
    AccountStatus,
)


class BankAccountInfo(AccountInfo):
    currency: AccountCurrency


class BankAccount(AbstractAccount):
    def __init__(
        self,
        user: Client,
        account_id: AccountId | None = None,
        balance: float = 0,
        account_status: AccountStatus = AccountStatus.ACTIVE,
        currency: AccountCurrency = AccountCurrency.RUB,
    ) -> None:
        super().__init__(user, account_id, balance, account_status, currency)

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
    def total_value(self) -> float:
        return self._balance

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
