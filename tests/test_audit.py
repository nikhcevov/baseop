import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from baseop.account import InsufficientFundsError
from baseop.audit import AuditLog, AuditLogSeverity, LogEntry, RiscAnalyzer
from baseop.bank import (
    AccountKind,
    Bank,
    ClientInactiveError,
    SuspiciousOperationError,
    WorkingHoursError,
)
from baseop.client import Client, ClientStatus
from baseop.transaction import Transaction, TransactionStatus, TransactionType


class _DayDateTime:
    @classmethod
    def now(cls, _tz=None):
        return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class _NightDateTime:
    @classmethod
    def now(cls, _tz=None):
        return datetime(2026, 1, 1, 3, 0, tzinfo=UTC)


class _MorningDateTime:
    @classmethod
    def now(cls, _tz=None):
        return datetime(2026, 1, 1, 6, 0, tzinfo=UTC)


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


def _open_account(bank: Bank, client: Client) -> str:
    return bank.open_account(client.id, AccountKind.BANK)["account_id"]


def test_high_amount_deposit_is_blocked_and_logged(bank: Bank, client: Client) -> None:
    account_id = _open_account(bank, client)

    with pytest.raises(SuspiciousOperationError) as error:
        bank.deposit(client.id, account_id, 1_000_000)

    assert bank.search_accounts(client.id)[0]["balance"] == 0
    assert client.suspicious is True
    assert client.risk_profile == "HIGH"

    high_entries = bank._audit_log.search_logs(severity=AuditLogSeverity.HIGH)
    assert len(high_entries) == 1
    assert "transaction_amount" in high_entries[0].tags
    assert client.id in high_entries[0].client_ids
    assert high_entries[0].tx_id in {entry.tx_id for entry in error.value.entries}


def test_normal_operation_is_logged_without_risk_findings(
    bank: Bank, client: Client
) -> None:
    account_id = _open_account(bank, client)

    tx = bank.deposit(client.id, account_id, 100)

    assert bank.search_accounts(client.id)[0]["balance"] == 100

    entries = bank._audit_log.search_logs()
    assert len(entries) == 1
    assert entries[0].tx_id == tx.id
    assert entries[0].severity is AuditLogSeverity.NONE
    assert entries[0].tags == ["transaction"]
    assert entries[0].client_ids == [client.id]
    assert bank._audit_log.search_logs(severity=AuditLogSeverity.HIGH) == []


def test_frequent_operations_are_flagged(bank: Bank, client: Client) -> None:
    account_id = _open_account(bank, client)
    for _ in range(9):
        bank.deposit(client.id, account_id, 100)

    assert bank._audit_log.search_logs(severity=AuditLogSeverity.MEDIUM) == []

    bank.deposit(client.id, account_id, 100)

    findings = bank._audit_log.search_logs(severity=AuditLogSeverity.MEDIUM)
    assert len(findings) == 1
    assert findings[0].tags == ["operation_count"]
    assert findings[0].client_ids == [client.id]
    assert client.suspicious is True
    assert client.risk_profile == "MEDIUM"


def test_frequent_operations_do_not_leak_between_clients(
    bank: Bank, client: Client
) -> None:
    account_id = _open_account(bank, client)
    for _ in range(9):
        bank.deposit(client.id, account_id, 100)

    other = bank.add_client(
        first_name="Bob",
        last_name="Jones",
        age=25,
        secret="other",
    )
    bank.authenticate_client(other.id, "other")
    other_account = _open_account(bank, other)

    bank.deposit(other.id, other_account, 100)

    assert bank._audit_log.search_logs(severity=AuditLogSeverity.MEDIUM) == []
    assert other.suspicious is False
    assert other.risk_profile is None


def test_amount_findings_do_not_count_as_operations() -> None:
    client_id = uuid4()
    audit_log = AuditLog()
    for _ in range(20):
        audit_log.add(
            LogEntry(
                tx_id=uuid4(),
                client_ids=[client_id],
                severity=AuditLogSeverity.MEDIUM,
                message="Transaction amount in danger zone",
                tags=["transaction_amount"],
            )
        )
    tx = Transaction(
        type=TransactionType.DEPOSIT,
        amount=10,
        currency="RUB",
        to_client_id=client_id,
        to_account_id="abcdefgh",
    )

    entries = RiscAnalyzer().audit_operation(tx, audit_log)

    assert entries is None


