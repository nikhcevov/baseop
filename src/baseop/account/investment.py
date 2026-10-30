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
    total_value: float


class InvestmentAccount(AbstractAccount):
    def __init__(
        self,
        user: User,
        account_id: AccountUUID | None = None,
        balance: float = 0,
        account_status: AccountStatus = AccountStatus.Active,
        portfolio: InvestmentPortfolio | None = None,
    ) -> None:
        super().__init__(user, account_id, balance, account_status)
        self._portfolio = {asset: 0.0 for asset in InvestmentAsset}

        for asset, amount in (portfolio or {}).items():
            self._validate_asset_type(asset)
            self._validate_amount_value(amount)
            self._portfolio[asset] = float(amount)

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
        Cash balance: {values["balance"]}
        Total value: {values["total_value"]}
        Portfolio: {portfolio}
        """

    @property
    def portfolio(self) -> InvestmentPortfolio:
        return dict(self._portfolio)

    @property
    def total_value(self) -> float:
        return self._balance + sum(self._portfolio.values())

    def _validate_asset_type(self, asset) -> None:
        if not isinstance(asset, InvestmentAsset):
            raise InvalidOperationError("Unknown asset type")

    def buy(self, amount: float, asset: InvestmentAsset) -> None:
        self._validate_account_status()
        self._validate_asset_type(asset)
        self._validate_amount_value(amount)

        if amount > self._balance:
            raise InsufficientFundsError("Not enough free funds.")

        try:
            holding_after_buy = self._portfolio[asset] + float(amount)
        except OverflowError:
            raise InvalidOperationError("Portfolio value is too large.")
        if not isfinite(holding_after_buy):
            raise InvalidOperationError("Portfolio value is too large.")

        self._balance = float(self._balance - amount)
        self._portfolio[asset] = holding_after_buy

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

        try:
            balance_after_sell = self._balance + float(amount)
        except OverflowError:
            raise InvalidOperationError("Resulting balance is too large.")
        if not isfinite(balance_after_sell):
            raise InvalidOperationError("Resulting balance is too large.")

        self._portfolio[asset] -= amount
        self._balance = balance_after_sell

    def deposit(self, amount: float) -> None:
        self._add_to_balance(amount)

    def withdraw(self, amount: float) -> None:
        self._subtract_from_balance(amount)

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
            "total_value": self.total_value,
        }
