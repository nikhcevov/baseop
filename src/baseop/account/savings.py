from math import isfinite

from baseop.user import User
from baseop.uuid import AccountUUID

from .base import (
    AbstractAccount,
    AccountInfo,
    AccountStatus,
    InsufficientFundsError,
    InvalidOperationError,
    verify_strict_numeric,
)


class SavingsAccountInfo(AccountInfo):
    min_balance: float
    monthly_interest: float


class SavingsAccount(AbstractAccount):
    def __init__(
        self,
        user: User,
        account_id: AccountUUID | None = None,
        balance: float = 0,
        account_status: AccountStatus = AccountStatus.Active,
        min_balance: float = 0,
        monthly_interest: float = 0,
    ) -> None:
        if not verify_strict_numeric(min_balance):
            raise ValueError("Minimal balance must be valid number")
        if min_balance < 0:
            raise ValueError("Minimal balance must be non negative")
        self._min_balance = min_balance

        if not verify_strict_numeric(monthly_interest):
            raise ValueError("Monthly interest ust be valid number")
        if monthly_interest < 0:
            raise ValueError("Monthly interest must be non negative")
        self._monthly_interest = monthly_interest
        super().__init__(user, account_id, balance, account_status)

    def __str__(self) -> str:
        values = self.get_account_info()
        last_acc_digits = str(values["account_id"])[-4:]

        return f"""
        Account type: SavingsAccount
        Client: {values["user"].id}
        Last 4 dig.: {last_acc_digits}
        Status: {values["account_status"].name}
        Balance: {values["balance"]}
        Min Balance: {values["min_balance"]}
        Monthly interest: {values["monthly_interest"]}
        """

    @property
    def min_balance(self) -> float:
        return self._min_balance

    @property
    def monthly_interest(self) -> float:
        return self._monthly_interest

    @monthly_interest.setter
    def monthly_interest(self, interest) -> None:
        if not verify_strict_numeric(interest):
            raise ValueError("Monthly interest ust be valid number")
        if interest < 0:
            raise ValueError("Monthly interest must be non negative")
        if self._monthly_interest == interest:
            raise ValueError("Monthly interest must be different from current one")
        self._monthly_interest = interest

    def apply_monthly_interest(self) -> None:
        """Adds monthly interest to balance"""
        self._validate_account_status()
        try:
            balance_increase_value = self._balance * self._monthly_interest
            resulting_balance = self._balance + balance_increase_value
        except OverflowError:
            raise InvalidOperationError("Resulting balance increase is too high")

        if not isfinite(resulting_balance):
            raise InvalidOperationError("Resulting balance increase is too high")

        self._balance = float(resulting_balance)

    def deposit(self, amount: float) -> None:
        self._add_to_balance(amount)

    def withdraw(self, amount: float) -> None:
        self._validate_account_status()
        self._validate_amount_value(amount)

        remaining_balance = self._balance - amount
        if remaining_balance < self.min_balance:
            raise InsufficientFundsError("Resulting balance is below minimum balance.")

        self._balance = float(remaining_balance)

    def get_account_info(self) -> SavingsAccountInfo:
        base_values = self._account_info()

        return {
            **base_values,
            "min_balance": self._min_balance,
            "monthly_interest": self._monthly_interest,
        }
