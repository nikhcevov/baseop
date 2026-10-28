from math import inf, nan
from uuid import uuid4

import pytest

from baseop.account import (
    InsufficientFundsError,
    InvalidOperationError,
    SavingsAccount,
)
from baseop.user import User


@pytest.fixture
def user():
    return User(id=uuid4(), name="John Doe")


@pytest.fixture
def account(user: User):
    return SavingsAccount(user)


def test_account_has_immutable_attributes(account: SavingsAccount):
    with pytest.raises(AttributeError):
        account.min_balance = 10  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.parametrize("value", [1, 100.0])
def test_account_init_with_good_min_balance(value: float, user: User):
    account = SavingsAccount(user, min_balance=value)
    assert account.min_balance == value


@pytest.mark.parametrize("value", [-1, -100.0, "balance", None])
def test_account_not_init_with_bad_min_balance(value: object, user: User):
    with pytest.raises(ValueError):
        SavingsAccount(user, min_balance=value)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("value", [1, 100.0])
def test_account_init_with_good_monthly_interest(value: float, user: User):
    account = SavingsAccount(user, monthly_interest=value)
    assert account.monthly_interest == value


@pytest.mark.parametrize("value", [-1, -100.0, "balance", None])
def test_account_not_init_with_bad_monthly_interest(value: object, user: User):
    with pytest.raises(ValueError):
        SavingsAccount(user, monthly_interest=value)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("value", [-1, -100.0, "interest", None, True, nan, inf])
def test_monthly_interest_validates_bad_args(account: SavingsAccount, value: object):
    with pytest.raises(ValueError):
        account.monthly_interest = value
    assert account.monthly_interest == 0


@pytest.mark.parametrize("value", [1, 0.5, 100.0])
def test_monthly_interest_validates_good_args(account: SavingsAccount, value: float):
    account.monthly_interest = value
    assert account.monthly_interest == value


def test_apply_monthly_interest_set_balance(user: User):
    account = SavingsAccount(user, balance=1000.0, monthly_interest=0.5)
    account.apply_monthly_interest()
    assert account.balance == 1500.0


def test_apply_monthly_interest_balance_overflow_raise_error(user: User):
    account = SavingsAccount(user, balance=1e308, monthly_interest=2)
    with pytest.raises(InvalidOperationError):
        account.apply_monthly_interest()


def test_apply_monthly_interest_balance_overflow_not_change_balance(user: User):
    account = SavingsAccount(user, balance=1e308, monthly_interest=2)
    balance_before = account.balance
    with pytest.raises(InvalidOperationError):
        account.apply_monthly_interest()
    assert account.balance == balance_before


def test_withdraw_minimal_balance_error(user: User):
    account = SavingsAccount(user, balance=100.0, min_balance=50.0)
    with pytest.raises(InsufficientFundsError):
        account.withdraw(60.0)


def test_withdraw_minimal_balance_error_not_change_balance(user: User):
    account = SavingsAccount(user, balance=100.0, min_balance=50.0)
    balance_before = account.balance
    with pytest.raises(InsufficientFundsError):
        account.withdraw(60.0)
    assert account.balance == balance_before


def test_withdraw_balance_update(user: User):
    account = SavingsAccount(user, balance=100.0, min_balance=50.0)
    account.withdraw(25.0)
    assert account.balance == 75.0
