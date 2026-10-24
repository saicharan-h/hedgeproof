"""Typed records shared by every part of HedgeProof, and canonical hashing.

Every record has an ``id`` (prefix + 12 hex characters), a ``schema_version``,
a ``created_at`` timestamp (UTC, ISO 8601) and a ``sha256`` computed over the
canonical JSON of all its other fields (sorted keys, compact separators,
UTF-8, no NaN or infinity). Hashes help detect changed evidence; they do not by
themselves prove that data or calculations are correct.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


def canonical_json(value: Any) -> bytes:
    """Serialize to canonical JSON bytes. Rejects NaN and infinity."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_value(value: Any) -> str:
    """SHA-256 of the canonical JSON of any JSON-compatible value."""
    return sha256_hex(canonical_json(value))


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6)}"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Record(BaseModel):
    """Base for every stored record. Subclasses set ``PREFIX``."""

    model_config = ConfigDict(extra="forbid")

    PREFIX: ClassVar[str] = "REC"

    id: str = ""
    schema_version: str = SCHEMA_VERSION
    created_at: str = ""
    sha256: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            self.id = new_id(self.PREFIX)
        if not self.created_at:
            self.created_at = utc_now()

    def body(self) -> dict[str, Any]:
        """All fields except the hash itself, as plain JSON-compatible data."""
        return self.model_dump(mode="json", exclude={"sha256"})

    def compute_sha256(self) -> str:
        return hash_value(self.body())

    def seal(self) -> "Record":
        """Compute and store the hash. Call once the record is complete."""
        self.sha256 = self.compute_sha256()
        return self

    def verify(self) -> bool:
        return bool(self.sha256) and self.sha256 == self.compute_sha256()


# --- Data -------------------------------------------------------------------


class SourceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    source_url: str
    retrieved_at: str
    retrieved_by: str
    sha256: str
    bytes: int


class SeriesInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    series_id: str
    name: str
    unit: str
    role: str
    first_date: str
    last_date: str
    observations: int


class DataManifest(Record):
    PREFIX: ClassVar[str] = "DM"
    files: list[SourceFile]
    series: list[SeriesInfo]
    sessions: int
    first_session: str
    last_session: str
    spot_missing_on_sessions: int
    continuity_flags: int
    continuity_boundaries: int
    period_table_sha256: str
    assumptions: dict[str, str]
    attribution: str = "Source: U.S. Energy Information Administration (EIA)"


# --- Research artifacts -----------------------------------------------------


class Candidate(Record):
    PREFIX: ClassVar[str] = "CAN"
    lineage_id: str
    ordinal: int = Field(ge=1, le=6)
    parent_id: str | None = None
    repair_count: int = Field(default=0, ge=0, le=2)
    source: str
    source_sha256: str
    family: str
    window: int
    params: dict[str, Any] = Field(default_factory=dict)
    change_note: str = ""
    created_by: str = ""
    origin: Literal["agent", "vetted_template", "test_fixture"] = "agent"


class VerificationReport(Record):
    PREFIX: ClassVar[str] = "VER"
    candidate_id: str
    source_sha256: str
    static_checks: list[dict[str, Any]]
    tests: list[dict[str, Any]]
    runner: str
    sandbox_image: str = ""
    sandbox_flags: list[str] = Field(default_factory=list)
    runtime_seconds: float = 0.0
    passed: bool


class BacktestReport(Record):
    PREFIX: ClassVar[str] = "BT"
    lineage_id: str
    strategy: str
    candidate_id: str | None = None
    source_sha256: str | None = None
    split: str
    n_positions: int
    rows: list[dict[str, Any]]
    metrics: dict[str, Any]
    comparison: dict[str, Any] = Field(default_factory=dict)
    config_hashes: dict[str, str]
    data_manifest_sha256: str
    label: str


class DiagnosticReport(Record):
    PREFIX: ClassVar[str] = "DX"
    candidate_id: str
    kind: str
    split: str
    result: dict[str, Any]
    base_metrics: dict[str, Any]
    interpretation: str


