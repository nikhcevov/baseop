from uuid import UUID, uuid4

import pytest

from baseop.account import (
    AbstractAccount,
    AccountClosedError,
    AccountFrozenError,
    AccountStatus,
    BankAccount,
    InsufficientFundsError,
    InvalidOperationError,
    User,
)


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


def test_bank_account_init_with_uuid(account: AbstractAccount):
    assert isinstance(account.account_id, UUID)


def test_bank_account_init_with_no_balance(account: AbstractAccount):
    assert account.balance == 0


def test_bank_account_init_with_user(user: User):
    account = BankAccount(user)
    assert account.user == user


def test_bank_account_init_with_active_account(account: AbstractAccount):
    assert account.account_status == AccountStatus.Active


def test_bank_account_creates_with_frozen_account(user: User):
    account = BankAccount(user, account_status=AccountStatus.Frozen)
    assert account.account_status == AccountStatus.Frozen


def test_bank_account_creates_with_closed_account(user: User):
    account = BankAccount(user, account_status=AccountStatus.Closed)
    assert account.account_status == AccountStatus.Closed


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


def test_deposit_negative_value(account: AbstractAccount):
    with pytest.raises(InvalidOperationError):
        account.deposit(-100.0)


def test_deposit_invalid_value_type(account: AbstractAccount):
    with pytest.raises(InvalidOperationError):
        account.deposit(100)


def test_withdraw(account: AbstractAccount):
    account.deposit(100.0)
    account.withdraw(50.0)
    assert account.balance == 50.0


def test_withdraw_below_balance(account: AbstractAccount):
    account.deposit(100.0)
    with pytest.raises(InsufficientFundsError):
        account.withdraw(200.0)


def test_withdraw_negative_value(account: AbstractAccount):
    account.deposit(100.0)
    with pytest.raises(InvalidOperationError):
        account.withdraw(-100.0)


def test_withdraw_invalid_value_type(account: AbstractAccount):
    account.deposit(100.0)
    with pytest.raises(InvalidOperationError):
        account.withdraw(100)
