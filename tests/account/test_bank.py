from uuid import uuid4

import pytest

from baseop.account import AccountCurrency, BankAccount
from baseop.user import User


@pytest.fixture
def user():
    return User(id=uuid4(), name="John Doe")


@pytest.fixture
def account(user: User):
    return BankAccount(user)


def test_bank_account_has_immutable_attributes(account: BankAccount, user: User):
    with pytest.raises(AttributeError):
        account.currency = AccountCurrency.CNY  # pyright: ignore[reportAttributeAccessIssue]