class FreezeRecord(Record):
    PREFIX: ClassVar[str] = "FRZ"
    lineage_id: str
    strategy: str
    candidate_id: str | None
    source_sha256: str | None
    config: dict[str, Any]
    validation_backtest_id: str | None
    data_manifest_sha256: str
    policy_sha256: str
    experiment_sha256: str
    agency_sha256: str


class HoldoutReport(Record):
    PREFIX: ClassVar[str] = "HO"
    lineage_id: str
    freeze_ids: list[str]
    consumed_at: str
    backtests: dict[str, dict[str, Any]]
    verdict: Literal["PASS", "ABSTAIN"]
    conditions: dict[str, Any]
    adaptive_vs_fixed50: dict[str, Any]
    label: str


# --- Evidence, intents, gate, approvals, orders -----------------------------


class EvidencePacket(Record):
    PREFIX: ClassVar[str] = "EVP"
    run_id: str
    lineage_id: str
    replay_date: str
    data_end_date: str
    data_manifest_id: str
    data_manifest_sha256: str
    policy_version: str
    policy_sha256: str
    experiment_sha256: str
    agency_sha256: str
    strategy: str
    candidate_id: str | None
    source_sha256: str | None
    artifacts: dict[str, str]
    recommendation: dict[str, Any]
    assumptions: dict[str, str]
    label: str


Side = Literal["BUY_OPEN", "SELL_CLOSE"]


class IntentTerms(BaseModel):
    """The exact order terms a human approves. Hashing these gives intent_hash."""

    model_config = ConfigDict(extra="forbid")
    evidence_packet_id: str
    evidence_packet_sha256: str
    replay_date: str
    hedge_month: str
    side: Side
    instrument: str
    delivery_month: str
    contracts: int = Field(ge=0, le=10_000)
    forecast_gallons: int = Field(gt=0, le=100_000_000)
    policy_sha256: str

    def intent_hash(self) -> str:
        return hash_value(self.model_dump(mode="json"))


class PaperIntent(Record):
    PREFIX: ClassVar[str] = "INT"
    intent_hash: str
    terms: IntentTerms
    exposure_ratio: float
    requested_by: str
    note: str = ""


class RuleOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule: str
    passed: bool
    reason_code: str | None = None
    detail: str


class GateDecision(Record):
    PREFIX: ClassVar[str] = "GATE"
    intent_hash: str
    policy_sha256: str
    ledger_version: int
    outcomes: list[RuleOutcome]
    verdict: Literal["ELIGIBLE", "BLOCKED", "HALT"]
    mode: Literal["dry_run", "submission"]


class Approval(Record):
    PREFIX: ClassVar[str] = "APR"
    intent_hash: str
    policy_sha256: str
    ledger_version: int
    approver: str
    approved_at: str
    replay_date: str
    used: bool = False


OrderStatus = Literal["ACCEPTED", "FILLED", "REJECTED", "UNKNOWN"]


class Order(Record):
    PREFIX: ClassVar[str] = "ORD"
    idempotency_key: str
    intent_hash: str
    status: OrderStatus
    side: Side
    contracts: int
    delivery_month: str
    fill_price: float | None = None
    fill_date: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)
    injected_ack_timeout: bool = False


# --- Agents and events ------------------------------------------------------


class AgentDecision(Record):
    PREFIX: ClassVar[str] = "DEC"
    run_id: str
    role: str
    step: int
    summary: str = Field(max_length=600)
    action: str
    evidence_ids: list[str]
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    model: str
    mode: Literal["live", "test_double", "recorded_replay"]
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    latency_seconds: float = 0.0


class Event(BaseModel):
    """Append-only event log entry (the database rejects updates and deletes)."""

    model_config = ConfigDict(extra="forbid")
    seq: int | None = None
    ts: str = Field(default_factory=utc_now)
    actor: str
    kind: str
    refs: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_sha256: str = ""
