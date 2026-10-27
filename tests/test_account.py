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
from baseop.uuid import AccountUUID, account_uuid


@pytest.fixture
def user():
    return User(id=uuid4(), name="John Doe")


@pytest.fixture
def account(user: User):
    return BankAccount(user)


@pytest.fixture
def frozen_account(user: User):
    return BankAccount(user, account_status=AccountStatus.Frozen)


@pytest.fixture
def closed_account(user: User):
    return BankAccount(user, account_status=AccountStatus.Closed)


def test_bank_account_init_with_random_uuid(user: User):
    account = BankAccount(user)
    assert isinstance(account.account_id, AccountUUID)


def test_bank_account_init_with_external_uuid(user: User):
    account_id = account_uuid()
    account = BankAccount(user, account_id)
    assert account.account_id == account_id


def test_bank_account_validates_external_uuid(user: User):
    account_id = "123qwerty"
    with pytest.raises(TypeError):
        BankAccount(user, account_id)  # pyright: ignore[reportArgumentType]


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


@pytest.mark.parametrize(
    "value",
    [
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
        10**400,
    ],
)
def test_deposit_wrong_amount_type(account: BankAccount, value: object):
    with pytest.raises(InvalidOperationError):
        account.deposit(value)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("value", [1, 100.0])
def test_deposit_good_amount_type(account: BankAccount, value: float):
    initial_value = account.balance
    account.deposit(value)
    assert account.balance == initial_value + value


def test_withdraw_state(account: BankAccount):
    account.deposit(100.0)
    account.withdraw(50.0)
    assert account.balance == 50.0


def test_withdraw_below_balance(account: BankAccount):
    account.deposit(100.0)
    with pytest.raises(InsufficientFundsError):
        account.withdraw(200.0)


@pytest.mark.parametrize(
    "value",
    [
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
        10**400,
    ],
)
def test_withdraw_wrong_value_type(account: BankAccount, value: object):
    account.deposit(1000000)
    with pytest.raises(InvalidOperationError):
        account.withdraw(value)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("value", [1, 100.0])
def test_withdraw_good_value_type(account: BankAccount, value: float):
    account.deposit(1000000)
    initial_value = account.balance
    account.withdraw(value)
    assert account.balance == initial_value - value


@pytest.mark.parametrize("amount", [10**400, -(10**400)])
def test_amount_unrepresentable_as_float(account: BankAccount, amount: float):
    with pytest.raises(InvalidOperationError):
        account.deposit(amount)
    assert account.balance == 0


def test_balance_unrepresentable_as_float(user: User):
    with pytest.raises(ValueError):
        BankAccount(user, balance=10**400)


def test_sum_of_valid_ints_overflows(user: User):
    account = BankAccount(user, balance=10**308)
    with pytest.raises(InvalidOperationError):
        account.deposit(10**308)
    assert account.balance == 10**308


def test_float_sum_overflows(account: BankAccount):
    account.deposit(1e308)
    with pytest.raises(InvalidOperationError):
        account.deposit(1e308)
    assert account.balance == 1e308


def test_int_amount_against_float_balance(account: BankAccount):
    account.deposit(1e308)
    with pytest.raises(InvalidOperationError):
        account.deposit(10**308)
    assert account.balance == 1e308
