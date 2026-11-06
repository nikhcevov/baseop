import json
from collections import Counter
from datetime import datetime, time, timedelta
from enum import IntEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from baseop.config import APP_TIMEZONE, convert
from baseop.transaction import Transaction, TransactionType


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
        logs = log_entries if log_entries and len(log_entries) else self._logs
        with open(path, "w", encoding="utf-8") as file:
            json.dump(logs, file, default=str)

    def search_logs(
        self,
        *,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        sort: Literal["asc", "desc"] | None = None,
        severity: AuditLogSeverity | None = None,
        tx_id: UUID | None = None,
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
        ]
        if sort:
            reverse = sort == "desc"
            search_result.sort(reverse=reverse, key=lambda x: x.created_at)

        return search_result

    def get_report(self) -> str:
        by_tags = Counter(tag for log in self._logs for tag in log.tags)
        by_severity = Counter(log.severity for log in self._logs)

        return f"""
        Most frequent log tags: {by_tags.most_common(3)}\n
        Log tags count: {len(by_tags)}
        Severity details: {by_severity.items()}
        """


class RiscAnalyzer:
    def __init__(self) -> None:
        self._SUSPICIOUS_TIME_START = time(5, tzinfo=APP_TIMEZONE)
        self._SUSPICIOUS_TIME_END = time(8, tzinfo=APP_TIMEZONE)
        self._RUB_TO_RISK_MAPPING = {
            AuditLogSeverity.HIGH: 1_000_000,
            AuditLogSeverity.MEDIUM: 350_000,
        }
        self._TRANSACTION_TYPE_TO_ATTRIBUTE_MAPPING = {
            TransactionType.WITHDRAW: "from_client_id"
        }
        self._SUSPICIOUS_OP_COUNT = 10
        self._SISPICIOUS_OP_TIME_SEC_WINDOW = 60

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
        window_delta = timedelta(seconds=self._SISPICIOUS_OP_TIME_SEC_WINDOW / 2)
        near_logs = audit_log.search_logs(
            created_from=tx.scheduled_at - window_delta,
            created_to=tx.scheduled_at + window_delta,
        )
        if len(near_logs) >= self._SUSPICIOUS_OP_COUNT:
            return LogEntry(
                severity=AuditLogSeverity.MEDIUM,
                tx_id=tx.id,
                message="Operation count is suspicious",
                tags=["operation_count"],
                client_ids=self._tx_client_ids(tx),
            )

    def _check_new_account_transfer(self, tx: Transaction) -> LogEntry | None:
        pass

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
        checks = [
            self._check_operation_time(tx),
            self._check_transaction_amount(tx),
            self._check_new_account_transfer(tx),
            self._check_frequent_operations(tx, audit_log),
        ]

        issues = [i for i in checks if i is not None]
        if not len(issues):
            return

        return issues
