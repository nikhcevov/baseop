from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict
from uuid import UUID

from baseop.bank import Bank
from baseop.clock import Clock, system_now
from baseop.transaction import TransactionType


class ReportRow(TypedDict, extra_items=Any):
    section: str


ReportType = Literal["client", "risk", "bank"]


class Report(TypedDict):
    type: ReportType
    title: str
    created_at: datetime
    rows: list[ReportRow]


class ReportError(Exception):
    pass


class ReportBuilder:
    def __init__(
        self, bank: Bank, output_dir: str = "reports", clock: Clock = system_now
    ):
        self._bank = bank
        self._output_dir = Path(output_dir)
        self._clock = system_now

    def report_template(self, name: str, type: ReportType) -> Report:
        return {"type": type, "title": name, "created_at": self._clock(), "rows": []}

    def client_report(self, client_id: UUID) -> Report:
        client = self._bank.get_client(client_id)
        if not client:
            raise ReportError("Client not found")
        report: Report = self.report_template(
            f"Client report: {client.first_name} {client.last_name}", "client"
        )

        report["rows"].append(
            {
                "section": "Summary",
                "client": f"{client.first_name} {client.last_name}",
                "status": client.status,
            }
        )

        accounts: list[ReportRow] = [
            {
                "section": "Accounts",
                "account_id": account.get("account_id"),
                "account_kind": account.get("kind"),
                "status": account.get("status"),
                "currency": account.get("currency"),
                "balance": account.get("balance"),
            }
            for account in self._bank.get_account_summaries()
            if account.get("client_id") == client.id
        ]

        report["rows"].append(*accounts)

        transactions: list[ReportRow] = [
            {
                "section": "Transactions",
                "id": str(tx.id),
                "type": tx.type,
                "status": str(tx.status),
                "created_at": str(tx.created_at),
            }
            for tx in self._bank.get_transactions()
            if (tx.type == TransactionType.DEPOSIT and tx.to_account_id == client.id)
            or (tx.from_client_id == client.id)
        ]

        report["rows"].append(*transactions)

        report["rows"].append(
            {
                "section": "Risk",
                "risk_profile": client.risk_profile or "None",
                "suspicious": client.suspicious,
            }
        )

        return report

    def bank_report(self) -> dict: ...
    def risk_report(self) -> dict: ...

    def export_to_json(self, report: Report, path=None) -> Path: ...
    def export_to_csv(self, report: Report, path=None) -> Path: ...
    def export_to_text(self, report: Report, path=None) -> Path:
        rows_by_section: dict[str, list[str]] = {}
        for row in report.get("rows"):
            section = row.get("section")
            row_line = " | ".join(f"{key} = {value}" for key, value in row.items())
            rows_by_section.setdefault(section, []).append(row_line)

        content = f"""
        Client report: {report.get("title")}
        Generated: {report.get("created_at")}

        {
            "".join(
                f"\n{section}\n{'-' * len(section)}\n{''.join(f'{line}\n' for line in lines)}"
                for section, lines in rows_by_section.items()
            )
        }
        """

        target = Path(path or self._output_dir / f"{report.get('type')}-report.txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def save_charts(self, report: Report, directory=None) -> list[Path]: ...
