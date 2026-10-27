from math import inf, nan
from uuid import uuid4

import pytest

from baseop.account import (
    AccountClosedError,
    AccountCurrency,
    AccountFrozenError,
    AccountStatus,
    BankAccount,
    InsufficientFundsError,
    InvalidOperationError,
    User,
)
from baseop.uuid import AccountUUID


@pytest.fixture
def user():
    return User(id=uuid4(), name="John Doe")


@pytest.fixture
def account(user):
    return BankAccount(user)


@pytest.fixture
def frozen_account(user):
    return BankAccount(user, account_status=AccountStatus.Frozen)


@pytest.fixture
def closed_account(user):
    return BankAccount(user, account_status=AccountStatus.Closed)


def test_bank_account_init_with_uuid(account: BankAccount):
    assert isinstance(account.account_id, AccountUUID)


def test_bank_account_init_with_no_balance(account: BankAccount):
    assert account.balance == 0


def test_bank_account_init_validate_balance(user: User):
    bad_balance = [-1000.0, inf, -inf, nan]
    good_balance = [0, 100, 1000.0]

    for value in bad_balance:
        with pytest.raises(ValueError):
            BankAccount(user, balance=value)

    for value in good_balance:
        assert BankAccount(user, balance=value).balance == value


def test_bank_account_init_with_user(user: User):
    account = BankAccount(user)
    assert account.user == user


def test_bank_account_init_validate_user():
    user = {"name": "John", id: "1"}
    with pytest.raises(TypeError):
        BankAccount(user=user)  # pyright: ignore[reportArgumentType]


def test_bank_account_init_with_active_account(account: BankAccount):
    assert account.account_status == AccountStatus.Active


def test_bank_account_init_with_frozen_account(user: User):
    account = BankAccount(user, account_status=AccountStatus.Frozen)
    assert account.account_status == AccountStatus.Frozen


def test_bank_account_init_with_closed_account(user: User):
    account = BankAccount(user, account_status=AccountStatus.Closed)
    assert account.account_status == AccountStatus.Closed


def test_bank_account_has_immutable_attributes(account: BankAccount, user: User):
    with pytest.raises(AttributeError):
        account.balance = 1000.0  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        account.account_id = "abcdefgh"  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        account.user = user  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        account.account_status = AccountStatus.Frozen  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        account.currency = AccountCurrency.CNY  # pyright: ignore[reportAttributeAccessIssue]


def test_deposit_frozen_account_denied(frozen_account: BankAccount):
    with pytest.raises(AccountFrozenError):
        frozen_account.deposit(100.0)


def test_withdraw_frozen_account_denied(frozen_account: BankAccount):
    with pytest.raises(AccountFrozenError):
        frozen_account.withdraw(100.0)


def test_deposit_closed_account_denied(closed_account: BankAccount):
    with pytest.raises(AccountClosedError):
        closed_account.deposit(100.0)


def test_withdraw_closed_account_denied(closed_account: BankAccount):
    with pytest.raises(AccountClosedError):
        closed_account.withdraw(100.0)


def test_deposit(account: BankAccount):
    account.deposit(100.0)
    assert account.balance == 100.0

    account.deposit(200.0)
    assert account.balance == 300.0


def test_deposit_validation(account: BankAccount):
    bad_values = [
        inf,
        -inf,
        nan,
        0,
        -1,
        -1000.0,
        "value",
        {"name": "John"},
        2 + 3j,
        [1],
        (1, 2),
        {1},
        True,
        None,
    ]
    for value in bad_values:
        with pytest.raises(InvalidOperationError):
            account.deposit(value)

    good_values = [1, 100.0]
    for value in good_values:
        initial_value = account.balance
        account.deposit(value)
        assert account.balance == initial_value + value


def test_withdraw(account: BankAccount):
    account.deposit(100.0)
    account.withdraw(50.0)
    assert account.balance == 50.0


def test_withdraw_below_balance(account: BankAccount):
    account.deposit(100.0)
    with pytest.raises(InsufficientFundsError):
        account.withdraw(200.0)


def test_withdraw_validation(account: BankAccount):
    account.deposit(1000000)
    bad_values = [
        inf,
        -inf,
        nan,
        0,
        -1,
        -1000.0,
        "value",
        {"name": "John"},
        2 + 3j,
        [1],
        (1, 2),
        {1},
        True,
        None,
    ]
    for value in bad_values:
        with pytest.raises(InvalidOperationError):
            account.withdraw(value)

    good_values = [1, 100.0]
    for value in good_values:
        initial_value = account.balance
        account.withdraw(value)
        assert account.balance == initial_value - value