def _add_client(bank: Bank, first_name: str, secret: str) -> Client:
    client = bank.add_client(
        first_name=first_name,
        last_name="Jones",
        age=25,
        secret=secret,
    )
    bank.authenticate_client(client.id, secret)
    return client


def test_transfer_to_new_account_is_flagged_once(bank: Bank, client: Client) -> None:
    sender = _open_account(bank, client)
    other = _add_client(bank, "Bob", "other")
    recipient = _open_account(bank, other)

    bank.submit_transfer(client.id, sender, 10, to_account_id=recipient)

    findings = [
        entry
        for entry in bank._audit_log.search_logs(severity=AuditLogSeverity.MEDIUM)
        if "new_account" in entry.tags
    ]
    assert len(findings) == 1
    assert findings[0].client_ids == [client.id]
    assert client.suspicious is True
    assert client.risk_profile == "MEDIUM"

    bank.submit_transfer(client.id, sender, 10, to_account_id=recipient)

    findings = [
        entry
        for entry in bank._audit_log.search_logs(severity=AuditLogSeverity.MEDIUM)
        if "new_account" in entry.tags
    ]
    assert len(findings) == 1


def test_transfer_between_own_accounts_is_not_flagged(
    bank: Bank, client: Client
) -> None:
    first = _open_account(bank, client)
    second = _open_account(bank, client)

    bank.submit_transfer(client.id, first, 10, to_account_id=second)

    assert bank._audit_log.search_logs(severity=AuditLogSeverity.MEDIUM) == []


def test_external_transfer_is_not_flagged_as_new_account(
    bank: Bank, client: Client
) -> None:
    sender = _open_account(bank, client)

    bank.submit_transfer(client.id, sender, 10, external_destination="EXTERNAL-ACC")

    assert bank._audit_log.search_logs(severity=AuditLogSeverity.MEDIUM) == []


def test_operation_is_audited_only_once(bank: Bank, client: Client) -> None:
    account_id = _open_account(bank, client)
    tx = bank.deposit(client.id, account_id, 100)

    before = bank._audit_log.search_logs()
    assert len(before) == 1

    bank._audit(tx)

    assert bank._audit_log.search_logs() == before


def test_repeated_audit_does_not_inflate_frequency(bank: Bank, client: Client) -> None:
    account_id = _open_account(bank, client)
    tx = bank.deposit(client.id, account_id, 100)

    for _ in range(20):
        bank._audit(tx)

    bank.deposit(client.id, account_id, 100)

    assert bank._audit_log.search_logs(severity=AuditLogSeverity.MEDIUM) == []


def _entry(severity: AuditLogSeverity, tag: str) -> LogEntry:
    return LogEntry(
        tx_id=uuid4(),
        client_ids=[uuid4()],
        severity=severity,
        message="test entry",
        tags=[tag],
    )


