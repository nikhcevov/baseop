from datetime import datetime, time
from enum import IntEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from baseop.config import APP_TIMEZONE, convert
from baseop.transaction import Transaction
from baseop.uuid import AccountId


class AuditLogSeverity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class LogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(APP_TIMEZONE))
    severity: AuditLogSeverity
    message: str
    tags: list[str] = Field(default_factory=list)
    tx_id: UUID


class AuditLog:
    def __init__(self) -> None:
        self._logs: list[LogEntry] = []

    def export_to_file(self, log_entries: list[LogEntry] | None = None) -> None:
        pass

    def search_logs(
        self,
        created_from: datetime,
        created_to: datetime,
        sort: Literal["asc", "desc"],
        severity: AuditLogSeverity,
    ) -> list[LogEntry]:
        return []


class RiscAnalyzer:
    def __init__(self) -> None:
        self._SUSPICIOUS_TIME_START = time(5, tzinfo=APP_TIMEZONE)
        self._SUSPICIOUS_TIME_END = time(8, tzinfo=APP_TIMEZONE)
        self._seen_clients: dict[UUID, set[AccountId]] = {}

    def _check_transaction_amount(self, tx: Transaction) -> LogEntry | None:
        _RUB_TO_RISK_MAPPING = {
            AuditLogSeverity.HIGH: 1_000_000,
            AuditLogSeverity.MEDIUM: 350_000,
        }
        rub_equivalent = convert(tx.amount, tx.currency, "RUB")
        for severity in sorted(_RUB_TO_RISK_MAPPING, reverse=True):
            if rub_equivalent >= _RUB_TO_RISK_MAPPING[severity]:
                return LogEntry(
                    severity=severity,
                    tx_id=tx.id,
                    message="Transaction amount in danger zone",
                    tags=["transaction_amount"],
                )

    def _check_frequent_operations(self, tx: Transaction) -> LogEntry | None:
        pass

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
            )

    def audit_operation(self, tx: Transaction) -> None:
        issues: list[LogEntry] = []
        checks = (
            self._check_operation_time(tx),
            self._check_transaction_amount(tx),
            self._check_new_account_transfer(tx),
            self._check_frequent_operations(tx),
        )
        issues.extend(check for check in checks if check is not None)
        if not len(issues):
            return

        max_severity = max(issue.severity for issue in issues)

        if max_severity == AuditLogSeverity.HIGH:
            # mark client
            pass

    def get_report(self) -> str:
        return """
        Suspicious operations: {} times, includes {} HIGH, {} MEDIUM and {} LOW
        Client's risc profile is {}
        Error stats: {}
        """
