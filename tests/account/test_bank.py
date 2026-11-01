from uuid import uuid4

import pytest

from baseop.account import AccountCurrency, BankAccount
from baseop.client import Client


@pytest.fixture
def user():
    return Client(id=uuid4(), first_name="John", last_name="Doe", age=30)


@pytest.fixture
def account(user: Client):
    return BankAccount(user)


def test_bank_account_has_immutable_attributes(account: BankAccount, user: Client):
    with pytest.raises(AttributeError):
        account.currency = AccountCurrency.CNY  # pyright: ignore[reportAttributeAccessIssue]
