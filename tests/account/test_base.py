from math import inf, nan
from uuid import uuid4

import pytest

from baseop.account import (
    AbstractAccount,
    AccountClosedError,
    AccountFrozenError,
    AccountStatus,
    InsufficientFundsError,
    InvalidOperationError,
)
from baseop.user import User
from baseop.uuid import AccountUUID


@pytest.fixture
def user():
    return User(id=uuid4(), name="John Doe")


@pytest.fixture
def account(user: User):
    return AbstractAccount(user)


@pytest.fixture
def frozen_account(user: User):
    return AbstractAccount(user, account_status=AccountStatus.Frozen)


@pytest.fixture
def closed_account(user: User):
    return AbstractAccount(user, account_status=AccountStatus.Closed)


def test_bank_account_init_with_random_uuid(user: User):
    account = AbstractAccount(user)
    assert isinstance(account.account_id, AccountUUID)


@pytest.mark.parametrize("uuid", [AccountUUID("123qwert"), None])
def test_bank_account_init_with_good_external_uuid(uuid: object, user: User):
    account = AbstractAccount(user, uuid)  # pyright: ignore[reportArgumentType]
    assert bool(account.account_id)


@pytest.mark.parametrize("uuid", ["123qwerty", "1", 1, (1, 2)])
def test_bank_account_validates_bad_external_uuid(uuid: object, user: User):
    with pytest.raises(TypeError):
        AbstractAccount(user, uuid)  # pyright: ignore[reportArgumentType]


def test_bank_account_init_with_no_balance(account: AbstractAccount):
    assert account.balance == 0


@pytest.mark.parametrize("value", [-1000.0, inf, -inf, nan])
def test_bank_account_init_validate_bad_balance(value: float, user: User):
    with pytest.raises(ValueError):
        AbstractAccount(user, balance=value)


@pytest.mark.parametrize("value", [0, 100, 1000.0])
def test_bank_account_init_validate_good_balance(value: float, user: User):
    assert AbstractAccount(user, balance=value).balance == value


def test_bank_account_init_with_user(user: User):
    account = AbstractAccount(user)
    assert account.user == user


def test_bank_account_init_validate_user():
    user = {"name": "John", id: "1"}
    with pytest.raises(TypeError):
        AbstractAccount(user=user)  # pyright: ignore[reportArgumentType]


def test_bank_account_init_with_active_account(account: AbstractAccount):
    assert account.account_status == AccountStatus.Active


def test_bank_account_init_with_frozen_account(user: User):
    account = AbstractAccount(user, account_status=AccountStatus.Frozen)
    assert account.account_status == AccountStatus.Frozen


def test_bank_account_init_with_closed_account(user: User):
    account = AbstractAccount(user, account_status=AccountStatus.Closed)
    assert account.account_status == AccountStatus.Closed


def test_bank_account_has_immutable_attributes(account: AbstractAccount, user: User):
    with pytest.raises(AttributeError):
        account.balance = 1000.0  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        account.account_id = "abcdefgh"  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        account.user = user  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        account.account_status = AccountStatus.Frozen  # pyright: ignore[reportAttributeAccessIssue]


def test_deposit_frozen_account_denied(frozen_account: AbstractAccount):
    with pytest.raises(AccountFrozenError):
        frozen_account.deposit(100.0)


def test_withdraw_frozen_account_denied(frozen_account: AbstractAccount):
    with pytest.raises(AccountFrozenError):
        frozen_account.withdraw(100.0)


def test_deposit_closed_account_denied(closed_account: AbstractAccount):
    with pytest.raises(AccountClosedError):
        closed_account.deposit(100.0)


def test_withdraw_closed_account_denied(closed_account: AbstractAccount):
    with pytest.raises(AccountClosedError):
        closed_account.withdraw(100.0)


def test_deposit(account: AbstractAccount):
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
def test_deposit_wrong_amount_type(account: AbstractAccount, value: object):
    with pytest.raises(InvalidOperationError):
        account.deposit(value)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("value", [1, 100.0])
def test_deposit_good_amount_type(account: AbstractAccount, value: float):
    initial_value = account.balance
    account.deposit(value)
    assert account.balance == initial_value + value


def test_withdraw_state(account: AbstractAccount):
    account.deposit(100.0)
    account.withdraw(50.0)
    assert account.balance == 50.0


def test_withdraw_below_balance(account: AbstractAccount):
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
def test_withdraw_wrong_value_type(account: AbstractAccount, value: object):
    account.deposit(1000000)
    with pytest.raises(InvalidOperationError):
        account.withdraw(value)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("value", [1, 100.0])
def test_withdraw_good_value_type(account: AbstractAccount, value: float):
    account.deposit(1000000)
    initial_value = account.balance
    account.withdraw(value)
    assert account.balance == initial_value - value


@pytest.mark.parametrize("amount", [10**400, -(10**400)])
def test_amount_unrepresentable_as_float(account: AbstractAccount, amount: float):
    with pytest.raises(InvalidOperationError):
        account.deposit(amount)
    assert account.balance == 0


def test_balance_unrepresentable_as_float(user: User):
    with pytest.raises(ValueError):
        AbstractAccount(user, balance=10**400)


def test_sum_of_valid_ints_overflows(user: User):
    account = AbstractAccount(user, balance=10**308)
    balance_before = account.balance
    with pytest.raises(InvalidOperationError):
        account.deposit(10**308)
    assert account.balance == balance_before


def test_float_sum_overflows(account: AbstractAccount):
    account.deposit(1e308)
    with pytest.raises(InvalidOperationError):
        account.deposit(1e308)
    assert account.balance == 1e308


def test_int_amount_against_float_balance(account: AbstractAccount):
    account.deposit(1e308)
    with pytest.raises(InvalidOperationError):
        account.deposit(10**308)
    assert account.balance == 1e308
