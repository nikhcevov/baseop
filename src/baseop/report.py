import csv
import io
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, TypedDict
from uuid import UUID

from baseop.audit import AuditLogSeverity
from baseop.bank import AccountKind, AccountSummary, Bank
from baseop.client import Client
from baseop.clock import Clock, system_now
from baseop.config import convert
from baseop.transaction import Transaction, TransactionStatus, TransactionType

ReportRow = dict[str, Any]


ReportType = Literal["client", "risk", "bank"]


class Chart(TypedDict):
    type: Literal["pie", "bar", "plot"]
    title: str
    filename: str
    labels: list[str]
    values: list[float | int]


class Report(TypedDict):
    type: ReportType
    title: str
    created_at: datetime
    rows: list[ReportRow]
    charts: list[Chart]


class ReportError(Exception):
    pass


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return str(value.value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, default=_json_default)
    return value


class ReportBuilder:
    def __init__(
        self, bank: Bank, output_dir: str = "reports", clock: Clock = system_now
    ):
        self._bank = bank
        self._output_dir = Path(output_dir)
        self._clock = clock

    def report_template(self, name: str, type: ReportType) -> Report:
        return {
            "type": type,
            "title": name,
            "created_at": self._clock(),
            "rows": [],
            "charts": [],
        }

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

        accounts = [
            account
            for account in self._bank.get_account_summaries()
            if account.get("client_id") == client.id
        ]
        account_rows: list[ReportRow] = [
            {
                "section": "Accounts",
                "account_id": account.get("account_id"),
                "account_kind": account.get("kind"),
                "status": account.get("status"),
                "currency": account.get("currency"),
                "balance": account.get("balance"),
            }
            for account in accounts
        ]

        report["rows"].extend(account_rows)

        transactions = [
            tx
            for tx in self._bank.get_transactions()
            if (tx.from_client_id == client.id) or (tx.to_client_id == client.id)
        ]
        transaction_rows: list[ReportRow] = [
            {
                "section": "Transactions",
                "id": str(tx.id),
                "type": tx.type,
                "status": str(tx.status),
                "created_at": str(tx.created_at),
            }
            for tx in transactions
        ]

        report["rows"].extend(transaction_rows)

        report["rows"].append(
            {
                "section": "Risk",
                "risk_profile": client.risk_profile or "None",
                "suspicious": client.suspicious,
            }
        )

        balance_by_account_kind = defaultdict(float)
        for account in accounts:
            balance = account.get("balance", 0.0)
            currency = account.get("currency")
            balance_in_rub = convert(balance, currency, "RUB")
            balance_by_account_kind[account.get("kind")] += balance_in_rub
        account_types_chart: Chart = {
            "type": "pie",
            "title": "Balances by account type",
            "filename": "account_types.png",
            "labels": list(balance_by_account_kind.keys()),
            "values": list(balance_by_account_kind.values()),
        }
        report["charts"].append(account_types_chart)

        tx_type_count = Counter(tx.type for tx in transactions)
        tx_types_chart: Chart = {
            "type": "bar",
            "title": "Transaction count by transaction type",
            "filename": "transaction_types.png",
            "labels": list(tx_type_count.keys()),
            "values": list(tx_type_count.values()),
        }
        report["charts"].append(tx_types_chart)

        sorted_tx_by_time = sorted(
            (tx for tx in transactions if tx.status is TransactionStatus.COMPLETED),
            key=lambda x: x.finished_at or x.created_at,
        )
        total_balance_deltas = []
        for tx in sorted_tx_by_time:
            internal = tx.from_client_id == client.id and tx.to_client_id == client.id

            if internal:
                total_balance_deltas.append(0.0)
            elif tx.to_client_id == client.id:
                total_balance_deltas.append(convert(tx.amount, tx.currency, "RUB"))
            else:
                total_balance_deltas.append(
                    -convert(tx.amount + tx.fee, tx.currency, "RUB")
                )

        starting_balance = sum(
            convert(account.get("balance"), account.get("currency"), "RUB")
            for account in accounts
        ) - sum(total_balance_deltas)

        balance = starting_balance
        balance_history = [balance]

        for delta in total_balance_deltas:
            balance += delta
            balance_history.append(balance)

        tx_timestamps = [
            str(tx.finished_at or tx.created_at) for tx in sorted_tx_by_time
        ]
        client_balance_history_chart: Chart = {
            "type": "plot",
            "title": "Balance history",
            "filename": "balance_history.png",
            "labels": ["start", *tx_timestamps],
            "values": balance_history,
        }
        report["charts"].append(client_balance_history_chart)

        return report

    def bank_report(self) -> Report:
        report: Report = self.report_template("Bank report", "bank")
        clients = self._bank.get_clients()
        accounts = self._bank.get_account_summaries()
        ranking = self._bank.get_clients_ranking()
        transactions = self._bank.get_transactions()
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

        report["charts"].extend(self._bank_charts(clients, accounts, transactions))
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

        report["charts"].extend(self._risk_charts(clients, findings_by_severity))
        return report

    def _bank_charts(
        self,
        clients: Sequence[Client],
        accounts: Sequence[AccountSummary],
        transactions: Sequence[Transaction],
    ) -> list[Chart]:
        charts: list[Chart] = []

        balances_by_kind: dict[AccountKind, float] = defaultdict(float)
        for account in accounts:
            balances_by_kind[account["kind"]] += convert(
                account["total_value"], account["currency"], "RUB"
            )
        kind_items = [
            (kind, value) for kind, value in balances_by_kind.items() if value > 0
        ]
        if kind_items:
            charts.append(
                {
                    "type": "pie",
                    "title": "Balances by account kind",
                    "filename": "bank_balances_by_kind.png",
                    "labels": [kind.value for kind, _ in kind_items],
                    "values": [value for _, value in kind_items],
                }
            )

        balances_by_client: dict[UUID, float] = defaultdict(float)
        for account in accounts:
            balances_by_client[account["client_id"]] += convert(
                account["total_value"], account["currency"], "RUB"
            )
        names = {
            client.id: f"{client.first_name} {client.last_name}" for client in clients
        }
        top_clients = sorted(
            balances_by_client.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:10]
        if top_clients:
            charts.append(
                {
                    "type": "bar",
                    "title": "Top clients by balance",
                    "filename": "bank_top_clients.png",
                    "labels": [
                        names.get(client_id, str(client_id))
                        for client_id, _ in top_clients
                    ],
                    "values": [value for _, value in top_clients],
                }
            )

        current_balance = sum(
            convert(account["total_value"], account["currency"], "RUB")
            for account in accounts
        )
        completed = sorted(
            (tx for tx in transactions if tx.status is TransactionStatus.COMPLETED),
            key=lambda tx: tx.finished_at or tx.created_at,
        )
        deltas = [self._bank_delta(tx) for tx in completed]
        balance = current_balance - sum(deltas)
        labels = ["start"]
        values = [balance]
        for tx, delta in zip(completed, deltas, strict=True):
            balance += delta
            labels.append(str(tx.finished_at or tx.created_at))
            values.append(balance)

        charts.append(
            {
                "type": "plot",
                "title": "Bank balance history",
                "filename": "bank_balance_history.png",
                "labels": labels,
                "values": values,
            }
        )
        return charts

    @staticmethod
    def _bank_delta(tx: Transaction) -> float:
        if tx.status is not TransactionStatus.COMPLETED:
            return 0.0
        if tx.type is TransactionType.DEPOSIT:
            return convert(tx.amount, tx.currency, "RUB")
        if tx.type is TransactionType.WITHDRAW:
            return -convert(tx.amount, tx.currency, "RUB")
        if tx.is_external:
            return -convert(tx.amount + tx.fee, tx.currency, "RUB")
        return 0.0

    def _risk_charts(
        self,
        clients: Sequence[Client],
        findings_by_severity: Counter[AuditLogSeverity],
    ) -> list[Chart]:
        charts: list[Chart] = []

        profile_counts = Counter(client.risk_profile or "UNRATED" for client in clients)
        profile_items = [
            (label, profile_counts[label])
            for label in ("HIGH", "MEDIUM", "LOW", "UNRATED")
            if profile_counts[label]
        ]
        if profile_items:
            charts.append(
                {
                    "type": "pie",
                    "title": "Risk profile distribution",
                    "filename": "risk_profiles.png",
                    "labels": [label for label, _ in profile_items],
                    "values": [count for _, count in profile_items],
                }
            )

        charts.append(
            {
                "type": "bar",
                "title": "Findings by severity",
                "filename": "risk_findings_by_severity.png",
                "labels": [
                    AuditLogSeverity.LOW.name,
                    AuditLogSeverity.MEDIUM.name,
                    AuditLogSeverity.HIGH.name,
                ],
                "values": [
                    findings_by_severity[AuditLogSeverity.LOW],
                    findings_by_severity[AuditLogSeverity.MEDIUM],
                    findings_by_severity[AuditLogSeverity.HIGH],
                ],
            }
        )
        return charts

    def export_to_json(
        self, report: Report, path: str | Path | None = None
    ) -> Path:
        target = Path(
            path or self._output_dir / f"{report['type']}-report.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            )
            + "\n",
            encoding="utf-8",
        )
        return target

    def export_to_csv(
        self, report: Report, path: str | Path | None = None
    ) -> Path:
        fieldnames: list[str] = ["section"]
        for row in report["rows"]:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)

        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for row in report["rows"]:
            writer.writerow(
                {
                    key: _csv_value(row.get(key))
                    for key in fieldnames
                }
            )

        target = Path(
            path or self._output_dir / f"{report['type']}-report.csv"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(buffer.getvalue(), encoding="utf-8")
        return target

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

    def save_charts(self, report: Report, directory=None) -> list[Path]:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        out = Path(directory or self._output_dir / "charts")
        out.mkdir(parents=True, exist_ok=True)

        paths: list[Path] = []

        for chart in report["charts"]:
            fig, ax = plt.subplots(figsize=(8, 5))
            try:
                if chart["type"] == "pie":
                    if not chart["values"] or sum(chart["values"]) == 0:
                        continue
                    ax.pie(
                        chart["values"],
                        labels=chart["labels"],
                        autopct="%1.1f%%",
                        startangle=90,
                    )
                    ax.axis("equal")
                elif chart["type"] == "bar":
                    ax.bar(chart["labels"], chart["values"])
                    ax.grid(axis="y", alpha=0.3)
                    ax.tick_params(axis="x", labelrotation=45, labelsize=8)
                else:
                    positions = range(len(chart["values"]))
                    ax.plot(positions, chart["values"], marker="o", linewidth=2)
                    ax.set_xticks(list(positions))
                    ax.set_xticklabels(
                        chart["labels"], rotation=45, ha="right", fontsize=8
                    )
                    ax.grid(True, alpha=0.3)

                ax.set_title(chart["title"])
                fig.tight_layout()
                path = out / chart["filename"]
                fig.savefig(path, dpi=150)
                paths.append(path)

            finally:
                plt.close(fig)

        return paths