def _read_export(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_export_writes_json_objects(tmp_path: Path) -> None:
    audit_log = AuditLog()
    first = _entry(AuditLogSeverity.MEDIUM, "transaction_amount")
    second = _entry(AuditLogSeverity.HIGH, "new_account")
    audit_log.add(first)
    audit_log.add(second)
    path = tmp_path / "logs.json"

    audit_log.export_to_file(path=str(path))

    data = _read_export(path)
    assert all(isinstance(item, dict) for item in data)
    assert [item["tx_id"] for item in data] == [str(first.tx_id), str(second.tx_id)]
    assert data[0]["severity"] == AuditLogSeverity.MEDIUM.value
    assert data[0]["tags"] == ["transaction_amount"]
    assert data[0]["client_ids"] == [str(first.client_ids[0])]
    assert isinstance(data[0]["created_at"], str)


def test_export_honours_explicit_selection(tmp_path: Path) -> None:
    audit_log = AuditLog()
    first = _entry(AuditLogSeverity.MEDIUM, "transaction_amount")
    second = _entry(AuditLogSeverity.HIGH, "new_account")
    audit_log.add(first)
    audit_log.add(second)
    path = tmp_path / "selected.json"

    audit_log.export_to_file([second], path=str(path))

    data = _read_export(path)
    assert [item["tx_id"] for item in data] == [str(second.tx_id)]


def test_export_of_empty_selection_writes_empty_list(tmp_path: Path) -> None:
    audit_log = AuditLog()
    audit_log.add(_entry(AuditLogSeverity.HIGH, "new_account"))
    path = tmp_path / "empty.json"

    audit_log.export_to_file([], path=str(path))

    assert _read_export(path) == []


def test_suspicious_operations_exclude_routine_entries() -> None:
    audit_log = AuditLog()
    audit_log.add(_entry(AuditLogSeverity.NONE, "transaction"))
    audit_log.add(_entry(AuditLogSeverity.LOW, "operation_time"))
    audit_log.add(_entry(AuditLogSeverity.MEDIUM, "new_account"))
    audit_log.add(_entry(AuditLogSeverity.HIGH, "transaction_amount"))

    suspicious = audit_log.get_suspicious_operations()

    assert {entry.severity for entry in suspicious} == {
        AuditLogSeverity.MEDIUM,
        AuditLogSeverity.HIGH,
    }
    assert {entry.tags[0] for entry in suspicious} == {
        "new_account",
        "transaction_amount",
    }


def test_client_risk_profile_reports_findings(bank: Bank, client: Client) -> None:
    account_id = _open_account(bank, client)

    assert bank.get_client_risk_profile(client.id) == {
        "risk_profile": None,
        "suspicious": False,
        "findings": {},
    }

    bank.deposit(client.id, account_id, 400_000)

    assert bank.get_client_risk_profile(client.id) == {
        "risk_profile": "MEDIUM",
        "suspicious": True,
        "findings": {AuditLogSeverity.MEDIUM: 1},
    }

    with pytest.raises(SuspiciousOperationError):
        bank.deposit(client.id, account_id, 1_000_000)

    profile = bank.get_client_risk_profile(client.id)
    assert profile["risk_profile"] == "HIGH"
    assert profile["findings"] == {
        AuditLogSeverity.MEDIUM: 1,
        AuditLogSeverity.HIGH: 1,
    }


def test_error_stats_count_failed_operations(bank: Bank, client: Client) -> None:
    account_id = _open_account(bank, client)
    bank.deposit(client.id, account_id, 100)

    assert bank.get_error_stats() == {}

    with pytest.raises(InsufficientFundsError):
        bank.withdraw(client.id, account_id, 1000)
    with pytest.raises(InsufficientFundsError):
        bank.withdraw(client.id, account_id, 1000)

    assert bank.get_error_stats() == {"Withdrawal amount is larger than balance.": 2}


def test_error_stats_count_failed_queued_transfer(bank: Bank, client: Client) -> None:
    sender = _open_account(bank, client)
    recipient = _open_account(bank, client)

    tx = bank.submit_transfer(client.id, sender, 100, to_account_id=recipient)
    assert tx.status is TransactionStatus.QUEUED

    processed = bank.run_transactions()

    assert [item.status for item in processed] == [TransactionStatus.FAILED]
    assert bank.get_error_stats() == {"Withdrawal amount is larger than balance.": 1}


def test_night_attempt_is_recorded_and_refused(
    bank: Bank, client: Client, monkeypatch
) -> None:
    account_id = _open_account(bank, client)
    monkeypatch.setattr("baseop.bank.datetime", _NightDateTime)
    monkeypatch.setattr("baseop.transaction.datetime", _NightDateTime)

    with pytest.raises(WorkingHoursError):
        bank.deposit(client.id, account_id, 100)

    assert bank.search_accounts(client.id)[0]["balance"] == 0
    assert [
        (entry.severity, entry.tags) for entry in bank._audit_log.search_logs()
    ] == [(AuditLogSeverity.MEDIUM, ["operation_time"])]
    assert client.suspicious is True
    assert bank._audit_log.search_logs(tags=["transaction"]) == []


def test_morning_operation_is_not_flagged(
    bank: Bank, client: Client, monkeypatch
) -> None:
    account_id = _open_account(bank, client)
    monkeypatch.setattr("baseop.bank.datetime", _MorningDateTime)
    monkeypatch.setattr("baseop.transaction.datetime", _MorningDateTime)

    bank.deposit(client.id, account_id, 100)

    assert [
        (entry.severity, entry.tags) for entry in bank._audit_log.search_logs()
    ] == [(AuditLogSeverity.NONE, ["transaction"])]
    assert client.suspicious is False


def test_night_high_amount_is_refused_by_hours(
    bank: Bank, client: Client, monkeypatch
) -> None:
    account_id = _open_account(bank, client)
    monkeypatch.setattr("baseop.bank.datetime", _NightDateTime)
    monkeypatch.setattr("baseop.transaction.datetime", _NightDateTime)

    with pytest.raises(WorkingHoursError):
        bank.deposit(client.id, account_id, 1_000_000)

    assert bank.search_accounts(client.id)[0]["balance"] == 0


def test_high_risk_transfer_does_not_mark_recipient(bank: Bank, client: Client) -> None:
    sender = _open_account(bank, client)
    other = _add_client(bank, "Bob", "other")
    recipient = _open_account(bank, other)

    for _ in range(3):
        with pytest.raises(SuspiciousOperationError):
            bank.submit_transfer(client.id, sender, 1_000_000, to_account_id=recipient)

    assert client.status is ClientStatus.BLOCKED
    assert other.status is ClientStatus.ACTIVE
    assert other.suspicious is False
    assert other.risk_profile is None

    high_entries = bank._audit_log.search_logs(severity=AuditLogSeverity.HIGH)
    assert len(high_entries) == 3
    assert all(entry.client_ids == [client.id] for entry in high_entries)


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (349_999.0, None),
        (350_000.0, AuditLogSeverity.MEDIUM),
        (999_999.0, AuditLogSeverity.MEDIUM),
    ],
)
def test_amount_thresholds(
    bank: Bank,
    client: Client,
    amount: float,
    expected: AuditLogSeverity | None,
) -> None:
    account_id = _open_account(bank, client)

    bank.deposit(client.id, account_id, amount)

    findings = [
        entry
        for entry in bank._audit_log.search_logs()
        if "transaction_amount" in entry.tags
    ]
    assert [entry.severity for entry in findings] == (
        [] if expected is None else [expected]
    )


