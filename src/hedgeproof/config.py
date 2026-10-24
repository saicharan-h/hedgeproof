"""Load the frozen configuration files and compute their hashes.

A config hash is the SHA-256 of the canonical JSON of the parsed TOML, so it
does not change with comments or Windows/Linux line endings, only with values.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

from hedgeproof.records import hash_value

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"
RESULTS_DIR = REPO_ROOT / "results"
VAR_DIR = REPO_ROOT / "var"


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        return tomllib.load(f)


@dataclass(frozen=True)
class Policy:
    raw: dict[str, Any]

    @property
    def sha256(self) -> str:
        return hash_value(self.raw)

    @property
    def version(self) -> str:
        return self.raw["policy_version"]

    @property
    def instrument(self) -> str:
        return self.raw["instrument"]

    @property
    def contract_size(self) -> int:
        for key in ("contract_size", "contract_size_litres", "contract_size_gal"):
            if key in self.raw:
                return int(self.raw[key])
        raise KeyError("policy is missing a contract_size field")

    @property
    def max_hedge_ratio(self) -> float:
        return float(self.raw["max_hedge_ratio"])

    @property
    def shock(self) -> float:
        return float(self.raw["cash_stress_shock"])

    @property
    def cash_cap(self) -> float:
        return float(self.raw["cash_stress_cap_usd"])

    @property
    def stale_max_sessions(self) -> int:
        return int(self.raw["stale_max_sessions"])

    @property
    def currency(self) -> str:
        return str(self.raw.get("currency", "USD"))

    @property
    def currency_symbol(self) -> str:
        return str(self.raw.get("currency_symbol", "$" if self.currency == "USD" else self.currency))

    def n_cap(self, forecast_gallons: int) -> int:
        """Largest whole number of contracts within the exposure cap."""
        return int((self.max_hedge_ratio * forecast_gallons) // self.contract_size)


@dataclass(frozen=True)
class Settings:
    """Everything the trusted side needs: policy, experiment, agency, runtime."""

    policy: Policy
    experiment: dict[str, Any]
    agency: dict[str, Any]
    runtime: dict[str, Any]
    overrides: dict[str, Any] = field(default_factory=dict)

    @cached_property
    def hashes(self) -> dict[str, str]:
        return {
            "policy": self.policy.sha256,
            "experiment": hash_value(self.experiment),
            "agency": hash_value(self.agency),
            "costs": hash_value(self.experiment["costs"]),
            "metrics": hash_value(self.experiment["metrics"]),
            "splits": hash_value(self.experiment["splits"]),
            "pass_rule": hash_value(self.experiment["pass_rule"]),
        }

    @property
    def forecast_gallons(self) -> int:
        return int(self.agency["forecast_gallons_per_month"])

    @property
    def experiment_id(self) -> str:
        return self.experiment["experiment_id"]

    @property
    def research_clock(self) -> str:
        return self.experiment["research_clock"]

    @property
    def replay_date(self) -> str:
        return self.overrides.get("replay_date", self.experiment["operational"]["replay_date"])

    @property
    def cost_per_contract(self) -> float:
        c = self.experiment["costs"]
        return float(c["fee_per_contract_round_trip_usd"]) + 2 * c["slippage_ticks_per_side"] * float(
            c["tick_value_usd"]
        )


def load_settings(config_dir: Path | None = None, **overrides: Any) -> Settings:
    d = config_dir or Path(os.environ.get("HEDGEPROOF_CONFIG_DIR", CONFIG_DIR))
    return Settings(
        policy=Policy(load_toml(d / "policy.toml")),
        experiment=load_toml(d / "experiment.toml"),
        agency=load_toml(d / "agency_fixture.toml"),
        runtime=load_toml(d / "runtime.toml"),
        overrides=overrides,
    )
