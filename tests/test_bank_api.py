from datetime import UTC, datetime

import pytest

from baseop.account import (
    AccountFrozenError,
    AccountStatus,
    InvalidOperationError,
)
from baseop.bank import (
    AccountKind,
    AccountNotFoundError,
    AuthenticationError,
    Bank,
    WorkingHoursError,
)
from baseop.client import Client, ClientStatus


class _DayDateTime:
    @classmethod
    def now(cls, _tz=None):
        return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def bank(monkeypatch) -> Bank:
    monkeypatch.setattr("baseop.bank.datetime", _DayDateTime)
    return Bank()


@pytest.fixture
def client(bank: Bank) -> Client:
    client = bank.add_client(
        first_name="Alice",
        last_name="Smith",
        age=30,
        secret="secret",
    )
    bank.authenticate_client(client.id, "secret")
    return client


def test_account_lifecycle(bank: Bank, client: Client):
    info = bank.open_account(client.id, AccountKind.BANK)
    account_id = info["account_id"]

    assert info["balance"] == 0
    assert info["account_status"] is AccountStatus.ACTIVE

    assert bank.deposit(client.id, account_id, 100)["balance"] == 100
    assert bank.withdraw(client.id, account_id, 40)["balance"] == 60
    assert bank.get_total_balance() == 60
    assert bank.get_clients_ranking()[client.id] == 60

    bank.freeze_account(client.id, account_id)
    with pytest.raises(AccountFrozenError):
        bank.deposit(client.id, account_id, 1)
    bank.unfreeze_account(client.id, account_id)

    with pytest.raises(InvalidOperationError):
        bank.close_account(client.id, account_id)

    bank.withdraw(client.id, account_id, 60)
    bank.close_account(client.id, account_id)

    closed = bank.search_accounts(client.id, status=AccountStatus.CLOSED)
    assert closed[0]["account_status"] is AccountStatus.CLOSED
    assert bank.get_total_balance() == 0


def test_three_failed_logins_block_client(bank: Bank):
    client = bank.add_client(
        first_name="Bob",
        last_name="Jones",
        age=25,
        secret="secret",
    )

    for _ in range(3):
        with pytest.raises(AuthenticationError):
            bank.authenticate_client(client.id, "wrong")

    assert client.status is ClientStatus.BLOCKED
    with pytest.raises(AuthenticationError):
        bank.authenticate_client(client.id, "secret")


def test_account_operations_are_scoped_to_owner(bank: Bank):
    alice = bank.add_client(
        first_name="Alice",
        last_name="Smith",
        age=30,
        secret="alice",
    )
    bank.authenticate_client(alice.id, "alice")

    bob = bank.add_client(
        first_name="Bob",
        last_name="Jones",
        age=25,
        secret="bob",
    )
    bank.authenticate_client(bob.id, "bob")

    account = bank.open_account(alice.id, AccountKind.BANK)

    with pytest.raises(AccountNotFoundError):
        bank.deposit(bob.id, account["account_id"], 50)


def test_night_operations_are_blocked(
    bank: Bank, client: Client, monkeypatch
):
    account = bank.open_account(client.id, AccountKind.BANK)

    class _NightDateTime:
        @classmethod
        def now(cls, _tz=None):
            return datetime(2026, 1, 1, 2, 0, tzinfo=UTC)

    monkeypatch.setattr("baseop.bank.datetime", _NightDateTime)

    with pytest.raises(WorkingHoursError):
        bank.deposit(client.id, account["account_id"], 10)
