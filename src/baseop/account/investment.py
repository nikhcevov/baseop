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
    verify_strict_numeric,
)


class InvestmentAsset(Enum):
    stocks = 1
    bonds = 2
    etf = 3


InvestmentPortfolio = dict[InvestmentAsset, float]


class InvestmentAccountInfo(AccountInfo):
    portfolio: InvestmentPortfolio


class InvestmentAccount(AbstractAccount):
    def __init__(
        self,
        user: User,
        account_id: AccountUUID | None = None,
        account_status: AccountStatus = AccountStatus.Active,
        portfolio: InvestmentPortfolio | None = None,
    ) -> None:
        super().__init__(user, account_id, balance=0, account_status=account_status)
        self._portfolio = {asset: 0.0 for asset in InvestmentAsset}

        for asset, amount in (portfolio or {}).items():
            self._add_holding(amount, asset)

    def __str__(self) -> str:
        values = self.get_account_info()
        last_acc_digits = str(values["account_id"])[-4:]
        portfolio = "".join(
            f"  - {asset.name}: {amount}\n" for asset, amount in self._portfolio.items()
        )

        return f"""
        Account type: InvestmentAccount
        Client: {values["user"].id}
        Last 4 dig.: {last_acc_digits}
        Status: {values["account_status"].name}
        Balance: {values["balance"]}
        Portfolio: {portfolio}
        """

    @property
    def portfolio(self) -> InvestmentPortfolio:
        return dict(self._portfolio)

    def _validate_asset_type(self, asset) -> None:
        if not isinstance(asset, InvestmentAsset):
            raise InvalidOperationError("Unknown asset type")

    def _add_holding(self, amount: float, asset: InvestmentAsset) -> None:
        self._validate_asset_type(asset)
        self._validate_amount_value(amount)
        if not isfinite(self._balance + amount):
            raise InvalidOperationError("Portfolio value is too large.")
        self._portfolio[asset] += amount
        self._balance += amount

    def buy(self, amount: float, asset: InvestmentAsset) -> None:
        self._validate_account_status()
        self._add_holding(amount, asset)

    def sell(
        self,
        amount: float,
        asset: InvestmentAsset,
    ) -> None:
        self._validate_account_status()
        self._validate_asset_type(asset)
        self._validate_amount_value(amount)

        if self._portfolio[asset] < amount:
            raise InsufficientFundsError("Not enough funds in asset.")

        self._portfolio[asset] -= amount
        self._balance -= amount

    def deposit(self, amount: float) -> None:
        self._add_to_balance(amount)

    def withdraw(self, amount: float) -> None:
        self._validate_account_status()
        self._validate_amount_value(amount)

        if self._balance < amount:
            raise InsufficientFundsError("Withdrawal amount is larger than balance.")

        withdrawn = 0.0
        for asset in InvestmentAsset:
            taken = min(self._portfolio[asset], amount - withdrawn)
            self._portfolio[asset] -= taken
            withdrawn += taken
            if withdrawn == amount:
                break

        self._balance -= withdrawn

    def project_yearly_growth(
        self, growth_rates: dict[InvestmentAsset, float]
    ) -> float:
        for asset, rate in growth_rates.items():
            self._validate_asset_type(asset)
            if not verify_strict_numeric(rate):
                raise InvalidOperationError("Growth rate must be valid number.")

        for asset in InvestmentAsset:
            if asset not in growth_rates:
                raise InvalidOperationError("Growth rate is missing for asset.")

        return sum(
            self._portfolio[asset] * growth_rates[asset] for asset in InvestmentAsset
        )

    def get_account_info(self) -> InvestmentAccountInfo:
        base_values = self._account_info()

        return {
            **base_values,
            "portfolio": dict(self._portfolio),
        }
