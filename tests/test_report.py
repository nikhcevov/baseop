import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from baseop.bank import AccountKind, Bank, SuspiciousOperationError
from baseop.client import Client
from baseop.clock import FrozenClock
from baseop.report import Chart, Report, ReportBuilder, ReportError
from baseop.transaction import TransactionType

DAY = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


@dataclass
class Demo:
    bank: Bank
    clock: FrozenClock
    alice: Client
    bob: Client
    carol: Client
    alice_bank: str
    alice_saving: str
    bob_bank: str
    carol_bank: str


@pytest.fixture
def demo() -> Demo:
    clock = FrozenClock(DAY)
    bank = Bank(clock=clock)

    alice = bank.add_client(
        first_name="Alice", last_name="Smith", age=30, secret="secret"
    )
    bob = bank.add_client(
        first_name="Bob", last_name="Jones", age=40, secret="secret"
    )
    carol = bank.add_client(
        first_name="Carol", last_name="Brown", age=35, secret="secret"
    )
    for client in (alice, bob, carol):
        bank.authenticate_client(client.id, "secret")

    alice_bank = bank.open_account(alice.id, AccountKind.BANK)["account_id"]
    alice_saving = bank.open_account(alice.id, AccountKind.SAVING)["account_id"]
    bob_bank = bank.open_account(bob.id, AccountKind.BANK)["account_id"]
    carol_bank = bank.open_account(carol.id, AccountKind.BANK)["account_id"]

    def step(operation):
        clock.advance(timedelta(minutes=1))
        return operation()

    step(lambda: bank.deposit(alice.id, alice_bank, 1_000))
    step(lambda: bank.deposit(alice.id, alice_saving, 500))
    step(lambda: bank.deposit(alice.id, alice_bank, 400_000))
    step(lambda: bank.deposit(bob.id, bob_bank, 500))
    step(lambda: bank.withdraw(alice.id, alice_bank, 200))
    step(
        lambda: bank.submit_transfer(
            alice.id, alice_bank, 100, to_account_id=alice_saving
        )
    )
    step(bank.run_transactions)
    with pytest.raises(SuspiciousOperationError):
        step(lambda: bank.deposit(carol.id, carol_bank, 1_000_000))

    return Demo(
        bank=bank,
        clock=clock,
        alice=alice,
        bob=bob,
        carol=carol,
        alice_bank=alice_bank,
        alice_saving=alice_saving,
        bob_bank=bob_bank,
        carol_bank=carol_bank,
    )


def _builder(demo: Demo, output_dir: str | Path = "reports") -> ReportBuilder:
    return ReportBuilder(demo.bank, output_dir=output_dir, clock=demo.clock)


def _sections(report: Report, name: str) -> list[dict]:
    return [row for row in report["rows"] if row["section"] == name]


def _charts(report: Report) -> dict[str, Chart]:
    return {chart["filename"]: chart for chart in report["charts"]}


def test_client_report_rows_and_charts(demo: Demo) -> None:
    report = _builder(demo).client_report(demo.alice.id)

    assert report["type"] == "client"
    accounts = _sections(report, "Accounts")
    assert len(accounts) == 2
    assert {
        row["account_kind"]: row["balance"] for row in accounts
    } == {AccountKind.BANK: 400_700.0, AccountKind.SAVING: 600.0}

    transaction_types = Counter(
        row["type"] for row in _sections(report, "Transactions")
    )
    assert transaction_types == Counter(
        {
            TransactionType.DEPOSIT: 3,
            TransactionType.WITHDRAW: 1,
            TransactionType.TRANSFER: 1,
        }
    )

    charts = _charts(report)
    pie = charts["account_types.png"]
    assert dict(zip(pie["labels"], pie["values"], strict=True)) == {
        AccountKind.BANK: 400_700.0,
        AccountKind.SAVING: 600.0,
    }

    bar = charts["transaction_types.png"]
    assert dict(zip(bar["labels"], bar["values"], strict=True)) == {
        TransactionType.DEPOSIT: 3,
        TransactionType.WITHDRAW: 1,
        TransactionType.TRANSFER: 1,
    }

    plot = charts["balance_history.png"]
    assert len(plot["labels"]) == len(plot["values"])
    assert plot["values"][0] == 0.0
    assert plot["values"][-1] == 401_300.0


