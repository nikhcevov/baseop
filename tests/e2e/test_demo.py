"""Deterministic end-to-end demo of the baseop bank.

Run with output: ``pytest -s tests/e2e/test_demo.py``.

Seven clients and twelve accounts are created through the public ``Bank``
facade, then 42 operation attempts are executed one by one. No mocks and
no wall clock: time comes from an injected ``FrozenClock``, so balances,
audit counts and reports are identical on every run.
"""

from collections import Counter
from datetime import datetime

import pytest

from baseop.account import (
    AccountClosedError,
    AccountFrozenError,
    AccountStatus,
    InsufficientFundsError,
)
from baseop.audit import AuditLogSeverity
from baseop.bank import (
    AccountKind,
    Bank,
    BankEventKind,
    ClientInactiveError,
    SuspiciousOperationError,
    WorkingHoursError,
)
from baseop.client import ClientStatus
from baseop.clock import FrozenClock
from baseop.transaction import Transaction, TransactionStatus

SECRET = "demo-secret"


def _settle(bank: Bank, tx: Transaction) -> None:
    """Runs a queued transaction immediately and asserts it completed."""
    assert tx.status is TransactionStatus.QUEUED
    assert bank.run_transactions() == [tx]
    assert tx.status is TransactionStatus.COMPLETED