def test_third_high_risk_operation_blocks_client(bank: Bank, client: Client) -> None:
    account_id = _open_account(bank, client)

    for _ in range(2):
        with pytest.raises(SuspiciousOperationError):
            bank.deposit(client.id, account_id, 1_000_000)
    assert client.status is ClientStatus.ACTIVE

    with pytest.raises(SuspiciousOperationError):
        bank.deposit(client.id, account_id, 1_000_000)

    assert client.status is ClientStatus.BLOCKED
    with pytest.raises(ClientInactiveError):
        bank.deposit(client.id, account_id, 100)


def test_search_logs_filters_by_tag_and_sorts() -> None:
    audit_log = AuditLog()
    first = _entry(AuditLogSeverity.MEDIUM, "new_account")
    second = _entry(AuditLogSeverity.HIGH, "transaction_amount")
    first.created_at = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    second.created_at = datetime(2026, 1, 1, 11, 0, tzinfo=UTC)
    audit_log.add(first)
    audit_log.add(second)

    assert [entry.tx_id for entry in audit_log.search_logs(tags=["new_account"])] == [
        first.tx_id
    ]
    assert [entry.tx_id for entry in audit_log.search_logs(sort="asc")] == [
        first.tx_id,
        second.tx_id,
    ]
    assert [entry.tx_id for entry in audit_log.search_logs(sort="desc")] == [
        second.tx_id,
        first.tx_id,
    ]
