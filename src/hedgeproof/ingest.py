"""Build the data manifest and derived period table from raw EIA files. Owner: Nikshep.

Raw files are committed unmodified in data/raw/. The manifest records each
file's SHA-256, size, source URL, who downloaded it and when (as reported by
the team), plus series facts, missing-spot counts and the continuity check.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hedgeproof.config import DATA_DIR, Settings
from hedgeproof.data import (
    EXPECTED_UNIT,
    SERIES_ROLES,
    SOURCE_URLS,
    MarketData,
    build_period_table,
    continuity_report,
    file_sha256,
    load_market_data,
    table_records,
    table_sha256,
)
from hedgeproof.india import (
    INDIAN_EXPECTED_UNIT,
    INDIAN_SERIES_ROLES,
    INDIAN_SOURCE_URLS,
    load_indian_market_data,
)
from hedgeproof.records import DataManifest, SeriesInfo, SourceFile


def _series_info(md: MarketData) -> list[SeriesInfo]:
    out = []
    for sid, s in (("EER_EPD2DXL0_PF4_RGC_DPG", md.spot), ("EER_EPD2F_PE1_Y35NY_DPG", md.c1),
                   ("EER_EPD2F_PE2_Y35NY_DPG", md.c2), ("EER_EPD2F_PE3_Y35NY_DPG", md.c3)):
        out.append(SeriesInfo(series_id=sid, name=md.names.get(sid, sid), unit=md.units.get(sid, EXPECTED_UNIT),
                              role=SERIES_ROLES[sid], first_date=s.index[0].date().isoformat(),
                              last_date=s.index[-1].date().isoformat(), observations=int(len(s))))
    return out


def _indian_series_info(md: MarketData) -> list[SeriesInfo]:
    out = []
    mapping = (
        ("IND_DIESEL_RETAIL_INR_PER_LITRE", md.spot),
        ("MCX_CRUDE_C1_INR_PER_LITRE", md.c1),
        ("MCX_CRUDE_C2_INR_PER_LITRE", md.c2),
        ("MCX_CRUDE_C3_INR_PER_LITRE", md.c3),
    )
    for sid, s in mapping:
        out.append(SeriesInfo(series_id=sid, name=md.names.get(sid, sid), unit=md.units.get(sid, INDIAN_EXPECTED_UNIT),
                              role=INDIAN_SERIES_ROLES[sid], first_date=s.index[0].date().isoformat(),
                              last_date=s.index[-1].date().isoformat(), observations=int(len(s))))
    return out


def manifest_for(md: MarketData, settings: Settings, files: list[SourceFile], label: str, series_info: Callable[[MarketData], list[SeriesInfo]] | None = None,
                attribution: str | None = None) -> tuple[DataManifest, Any]:
    if series_info is None:
        series_info = _indian_series_info if any("INDIA" in str(md.names.get(k, "")) or "IND_" in str(k) for k in md.names) else _series_info
    table = build_period_table(md, settings.experiment)
    cont = continuity_report(md)
    sessions = md.sessions
    in_range = [s for s in sessions if s.year >= 2013]
    spot_missing = sum(1 for s in in_range if s not in md.spot.index)
    man = DataManifest(
        files=files,
        series=series_info(md),
        sessions=len(sessions),
        first_session=sessions[0].date().isoformat(),
        last_session=sessions[-1].date().isoformat(),
        spot_missing_on_sessions=spot_missing,
        continuity_flags=cont["flagged"],
        continuity_boundaries=cont["boundaries"],
        period_table_sha256=table_sha256(table),
        assumptions={"label": label, **{k: str(v) for k, v in settings.experiment["availability"].items()}},
        attribution=attribution or "Source: U.S. Energy Information Administration (EIA)",
    ).seal()
    return man, table


def ingest(settings: Settings, raw_dir: Path, retrieved_at: str, retrieved_by: str, out_dir: Path | None = None,
          scenario: str = "auto") -> dict[str, Any]:
    out_dir = out_dir or DATA_DIR
    raw_dir = Path(raw_dir)
    if scenario == "auto":
        scenario = "india" if (raw_dir / "ppac_diesel_daily.csv").exists() else "us"
    if scenario == "india":
        md = load_indian_market_data(raw_dir)
        series_info_fn = _indian_series_info
        source_urls = INDIAN_SOURCE_URLS
        source_names = list(INDIAN_SOURCE_URLS.keys())
        label = "HISTORICAL MARKET REPLAY (Indian scenario)"
        raw_rel = "data/india/raw"
    else:
        md = load_market_data(raw_dir)
        series_info_fn = _series_info
        source_urls = SOURCE_URLS
        source_names = list(SOURCE_URLS.keys())
        label = "HISTORICAL MARKET REPLAY (EIA public data)"
        raw_rel = "data/raw"
    files = []
    for name in source_names:
        url = source_urls[name]
        p = raw_dir / name
        files.append(SourceFile(path=f"{raw_rel}/{name}", source_url=url, retrieved_at=retrieved_at, retrieved_by=retrieved_by,
                                sha256=file_sha256(p), bytes=p.stat().st_size))
    _si = _indian_series_info if scenario == "india" else _series_info
    _attr = "Source: PPAC (India) and MCX (India)" if scenario == "india" else "Source: U.S. Energy Information Administration (EIA)"
    man, table = manifest_for(md, settings, files, label, series_info=_si, attribution=_attr)
    # Override series info with the scenario-specific one (manifest_for uses _series_info by default)
    man = man.model_copy(update={"series": series_info_fn(md)})
    man.seal()
    (out_dir / "derived").mkdir(parents=True, exist_ok=True)
    table.to_csv(out_dir / "derived" / "period_table.csv", index=False)
    (out_dir / "manifest.json").write_text(json.dumps(man.model_dump(mode="json"), indent=1, sort_keys=True) + "\n")
    cont = continuity_report(md)
    (out_dir / "derived" / "continuity_report.json").write_text(json.dumps(cont, indent=1, sort_keys=True) + "\n")
    counts: dict[str, int] = {}
    for r in table_records(table):
        counts[r["split"]] = counts.get(r["split"], 0) + 1
    return {"manifest": man.model_dump(mode="json"), "split_counts": counts, "continuity": cont,
            "rejected": [r for r in table_records(table) if r["status"] != "ok"]}


def load_manifest(data_dir: Path | None = None) -> dict[str, Any] | None:
    p = (data_dir or DATA_DIR) / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else None


def verify_raw_files(manifest: dict[str, Any], repo_root: Path) -> list[str]:
    """Return problems if committed raw files no longer match the manifest hashes."""
    problems = []
    for f in manifest["files"]:
        p = repo_root / f["path"]
        if not p.exists():
            problems.append(f"missing {f['path']}")
        elif file_sha256(p) != f["sha256"]:
            problems.append(f"hash mismatch {f['path']}")
    return problems
