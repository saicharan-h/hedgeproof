# Indian scenario (HedgeProof)

This document describes the **Indian scenario**, a parallel, clearly labelled
scenario that lets the same trusted engine, gate and dashboard run on
Indian-flavoured data. It is an addition to, not a replacement of, the U.S.
scenario. The U.S. scenario remains the primary, frozen experiment
(`HP-FINAL`).

## Why a separate scenario

HedgeProof's core mechanism (the Mandate-Bound Evidence Gate, G01-G12) is
source-agnostic: it checks an evidence record against a frozen policy and a
human approval. The U.S. scenario uses EIA public data and NY Harbor ULSD
futures because that is the only free, public, daily, machine-readable
spot-plus-futures dataset with a clean contract-identity story. There is no
equivalent Indian dataset, so the Indian scenario is provided as a
**second, illustrative scenario** with its own config, data folder and label.

## Honesty constraints (non-negotiable)

1. **No invented market data.** India has no liquid exchange-traded ULSD
   diesel futures contract. The Indian scenario uses MCX crude-oil futures as
   the hedge instrument and an Indian retail diesel price as the physical
   price proxy, with the basis risk between the two stated explicitly. This is
   an illustrative proxy, not a validated deployment for any Indian transit
   agency.
2. **Synthetic data is labelled.** All synthetic Indian data carries the label
   `SYNTHETIC-INDIA` and is never used for empirical claims, exactly like the
   U.S. `SYNTHETIC` data.
3. **Real Indian files, when supplied, are recorded in a manifest** exactly
   like the EIA files (SHA-256, size, source URL, who downloaded, when).
4. **No performance or savings claims** are made for the Indian scenario.

## What changed (and what did not)

| Area | U.S. scenario | Indian scenario |
|---|---|---|
| Config folder | `config/` | `config/india/` |
| Data folder | `data/` | `data/india/` |
| Label | `HISTORICAL MARKET REPLAY` | `HISTORICAL MARKET REPLAY (Indian scenario)` |
| Synthetic label | `SYNTHETIC` | `SYNTHETIC-INDIA` |
| Agency (fixture) | mid-size city bus agency | mid-size Indian city bus agency (BMTC-style) |
| Currency | USD | INR (₹) |
| Volume unit | gallons | litres |
| Physical price proxy | U.S. Gulf Coast ULSD spot (EIA) | Indian retail diesel price (PPAC) |
| Hedge instrument | NY Harbor ULSD futures (HO) | MCX crude-oil futures (proxy) |
| Contract size | 42,000 gallons | 15,000 litres |
| Forecast volume | 420,000 gal/month | 1,500,000 litres/month |
| Cash-stress cap | $250,000 | ₹2,000,000 |
| Costs (per contract) | $10 + $8.40 slippage | ₹500 + ₹16 slippage |
| Experiment id | `HP-FINAL` | `HP-INDIA` |
| Engine / gate / dashboard logic | unchanged | unchanged (source-agnostic) |

The engine, the Mandate-Bound Evidence Gate (G01-G12), the paper simulator,
the spend controller and the agent workflow are **unchanged**. Only the data
source, the labels, the units and the frozen config values differ.

## Running the Indian scenario

### Synthetic (no data files needed)

```powershell
uv run hedgeproof serve --mode test --scenario india     # terminal 1 (prints operator code)
uv run hedgeproof dashboard                              # terminal 2
```

The dashboard reads the currency and volume unit from the policy/agency, so it
displays ₹ and litres automatically.

### Real Indian files

1. Obtain the PPAC daily diesel price CSV and the MCX crude-oil bhavcopy CSV.
2. Place them in `data/india/raw/` as:
   - `ppac_diesel_daily.csv` (columns: `date`, `diesel_<city>`)
   - `mcx_crude_daily.csv` (columns: `date`, `contract`, `close` in INR/barrel)
3. Ingest:

   ```powershell
   uv run hedgeproof ingest --scenario india --retrieved-at 2026-10-24T12:30 --retrieved-by "Name"
   ```

4. Serve:

   ```powershell
   uv run hedgeproof serve --mode rehearsal --scenario india
   ```

## Data format notes

### PPAC CSV (`ppac_diesel_daily.csv`)

* One row per trading date.
* A `date` column (any common format: `YYYY-MM-DD`, `DD-MM-YYYY`, `DD/MM/YYYY`).
* A diesel price column whose name contains `diesel` and the city name
  (e.g. `diesel_delhi`). If no city-specific column is found, the first
  column containing `diesel` is used. Prices are INR per litre.

### MCX CSV (`mcx_crude_daily.csv`)

* Long form: `date`, `contract` (e.g. `C1`, `C2`, `C3`), `close` (INR per
  barrel). The loader converts INR/barrel to INR/litre using 158.987
  litres per barrel.
* Values are sorted by contract code within each date to assign Contracts 1-3.

## Files added

* `src/hedgeproof/india.py` — Indian calendar, synthetic generator, PPAC and
  MCX loaders, `load_indian_market_data`.
* `config/india/` — `policy.toml`, `experiment.toml`, `agency_fixture.toml`,
  `runtime.toml`.
* `data/india/sources/sources.json` — Indian source citations.
* `tests/test_india.py` — 33 tests (calendar, synthetic market, period table,
  manifest, config, loaders, trusted core smoke).
* `tests/test_india_service.py` — 4 HTTP boundary tests.
* `docs/INDIA_SCENARIO.md` — this document.

## Known limitations

* The Indian scenario uses MCX crude as a **proxy** for diesel; the basis
  risk between crude and Indian retail diesel is larger than the U.S.
  basis risk and is stated, not hidden.
* Indian retail prices are administered in part; the scenario does not model
  subsidy changes, tax changes or OMC pricing decisions.
* The split dates (2017-2024) are reused for comparability with the U.S.
  scenario; they are not Indian fiscal-year aligned.
* No real Indian market data is shipped; only the loaders and a labelled
  synthetic generator. Real data must be obtained and ingested by the user.