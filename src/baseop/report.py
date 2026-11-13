from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict
from uuid import UUID

from baseop.audit import AuditLogSeverity
from baseop.bank import AccountKind, Bank
from baseop.clock import Clock, system_now
from baseop.transaction import TransactionType

ReportRow = dict[str, Any]


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
        self._clock = clock

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

        report["rows"].extend(accounts)

        transactions: list[ReportRow] = [
            {
                "section": "Transactions",
                "id": str(tx.id),
                "type": tx.type,
                "status": str(tx.status),
                "created_at": str(tx.created_at),
            }
            for tx in self._bank.get_transactions()
            if (tx.type == TransactionType.WITHDRAW and tx.from_client_id == client.id)
            if (tx.type == TransactionType.DEPOSIT and tx.to_client_id == client.id)
            or (tx.from_client_id == client.id)
            or (tx.to_client_id == client.id)
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

    def bank_report(self) -> Report:
        report: Report = self.report_template("Bank report", "bank")
        clients = self._bank.get_clients()
        accounts = self._bank.get_account_summaries()
        ranking = self._bank.get_clients_ranking()
        stats = self._bank.get_transaction_stats()
        errors = self._bank.get_error_stats()

        report["rows"].append(
            {
                "section": "Summary",
                "clients": len(clients),
                "accounts": len(accounts),
                "total_balance": self._bank.get_total_balance(),
                "transactions": stats["total"],
                "rejected": stats["rejected"],
            }
        )

        clients_by_id = {client.id: client for client in clients}
        for client_id, balance in ranking.items():
            client = clients_by_id[client_id]
            report["rows"].append(
                {
                    "section": "Clients",
                    "client": f"{client.first_name} {client.last_name}",
                    "status": client.status,
                    "risk_profile": client.risk_profile or "None",
                    "suspicious": client.suspicious,
                    "total_balance": balance,
                }
            )

        kind_counts: Counter[AccountKind] = Counter()
        kind_balances: dict[AccountKind, float] = {}
        for account in accounts:
            kind = account["kind"]
            kind_counts[kind] += 1
            kind_balances[kind] = kind_balances.get(kind, 0.0) + account["total_value"]

        for kind in AccountKind:
            report["rows"].append(
                {
                    "section": "Accounts by kind",
                    "kind": kind,
                    "accounts": kind_counts[kind],
                    "total_value": kind_balances.get(kind, 0.0),
                }
            )

        for name, value in stats.items():
            report["rows"].append(
                {
                    "section": "Transaction stats",
                    "metric": name,
                    "value": value,
                }
            )

        for name, value in errors.items():
            report["rows"].append(
                {"section": "Error stats", "metric": name, "value": value}
            )

        return report

    def risk_report(self) -> Report:
        report: Report = self.report_template("Risk report", "risk")
        clients = self._bank.get_clients()
        profiles = [
            (client, self._bank.get_client_risk_profile(client.id))
            for client in clients
        ]

        findings_by_severity: Counter[AuditLogSeverity] = Counter()
        for _, profile in profiles:
            findings_by_severity.update(profile["findings"])

        profile_counts = Counter(client.risk_profile or "UNRATED" for client in clients)

        report["rows"].append(
            {
                "section": "Summary",
                "clients": len(clients),
                "suspicious_clients": sum(1 for client in clients if client.suspicious),
                "high_risk": profile_counts["HIGH"],
                "medium_risk": profile_counts["MEDIUM"],
                "low_risk": profile_counts["LOW"],
                "unrated": profile_counts["UNRATED"],
                "low_findings": findings_by_severity[AuditLogSeverity.LOW],
                "medium_findings": findings_by_severity[AuditLogSeverity.MEDIUM],
                "high_findings": findings_by_severity[AuditLogSeverity.HIGH],
            }
        )

        for client, profile in profiles:
            findings = profile["findings"]
            report["rows"].append(
                {
                    "section": "Clients",
                    "client": f"{client.first_name} {client.last_name}",
                    "status": client.status,
                    "risk_profile": profile["risk_profile"] or "UNRATED",
                    "suspicious": profile["suspicious"],
                    "low": findings.get(AuditLogSeverity.LOW, 0),
                    "medium": findings.get(AuditLogSeverity.MEDIUM, 0),
                    "high": findings.get(AuditLogSeverity.HIGH, 0),
                    "total_findings": sum(findings.values()),
                }
            )

        names = {
            client.id: f"{client.first_name} {client.last_name}" for client in clients
        }
        for entry in self._bank.get_suspicious_operations():
            report["rows"].append(
                {
                    "section": "Suspicious operations",
                    "created_at": str(entry.created_at),
                    "severity": entry.severity.name,
                    "clients": ", ".join(
                        names.get(client_id, str(client_id))
                        for client_id in entry.client_ids
                    ),
                    "message": entry.message,
                    "tags": ", ".join(entry.tags),
                }
            )

        return report

    def export_to_json(self, report: Report, path=None) -> Path: ...
    def export_to_csv(self, report: Report, path=None) -> Path: ...
    def export_to_text(self, report: Report, path=None) -> Path:
        rows_by_section: dict[str, list[str]] = {}
        for row in report.get("rows"):
            section = row["section"]
            row_line = " | ".join(
                f"{key} = {value}" for key, value in row.items() if key != "section"
            )
            rows_by_section.setdefault(section, []).append(row_line)

        content = f"""
        {report.get("title")}
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
