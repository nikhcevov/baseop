from uuid import uuid4

import pytest

from baseop.account import (
    InsufficientFundsError,
    InvalidOperationError,
    InvestmentAccount,
    InvestmentAsset,
)
from baseop.user import User

INITIAL_PORTFOLIO = {
    InvestmentAsset.stocks: 1000.0,
    InvestmentAsset.bonds: 500.0,
    InvestmentAsset.etf: 2000.0,
}


@pytest.fixture
def user():
    return User(id=uuid4(), name="John Doe")


@pytest.fixture
def account(user: User):
    return InvestmentAccount(user, portfolio=dict(INITIAL_PORTFOLIO))


@pytest.fixture
def funded_account(user: User):
    return InvestmentAccount(
        user,
        balance=1000.0,
        portfolio=dict(INITIAL_PORTFOLIO),
    )


def test_account_init_with_portfolio(account: InvestmentAccount):
    assert account.balance == 0
    assert account.portfolio == INITIAL_PORTFOLIO
    assert account.total_value == 3500.0


def test_account_init_with_free_balance(user: User):
    account = InvestmentAccount(
        user,
        balance=1000.0,
        portfolio=dict(INITIAL_PORTFOLIO),
    )
    assert account.balance == 1000.0
    assert account.total_value == 4500.0


@pytest.mark.parametrize("value", [-1, 0, "amount", None])
def test_account_init_validates_bad_portfolio_amount(value: object, user: User):
    with pytest.raises(InvalidOperationError):
        InvestmentAccount(
            user,
            portfolio={InvestmentAsset.stocks: value},  # pyright: ignore[reportArgumentType]
        )


def test_deposit_increases_cash_without_touching_portfolio(account: InvestmentAccount):
    account.deposit(100.0)

    assert account.balance == 100.0
    assert account.portfolio == INITIAL_PORTFOLIO
    assert account.total_value == 3600.0


def test_withdraw_after_deposit_returns_exactly_deposited_cash(
    account: InvestmentAccount,
):
    account.deposit(100.0)
    account.withdraw(100.0)

    assert account.balance == 0
    assert account.portfolio == INITIAL_PORTFOLIO
    assert account.total_value == 3500.0


def test_withdraw_does_not_liquidate_portfolio(account: InvestmentAccount):
    with pytest.raises(InsufficientFundsError):
        account.withdraw(100.0)

    assert account.portfolio == INITIAL_PORTFOLIO
    assert account.total_value == 3500.0


def test_withdraw_reduces_only_cash(funded_account: InvestmentAccount):
    funded_account.withdraw(400.0)

    assert funded_account.balance == 600.0
    assert funded_account.portfolio == INITIAL_PORTFOLIO
    assert funded_account.total_value == 4100.0


def test_buy_moves_cash_into_portfolio(funded_account: InvestmentAccount):
    total_before = funded_account.total_value

    funded_account.buy(500.0, InvestmentAsset.etf)

    assert funded_account.balance == 500.0
    assert funded_account.portfolio[InvestmentAsset.etf] == 2500.0
    assert funded_account.total_value == total_before


def test_buy_without_free_funds_denied(account: InvestmentAccount):
    with pytest.raises(InsufficientFundsError):
        account.buy(100.0, InvestmentAsset.etf)

    assert account.balance == 0
    assert account.portfolio == INITIAL_PORTFOLIO
    assert account.total_value == 3500.0


def test_buy_above_free_funds_denied(funded_account: InvestmentAccount):
    balance_before = funded_account.balance
    portfolio_before = funded_account.portfolio

    with pytest.raises(InsufficientFundsError):
        funded_account.buy(1000.01, InvestmentAsset.etf)

    assert funded_account.balance == balance_before
    assert funded_account.portfolio == portfolio_before


def test_buy_rejects_unknown_asset(funded_account: InvestmentAccount):
    with pytest.raises(InvalidOperationError):
        funded_account.buy(100.0, "etf")  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("amount", [0, -100.0])
def test_buy_rejects_non_positive_amount(
    funded_account: InvestmentAccount, amount: float
):
    with pytest.raises(InvalidOperationError):
        funded_account.buy(amount, InvestmentAsset.etf)


def test_buy_portfolio_overflow_denied(funded_account: InvestmentAccount):
    overflow_account = InvestmentAccount(
        funded_account.user,
        balance=1e308,
        portfolio={InvestmentAsset.stocks: 1e308},
    )
    balance_before = overflow_account.balance

    with pytest.raises(InvalidOperationError):
        overflow_account.buy(1e308, InvestmentAsset.stocks)

    assert overflow_account.balance == balance_before
    assert overflow_account.portfolio[InvestmentAsset.stocks] == 1e308


def test_sell_returns_cash_from_portfolio(account: InvestmentAccount):
    total_before = account.total_value

    account.sell(400.0, InvestmentAsset.stocks)

    assert account.balance == 400.0
    assert account.portfolio[InvestmentAsset.stocks] == 600.0
    assert account.total_value == total_before


def test_sell_more_than_asset_denied(account: InvestmentAccount):
    balance_before = account.balance

    with pytest.raises(InsufficientFundsError):
        account.sell(600.0, InvestmentAsset.bonds)

    assert account.portfolio[InvestmentAsset.bonds] == 500.0
    assert account.balance == balance_before


def test_sell_balance_overflow_denied(user: User):
    account = InvestmentAccount(
        user,
        balance=1e308,
        portfolio={InvestmentAsset.stocks: 1e308},
    )
    portfolio_before = account.portfolio

    with pytest.raises(InvalidOperationError):
        account.sell(1e308, InvestmentAsset.stocks)

    assert account.balance == 1e308
    assert account.portfolio == portfolio_before


def test_project_yearly_growth(account: InvestmentAccount):
    growth = account.project_yearly_growth(
        {
            InvestmentAsset.stocks: 0.10,
            InvestmentAsset.bonds: 0.04,
            InvestmentAsset.etf: 0.07,
        }
    )

    assert growth == pytest.approx(260.0)


def test_get_account_info_includes_cash_portfolio_and_total(
    funded_account: InvestmentAccount,
):
    info = funded_account.get_account_info()

    assert info["balance"] == 1000.0
    assert info["portfolio"] == funded_account.portfolio
    assert info["total_value"] == 4500.0


def test_str_reports_investment_account(account: InvestmentAccount):
    assert "Account type: InvestmentAccount" in str(account)