def test_demo_scenario(
    bank: Bank, clock: FrozenClock, day: datetime, night: datetime
) -> None:
    # --- initialization: 7 clients -------------------------------------
    alice = bank.add_client(
        first_name="Alice", last_name="Smith", age=30, secret=SECRET
    )
    bob = bank.add_client(first_name="Bob", last_name="Jones", age=41, secret=SECRET)
    carol = bank.add_client(
        first_name="Carol", last_name="White", age=28, secret=SECRET
    )
    dave = bank.add_client(first_name="Dave", last_name="Brown", age=52, secret=SECRET)
    eve = bank.add_client(first_name="Eve", last_name="Davis", age=35, secret=SECRET)
    frank = bank.add_client(
        first_name="Frank", last_name="Miller", age=24, secret=SECRET
    )
    grace = bank.add_client(
        first_name="Grace", last_name="Wilson", age=47, secret=SECRET
    )

    bank.authenticate_client(alice.id, SECRET)
    bank.authenticate_client(bob.id, SECRET)
    bank.authenticate_client(carol.id, SECRET)
    bank.authenticate_client(dave.id, SECRET)
    bank.authenticate_client(eve.id, SECRET)
    bank.authenticate_client(frank.id, SECRET)
    bank.authenticate_client(grace.id, SECRET)

    # --- initialization: 12 accounts -----------------------------------
    alice_bank = bank.open_account(alice.id, AccountKind.BANK)["account_id"]
    alice_savings = bank.open_account(alice.id, AccountKind.SAVING)["account_id"]
    alice_premium = bank.open_account(alice.id, AccountKind.PREMIUM)["account_id"]
    bob_bank = bank.open_account(bob.id, AccountKind.BANK)["account_id"]
    bob_savings = bank.open_account(bob.id, AccountKind.SAVING)["account_id"]
    carol_bank = bank.open_account(carol.id, AccountKind.BANK)["account_id"]
    dave_bank = bank.open_account(dave.id, AccountKind.BANK)["account_id"]
    dave_investment = bank.open_account(dave.id, AccountKind.INVESTMENT)["account_id"]
    eve_bank = bank.open_account(eve.id, AccountKind.BANK)["account_id"]
    frank_bank = bank.open_account(frank.id, AccountKind.BANK)["account_id"]
    grace_bank = bank.open_account(grace.id, AccountKind.BANK)["account_id"]
    grace_premium = bank.open_account(grace.id, AccountKind.PREMIUM)["account_id"]

    clients = {
        "Alice": alice,
        "Bob": bob,
        "Carol": carol,
        "Dave": dave,
        "Eve": eve,
        "Frank": frank,
        "Grace": grace,
    }
    accounts = {
        "alice:bank": alice_bank,
        "alice:savings": alice_savings,
        "alice:premium": alice_premium,
        "bob:bank": bob_bank,
        "bob:savings": bob_savings,
        "carol:bank": carol_bank,
        "dave:bank": dave_bank,
        "dave:investment": dave_investment,
        "eve:bank": eve_bank,
        "frank:bank": frank_bank,
        "grace:bank": grace_bank,
        "grace:premium": grace_premium,
    }

    # --- funding deposits ----------------------------------------------
    bank.deposit(alice.id, alice_bank, 5_000)
    bank.deposit(alice.id, alice_savings, 3_000)
    bank.deposit(bob.id, bob_bank, 4_000)
    bank.deposit(carol.id, carol_bank, 2_500)
    bank.deposit(dave.id, dave_bank, 6_000)
    bank.deposit(eve.id, eve_bank, 1_500)
    bank.deposit(frank.id, frank_bank, 800)
    bank.deposit(grace.id, grace_bank, 10_000)

    # --- internal transfers --------------------------------------------
    first_transfer = bank.submit_transfer(
        alice.id, alice_bank, 500, to_account_id=bob_bank
    )
    _settle(bank, first_transfer)
    _settle(
        bank,
        bank.submit_transfer(bob.id, bob_bank, 300, to_account_id=carol_bank),
    )
    _settle(
        bank,
        bank.submit_transfer(dave.id, dave_bank, 1_000, to_account_id=alice_premium),
    )
    _settle(
        bank,
        bank.submit_transfer(grace.id, grace_bank, 700, to_account_id=alice_savings),
    )
    _settle(
        bank,
        bank.submit_transfer(eve.id, eve_bank, 200, to_account_id=frank_bank),
    )
    _settle(
        bank,
        bank.submit_transfer(carol.id, carol_bank, 400, to_account_id=dave_bank),
    )

    # --- external transfers (3% fee) -----------------------------------
    _settle(
        bank,
        bank.submit_transfer(
            alice.id, alice_bank, 100, external_destination="iban-DE89"
        ),
    )
    _settle(
        bank,
        bank.submit_transfer(bob.id, bob_bank, 200, external_destination="iban-FR14"),
    )
    _settle(
        bank,
        bank.submit_transfer(
            grace.id, grace_bank, 500, external_destination="iban-NL02"
        ),
    )

    # --- withdrawals ----------------------------------------------------
    bank.withdraw(dave.id, dave_bank, 500)
    bank.withdraw(carol.id, carol_bank, 100)
    bank.withdraw(eve.id, eve_bank, 100)

    # --- erroneous operations -------------------------------------------
    with pytest.raises(InsufficientFundsError):
        bank.withdraw(frank.id, frank_bank, 100_000)

    bank.freeze_account(eve.id, eve_bank)
    with pytest.raises(AccountFrozenError):
        bank.deposit(eve.id, eve_bank, 50)
    bank.unfreeze_account(eve.id, eve_bank)
    bank.deposit(eve.id, eve_bank, 50)

    doomed = bank.submit_transfer(
        frank.id, frank_bank, 100_000, to_account_id=alice_bank
    )
    assert bank.run_transactions() == [doomed]
    assert doomed.status is TransactionStatus.FAILED

    cancelled = bank.submit_transfer(bob.id, bob_bank, 100, to_account_id=alice_bank)
    assert bank.cancel_transaction(bob.id, cancelled.id) is True
    assert cancelled.status is TransactionStatus.CANCELLED
    assert bank.run_transactions() == []

    # --- suspicious operations: high amounts block the client -----------
    with pytest.raises(SuspiciousOperationError):
        bank.submit_transfer(dave.id, dave_bank, 1_000_000, to_account_id=grace_bank)
    with pytest.raises(SuspiciousOperationError):
        bank.submit_transfer(dave.id, dave_bank, 1_000_000, to_account_id=grace_bank)
    with pytest.raises(SuspiciousOperationError):
        bank.submit_transfer(dave.id, dave_bank, 1_000_000, to_account_id=grace_bank)

    assert dave.status is ClientStatus.BLOCKED
    with pytest.raises(ClientInactiveError):
        bank.deposit(dave.id, dave_bank, 100)

    # --- night operations are audited and refused -----------------------
    clock.set(night)
    with pytest.raises(WorkingHoursError):
        bank.deposit(alice.id, alice_bank, 1_000_000)
    with pytest.raises(WorkingHoursError):
        bank.deposit(bob.id, bob_bank, 10)
    clock.set(day)

    # --- burst of small operations triggers the frequency check ---------
    bank.deposit(grace.id, grace_bank, 10)
    bank.deposit(grace.id, grace_bank, 10)
    bank.deposit(grace.id, grace_bank, 10)
    bank.deposit(grace.id, grace_bank, 10)
    bank.deposit(grace.id, grace_bank, 10)
    bank.deposit(grace.id, grace_bank, 10)
    bank.deposit(grace.id, grace_bank, 10)

    # --- premium accounts, closing, post-close failure ------------------
    bank.deposit(alice.id, alice_premium, 250)
    _settle(
        bank,
        bank.submit_transfer(alice.id, alice_premium, 250, to_account_id=grace_premium),
    )
    bank.withdraw(grace.id, grace_premium, 50)

    bank.close_account(bob.id, bob_savings)
    with pytest.raises(AccountClosedError):
        bank.deposit(bob.id, bob_savings, 10)

    # --- verification ---------------------------------------------------
    logs = bank._audit_log.search_logs()
    counts = Counter(entry.severity for entry in logs)
    severity = {level: counts[level] for level in AuditLogSeverity}
    completed_count = severity[AuditLogSeverity.NONE]
    failed_count = sum(bank.get_error_stats().values())

    stats = bank.get_transaction_stats()
    event_counts = {kind: len(bank.get_events(kind=kind)) for kind in BankEventKind}
    attempted = stats["total"]

    assert len(clients) == 7
    assert len(accounts) == 12
    assert 30 <= attempted <= 50
    assert attempted == 42
    assert completed_count == 31
    assert failed_count == 4

    assert stats == {
        "queued": 0,
        "completed": 31,
        "failed": 4,
        "cancelled": 1,
        "rejected": 6,
        "total": 42,
    }
    assert {kind.value: count for kind, count in event_counts.items()} == {
        "queued": 12,
        "completed": 31,
        "failed": 4,
        "cancelled": 1,
        "rejected": 6,
    }
    assert [event.kind for event in bank.get_events(tx_id=first_transfer.id)] == [
        BankEventKind.QUEUED,
        BankEventKind.COMPLETED,
    ]

    assert bank.get_total_balance() == 31_396.0
    assert bank.get_error_stats() == {
        "Withdrawal amount is larger than balance.": 2,
        "Account is frozen, operation denied.": 1,
        "Account is closed, operation denied.": 1,
    }
    assert severity == {
        AuditLogSeverity.NONE: 31,
        AuditLogSeverity.LOW: 0,
        AuditLogSeverity.MEDIUM: 15,
        AuditLogSeverity.HIGH: 4,
    }

    names = {client.id: name for name, client in clients.items()}
    ranking = {
        names[client_id]: total
        for client_id, total in bank.get_clients_ranking().items()
    }
    assert list(ranking) == ["Alice", "Grace", "Dave", "Bob", "Carol", "Eve", "Frank"]
    assert ranking == {
        "Alice": 8_997.0,
        "Grace": 8_955.0,
        "Dave": 4_900.0,
        "Bob": 3_994.0,
        "Carol": 2_300.0,
        "Eve": 1_250.0,
        "Frank": 1_000.0,
    }

    risk = {
        name: (
            bank.get_client_risk_profile(client.id)["risk_profile"],
            bank.get_client_risk_profile(client.id)["suspicious"],
        )
        for name, client in clients.items()
    }
    assert risk == {
        "Alice": ("HIGH", True),
        "Bob": ("MEDIUM", True),
        "Carol": ("MEDIUM", True),
        "Dave": ("HIGH", True),
        "Eve": ("MEDIUM", True),
        "Frank": ("MEDIUM", True),
        "Grace": ("MEDIUM", True),
    }

    bob_accounts = {info["account_id"]: info for info in bank.search_accounts(bob.id)}
    assert bob_accounts[bob_savings]["account_status"] is AccountStatus.CLOSED

    # --- user scenarios --------------------------------------------------
    alice_accounts = bank.get_client_accounts(alice.id)
    alice_transactions = bank.get_client_transactions(alice.id)
    alice_history = bank.get_client_history(alice.id)
    alice_suspicious = bank.get_suspicious_operations(client_id=alice.id)

    assert len(alice_accounts) == 3
    assert len(alice_transactions) == 10
    assert len(alice_history) == 12
    assert len(alice_suspicious) == 4

    rejections = [
        (names[event.client_id] if event.client_id else None, event.reason)
        for event in bank.get_events(kind=BankEventKind.REJECTED)
    ]
    assert rejections == [
        ("Dave", "risk analyzer"),
        ("Dave", "risk analyzer"),
        ("Dave", "risk analyzer"),
        ("Dave", "client inactive"),
        ("Alice", "closed hours"),
        ("Bob", "closed hours"),
    ]

    # --- reports ---------------------------------------------------------
    top3 = list(ranking.items())[:3]
    assert top3 == [("Alice", 8_997.0), ("Grace", 8_955.0), ("Dave", 4_900.0)]

    # --- deterministic report -------------------------------------------
    account_labels = {account_id: label for label, account_id in accounts.items()}
    print()
    print("=== baseop demo ===")
    print(f"clients: {len(clients)}, accounts: {len(accounts)}")
    print(f"operations attempted: {attempted}")
    print()
    print("[logging]")
    print(
        "  events: "
        + ", ".join(f"{kind.value}={event_counts[kind]}" for kind in BankEventKind)
    )
    lifecycle = [
        event.kind.value for event in bank.get_events(tx_id=first_transfer.id)
    ]
    print(f"  first transfer lifecycle: {lifecycle}")
    print("  rejections:")
    for client_name, reason in rejections:
        print(f"    {client_name}: {reason}")
    print()
    print("[client scenario: Alice]")
    print("  accounts:")
    for info in alice_accounts:
        label = account_labels[info["account_id"]]
        print(
            f"    {label:<14} {info['balance']:>8.2f} "
            f"{info['account_status'].value}"
        )
    print(f"  transactions: {len(alice_transactions)}")
    print(f"  history entries: {len(alice_history)}")
    for entry in alice_history[-3:]:
        print(f"    {entry.severity.name:<6} {'/'.join(entry.tags)}")
    print(f"  suspicious entries: {len(alice_suspicious)}")
    print()
    print("[reports]")
    print("  top-3 clients:")
    for name, total in top3:
        print(f"    {name:<6} {total:>9.2f}")
    print(f"  transaction stats: {stats}")
    print(f"  total balance: {bank.get_total_balance():.2f}")
    print("  risk profiles:")
    for name, (profile, suspicious) in risk.items():
        print(f"    {name:<6} risk={profile:<6} suspicious={suspicious}")
    print("  error stats:")
    for reason, count in bank.get_error_stats().items():
        print(f"    {count}x {reason}")
    print("  audit log:")
    print(
        "    severity: "
        + ", ".join(
            f"{level.name}={severity[level]}" for level in AuditLogSeverity
        )
    )
    tags = Counter(tag for entry in logs for tag in entry.tags)
    print(f"    tags: {dict(sorted(tags.items()))}")