def test_bank_report_rows_and_charts(demo: Demo) -> None:
    report = _builder(demo).bank_report()
    summary = _sections(report, "Summary")[0]

    assert summary["clients"] == 3
    assert summary["accounts"] == 4
    assert summary["total_balance"] == 401_800.0
    assert summary["transactions"] == 7
    assert summary["rejected"] == 1

    charts = _charts(report)
    pie = charts["bank_balances_by_kind.png"]
    assert dict(zip(pie["labels"], pie["values"], strict=True)) == {
        "bank": 401_200.0,
        "saving": 600.0,
    }

    bar = charts["bank_top_clients.png"]
    assert dict(zip(bar["labels"], bar["values"], strict=True)) == {
        "Alice Smith": 401_300.0,
        "Bob Jones": 500.0,
        "Carol Brown": 0.0,
    }

    plot = charts["bank_balance_history.png"]
    assert plot["values"][0] == 0.0
    assert plot["values"][-1] == 401_800.0


def test_risk_report_rows_and_charts(demo: Demo) -> None:
    report = _builder(demo).risk_report()
    summary = _sections(report, "Summary")[0]

    assert summary["high_risk"] == 1
    assert summary["medium_risk"] == 1
    assert summary["low_risk"] == 0
    assert summary["unrated"] == 1
    assert summary["suspicious_clients"] == 2
    assert summary["low_findings"] == 0
    assert summary["medium_findings"] == 1
    assert summary["high_findings"] == 1

    charts = _charts(report)
    pie = charts["risk_profiles.png"]
    assert dict(zip(pie["labels"], pie["values"], strict=True)) == {
        "HIGH": 1,
        "MEDIUM": 1,
        "UNRATED": 1,
    }

    bar = charts["risk_findings_by_severity.png"]
    assert bar["labels"] == ["LOW", "MEDIUM", "HIGH"]
    assert bar["values"] == [0, 1, 1]

    suspicious = _sections(report, "Suspicious operations")
    assert len(suspicious) == 2
    assert {row["severity"] for row in suspicious} == {"MEDIUM", "HIGH"}


def test_client_report_unknown_client_raises(demo: Demo) -> None:
    with pytest.raises(ReportError, match="Client not found"):
        _builder(demo).client_report(uuid4())


def test_exports_json_and_csv(demo: Demo, tmp_path: Path) -> None:
    builder = _builder(demo, tmp_path)
    reports = [
        builder.client_report(demo.alice.id),
        builder.bank_report(),
        builder.risk_report(),
    ]

    for report in reports:
        json_path = builder.export_to_json(report)
        csv_path = builder.export_to_csv(report)

        assert json_path == tmp_path / f"{report['type']}-report.json"
        assert csv_path == tmp_path / f"{report['type']}-report.csv"

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["type"] == report["type"]
        assert payload["created_at"] == demo.clock().isoformat()
        assert len(payload["rows"]) == len(report["rows"])
        assert len(payload["charts"]) == len(report["charts"])
        assert payload["rows"][0]["section"] == "Summary"

        with csv_path.open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            rows = list(reader)

        assert reader.fieldnames is not None
        assert reader.fieldnames[0] == "section"
        assert "charts" not in reader.fieldnames
        assert len(rows) == len(report["rows"])
        assert rows[0]["section"] == "Summary"


def test_export_to_custom_path(demo: Demo, tmp_path: Path) -> None:
    builder = _builder(demo, tmp_path)
    report = builder.client_report(demo.alice.id)

    json_path = builder.export_to_json(report, tmp_path / "nested" / "client.json")
    csv_path = builder.export_to_csv(report, tmp_path / "nested" / "client.csv")

    assert json_path.exists()
    assert csv_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["type"] == "client"


def test_save_charts_writes_png_files(demo: Demo, tmp_path: Path) -> None:
    builder = _builder(demo, tmp_path)
    report = builder.client_report(demo.alice.id)

    paths = builder.save_charts(report, tmp_path / "charts")

    assert {path.name for path in paths} == {
        "account_types.png",
        "transaction_types.png",
        "balance_history.png",
    }
    for path in paths:
        assert path.exists()
        assert path.stat().st_size > 1_000
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_save_charts_skips_empty_pie(tmp_path: Path) -> None:
    clock = FrozenClock(DAY)
    builder = ReportBuilder(Bank(clock=clock), output_dir=tmp_path, clock=clock)
    report = builder.bank_report()

    assert [chart["type"] for chart in report["charts"]] == ["plot"]
    paths = builder.save_charts(report, tmp_path / "charts")
    assert [path.name for path in paths] == ["bank_balance_history.png"]
