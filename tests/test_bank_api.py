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
from baseop.transaction import TransactionStatus


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


def test_failed_login_marks_client_suspicious(bank: Bank):
    client = bank.add_client(
        first_name="Bob",
        last_name="Jones",
        age=25,
        secret="secret",
    )

    with pytest.raises(AuthenticationError):
        bank.authenticate_client(client.id, "wrong")

    assert client.suspicious is True

    bank.authenticate_client(client.id, "secret")
    assert client.suspicious is True


def _balances(bank: Bank, client: Client) -> dict[str, float]:
    return {
        info["account_id"]: info["balance"]
        for info in bank.search_accounts(client.id)
    }


def test_submit_and_process_internal_transfer(bank: Bank, client: Client):
    sender = bank.open_account(client.id, AccountKind.BANK)["account_id"]
    recipient = bank.open_account(client.id, AccountKind.BANK)["account_id"]
    bank.deposit(client.id, sender, 1000.0)

    tx = bank.submit_transfer(client.id, sender, 100.0, to_account_id=recipient)

    assert tx.status is TransactionStatus.QUEUED
    assert bank.run_transactions() == [tx]
    assert tx.status is TransactionStatus.COMPLETED
    assert _balances(bank, client) == {sender: 900.0, recipient: 100.0}


def test_submit_external_transfer_charges_fee(bank: Bank, client: Client):
    account_id = bank.open_account(client.id, AccountKind.BANK)["account_id"]
    bank.deposit(client.id, account_id, 1000.0)

    tx = bank.submit_transfer(
        client.id,
        account_id,
        100.0,
        external_destination="EXTERNAL-ACCOUNT",
    )
    bank.run_transactions()

    assert tx.status is TransactionStatus.COMPLETED
    assert tx.fee == 3.0
    assert _balances(bank, client)[account_id] == 897.0


def test_cancel_queued_transfer(bank: Bank, client: Client):
    sender = bank.open_account(client.id, AccountKind.BANK)["account_id"]
    recipient = bank.open_account(client.id, AccountKind.BANK)["account_id"]
    bank.deposit(client.id, sender, 1000.0)

    tx = bank.submit_transfer(client.id, sender, 100.0, to_account_id=recipient)

    assert bank.cancel_transaction(client.id, tx.id) is True
    assert tx.status is TransactionStatus.CANCELLED
    assert bank.run_transactions() == []
    assert _balances(bank, client) == {sender: 1000.0, recipient: 0.0}


def test_transfer_requires_ownership(bank: Bank, client: Client):
    account_id = bank.open_account(client.id, AccountKind.BANK)["account_id"]
    bank.deposit(client.id, account_id, 100.0)

    other = bank.add_client(
        first_name="Bob",
        last_name="Jones",
        age=25,
        secret="other",
    )
    bank.authenticate_client(other.id, "other")

    with pytest.raises(AccountNotFoundError):
        bank.submit_transfer(
            other.id,
            account_id,
            10.0,
            external_destination="EXTERNAL-ACCOUNT",
        )

    with pytest.raises(AccountNotFoundError):
        bank.submit_transfer(
            client.id,
            account_id,
            10.0,
            to_account_id="zzzzzzzz",
        )
