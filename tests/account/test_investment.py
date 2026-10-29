from uuid import uuid4

import pytest

from baseop.account import (
    InsufficientFundsError,
    InvalidOperationError,
    InvestmentAccount,
    InvestmentAsset,
)
from baseop.user import User


@pytest.fixture
def user():
    return User(id=uuid4(), name="John Doe")


@pytest.fixture
def account(user: User):
    return InvestmentAccount(
        user,
        portfolio={
            InvestmentAsset.stocks: 1000.0,
            InvestmentAsset.bonds: 500.0,
            InvestmentAsset.etf: 2000.0,
        },
    )


def test_account_init_with_portfolio(account: InvestmentAccount):
    assert account.balance == 3500.0
    assert account.portfolio == {
        InvestmentAsset.stocks: 1000.0,
        InvestmentAsset.bonds: 500.0,
        InvestmentAsset.etf: 2000.0,
    }


def test_buy_updates_asset_and_balance(account: InvestmentAccount):
    account.buy(500.0, InvestmentAsset.etf)

    assert account.portfolio[InvestmentAsset.etf] == 2500.0
    assert account.balance == 4000.0


def test_sell_updates_asset_and_balance(account: InvestmentAccount):
    account.sell(400.0, InvestmentAsset.stocks)

    assert account.portfolio[InvestmentAsset.stocks] == 600.0
    assert account.balance == 3100.0


def test_sell_more_than_asset_denied(account: InvestmentAccount):
    balance_before = account.balance

    with pytest.raises(InsufficientFundsError):
        account.sell(600.0, InvestmentAsset.bonds)

    assert account.portfolio[InvestmentAsset.bonds] == 500.0
    assert account.balance == balance_before


def test_project_yearly_growth(account: InvestmentAccount):
    growth = account.project_yearly_growth(
        {
            InvestmentAsset.stocks: 0.10,
            InvestmentAsset.bonds: 0.04,
            InvestmentAsset.etf: 0.07,
        }
    )

    assert growth == pytest.approx(260.0)


def test_get_account_info_includes_portfolio(account: InvestmentAccount):
    info = account.get_account_info()

    assert info["balance"] == 3500.0
    assert info["portfolio"] == account.portfolio


def test_str_reports_investment_account(account: InvestmentAccount):
    assert "Account type: InvestmentAccount" in str(account)


def test_buy_rejects_unknown_asset(account: InvestmentAccount):
    with pytest.raises(InvalidOperationError):
        account.buy(100.0, "etf")  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("amount", [0, -100.0])
def test_buy_rejects_non_positive_amount(account: InvestmentAccount, amount: float):
    with pytest.raises(InvalidOperationError):
        account.buy(amount, InvestmentAsset.etf)


def test_withdraw_raises_insufficient_when_above_balance(account: InvestmentAccount):
    with pytest.raises(InsufficientFundsError):
        account.withdraw(3500.01)


def test_withdraw_follows_base_contract(account: InvestmentAccount):
    balance_before = account.balance
    account.withdraw(100.0)

    assert account.balance == balance_before - 100.0
    assert sum(account.portfolio.values()) == account.balance
