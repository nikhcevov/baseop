import json
from collections import Counter
from datetime import datetime, time, timedelta
from enum import IntEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from baseop.config import APP_TIMEZONE, convert
from baseop.transaction import Transaction, TransactionType
from baseop.uuid import AccountId


class AuditLogSeverity(IntEnum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class LogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    tx_id: UUID
    client_ids: list[UUID]
    severity: AuditLogSeverity
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(APP_TIMEZONE))
    tags: list[str] = Field(default_factory=list)


class AuditLog:
    def __init__(self) -> None:
        self._logs: list[LogEntry] = []

    def add(self, log: LogEntry) -> None:
        self._logs.append(log)

    def export_to_file(
        self, log_entries: list[LogEntry] | None = None, path: str = "logs.json"
    ) -> None:
        logs = self._logs if log_entries is None else log_entries
        payload = [entry.model_dump(mode="json") for entry in logs]
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def search_logs(
        self,
        *,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        sort: Literal["asc", "desc"] | None = None,
        severity: AuditLogSeverity | None = None,
        tx_id: UUID | None = None,
        client_id: UUID | None = None,
        tags: list[str] | None = None,
    ) -> list[LogEntry]:
        search_result = [
            log
            for log in self._logs
            if (created_from is None or log.created_at >= created_from)
            and (created_to is None or log.created_at < created_to)
            and (severity is None or log.severity is severity)
            and (tx_id is None or log.tx_id == tx_id)
            and (tags is None or any(tag in log.tags for tag in tags))
            and (
                client_id is None
                or any(uid for uid in log.client_ids if uid == client_id)
            )
        ]
        if sort:
            reverse = sort == "desc"
            search_result.sort(reverse=reverse, key=lambda x: x.created_at)

        return search_result

    def get_report(self) -> str:
        by_tags = Counter(tag for log in self._logs for tag in log.tags)
        by_severity = Counter(log.severity for log in self._logs)
        by_client = Counter(
            client_id for log in self._logs for client_id in log.client_ids
        )

        return f"""
        Most frequent log tags: {by_tags.most_common(3)}\n
        Log tags count: {len(by_tags)}
        Severity details: {by_severity.items()}
        Risk zone clients: {by_client.items()}
        """


class RiscAnalyzer:
    def __init__(self) -> None:
        self._SUSPICIOUS_TIME_START = time(5, tzinfo=APP_TIMEZONE)
        self._SUSPICIOUS_TIME_END = time(8, tzinfo=APP_TIMEZONE)
        self._RUB_TO_RISK_MAPPING = {
            AuditLogSeverity.HIGH: 1_000_000,
            AuditLogSeverity.MEDIUM: 350_000,
        }
        self._SUSPICIOUS_OP_COUNT = 10
        self._SUSPICIOUS_OP_TIME_SEC_WINDOW = 60
        self._seen_recipients: dict[UUID, set[AccountId]] = {}
        self._audited_tx_ids: set[UUID] = set()

    def _tx_client_ids(self, tx: Transaction) -> list[UUID]:
        return [uid for uid in [tx.from_client_id, tx.to_client_id] if uid is not None]

    def _check_transaction_amount(self, tx: Transaction) -> LogEntry | None:
        rub_equivalent = convert(tx.amount, tx.currency, "RUB")
        for severity in sorted(self._RUB_TO_RISK_MAPPING, reverse=True):
            if rub_equivalent >= self._RUB_TO_RISK_MAPPING[severity]:
                return LogEntry(
                    severity=severity,
                    tx_id=tx.id,
                    client_ids=self._tx_client_ids(tx),
                    message="Transaction amount in danger zone",
                    tags=["transaction_amount"],
                )

    def _check_frequent_operations(
        self, tx: Transaction, audit_log: AuditLog
    ) -> LogEntry | None:
        window_start = tx.created_at - timedelta(
            seconds=self._SUSPICIOUS_OP_TIME_SEC_WINDOW
        )
        for client_id in self._tx_client_ids(tx):
            operations = audit_log.search_logs(
                created_from=window_start,
                client_id=client_id,
                tags=["transaction"],
            )
            if len(operations) >= self._SUSPICIOUS_OP_COUNT - 1:
                return LogEntry(
                    severity=AuditLogSeverity.MEDIUM,
                    tx_id=tx.id,
                    message="Operation count is suspicious",
                    tags=["operation_count"],
                    client_ids=[client_id],
                )
        return None

    def _check_new_account_transfer(self, tx: Transaction) -> LogEntry | None:
        if (
            tx.type is not TransactionType.TRANSFER
            or tx.from_client_id is None
            or tx.to_account_id is None
            or tx.to_client_id == tx.from_client_id
        ):
            return None

        seen = self._seen_recipients.setdefault(tx.from_client_id, set())
        if tx.to_account_id in seen:
            return None
        seen.add(tx.to_account_id)

        return LogEntry(
            severity=AuditLogSeverity.MEDIUM,
            tx_id=tx.id,
            message="Transfer to a new account",
            tags=["new_account"],
            client_ids=[tx.from_client_id],
        )

    def _check_operation_time(self, tx: Transaction) -> LogEntry | None:
        if (
            self._SUSPICIOUS_TIME_START
            <= time(
                tx.scheduled_at.hour,
                tx.scheduled_at.minute,
                tx.scheduled_at.second,
                tx.scheduled_at.microsecond,
                tzinfo=APP_TIMEZONE,
            )
            <= self._SUSPICIOUS_TIME_END
        ):
            return LogEntry(
                severity=AuditLogSeverity.LOW,
                tx_id=tx.id,
                message="Operation time in danger zone",
                tags=["operation_time"],
                client_ids=self._tx_client_ids(tx),
            )

    def audit_operation(
        self, tx: Transaction, audit_log: AuditLog
    ) -> list[LogEntry] | None:
        if tx.id in self._audited_tx_ids:
            return None
        self._audited_tx_ids.add(tx.id)

        checks = [
            self._check_operation_time(tx),
            self._check_transaction_amount(tx),
            self._check_new_account_transfer(tx),
            self._check_frequent_operations(tx, audit_log),
        ]

        op_log = LogEntry(
            severity=AuditLogSeverity.NONE,
            tx_id=tx.id,
            message="Operation ok",
            tags=["transaction"],
            client_ids=self._tx_client_ids(tx),
        )

        issues = [i for i in checks if i is not None]
        issues.append(op_log)

        return issues
