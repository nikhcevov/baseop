from uuid import uuid4

import pytest

from baseop.account import (
    InsufficientFundsError,
    InvalidOperationError,
    PremiumAccount,
)
from baseop.user import User


@pytest.fixture
def user():
    return User(id=uuid4(), name="John Doe")


@pytest.fixture
def account(user: User):
    return PremiumAccount(
        user,
        balance=1000.0,
        withdrawal_limit=500.0,
        overdraft_limit=200.0,
        fixed_fee=100.0,
    )


def test_account_has_premium_settings(account: PremiumAccount):
    assert account.withdrawal_limit == 500.0
    assert account.overdraft_limit == 200.0
    assert account.fixed_fee == 100.0


def test_withdraw_applies_limit_and_fee(account: PremiumAccount):
    account.withdraw(500.0)
    assert account.balance == 400.0


def test_withdraw_above_limit_denied(account: PremiumAccount):
    balance_before = account.balance
    with pytest.raises(InvalidOperationError):
        account.withdraw(500.01)
    assert account.balance == balance_before


def test_withdraw_can_use_overdraft(user: User):
    account = PremiumAccount(
        user,
        balance=100.0,
        withdrawal_limit=500.0,
        overdraft_limit=200.0,
        fixed_fee=0.0,
    )
    account.withdraw(200.0)
    assert account.balance == -100.0


def test_withdraw_below_overdraft_denied(user: User):
    account = PremiumAccount(
        user,
        balance=100.0,
        withdrawal_limit=500.0,
        overdraft_limit=200.0,
        fixed_fee=0.0,
    )
    balance_before = account.balance
    with pytest.raises(InsufficientFundsError):
        account.withdraw(300.01)
    assert account.balance == balance_before


def test_get_account_info_includes_premium_fields(account: PremiumAccount):
    info = account.get_account_info()
    assert info["withdrawal_limit"] == 500.0
    assert info["overdraft_limit"] == 200.0
    assert info["fixed_fee"] == 100.0


def test_str_reports_premium_account(account: PremiumAccount):
    assert "Account type: PremiumAccount" in str(account)
