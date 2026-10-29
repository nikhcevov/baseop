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


class PremiumAccountInfo(AccountInfo):
    withdrawal_limit: float
    overdraft_limit: float
    fixed_fee: float


class PremiumAccount(AbstractAccount):
    def __init__(
        self,
        user: User,
        account_id: AccountUUID | None = None,
        balance: float = 0,
        account_status: AccountStatus = AccountStatus.Active,
        # Withdrawal limit is premium account only feature, I omit it intentionally for other account types
        withdrawal_limit: float = 1_000_000.0,
        overdraft_limit: float = 50_000.0,
        fixed_fee: float = 100.0,
    ) -> None:
        if not verify_strict_numeric(withdrawal_limit):
            raise ValueError("Withdrawal limit must be valid number")
        if withdrawal_limit < 0:
            raise ValueError("Withdrawal limit must be non negative")
        self._withdrawal_limit = withdrawal_limit

        if not verify_strict_numeric(overdraft_limit):
            raise ValueError("Overdraft limit must be valid number")
        if overdraft_limit < 0:
            raise ValueError("Overdraft limit must be non negative")
        self._overdraft_limit = overdraft_limit

        if not verify_strict_numeric(fixed_fee):
            raise ValueError("Fixed fee must be valid number")
        if fixed_fee < 0:
            raise ValueError("Fixed fee must be non negative")
        self._fixed_fee = fixed_fee

        super().__init__(user, account_id, balance, account_status)

    def __str__(self) -> str:
        values = self.get_account_info()
        last_acc_digits = str(values["account_id"])[-4:]

        return f"""
        Account type: PremiumAccount
        Client: {values["user"].id}
        Last 4 dig.: {last_acc_digits}
        Status: {values["account_status"].name}
        Balance: {values["balance"]}
        Withdrawal limit: {values["withdrawal_limit"]}
        Overdraft limit: {values["overdraft_limit"]}
        Fixed fee: {values["fixed_fee"]}
        """

    def _validate_setter_number(self, value: object) -> float:
        if not verify_strict_numeric(value):
            raise ValueError("Value must be valid number")
        if value < 0:
            raise ValueError("Value must be non negative")
        return float(value)

    @property
    def withdrawal_limit(self) -> float:
        return self._withdrawal_limit

    @withdrawal_limit.setter
    def withdrawal_limit(self, value: float) -> None:
        self._withdrawal_limit = self._validate_setter_number(value)

    @property
    def overdraft_limit(self) -> float:
        return self._overdraft_limit

    @overdraft_limit.setter
    def overdraft_limit(self, value: float) -> None:
        self._overdraft_limit = self._validate_setter_number(value)

    @property
    def fixed_fee(self) -> float:
        return self._fixed_fee

    @fixed_fee.setter
    def fixed_fee(self, value: float) -> None:
        self._fixed_fee = self._validate_setter_number(value)

    def withdraw(self, amount: float) -> None:
        self._validate_account_status()
        self._validate_amount_value(amount)

        if amount > self._withdrawal_limit:
            raise InvalidOperationError("Amount must be less than withdrawal limit.")

        remaining_after_withdrawal = self._balance - amount - self._fixed_fee
        if remaining_after_withdrawal < -self._overdraft_limit:
            raise InsufficientFundsError(
                "Resulting balance is below maximum overdraft."
            )

        self._balance = float(remaining_after_withdrawal)

    def get_account_info(self) -> PremiumAccountInfo:
        base_values = super().get_account_info()

        return {
            **base_values,
            "withdrawal_limit": self._withdrawal_limit,
            "overdraft_limit": self._overdraft_limit,
            "fixed_fee": self._fixed_fee,
        }
