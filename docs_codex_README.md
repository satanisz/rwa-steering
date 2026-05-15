# RWA Calculator Backend

Python RWA calculator backend for the supplied synthetic Basel dataset. The project now has two runtime profiles:

- Production microservice profile with FastAPI, Pydantic, Pandas, Pandera and SciPy.
- Restricted fallback profile using only the Python standard library.

## What It Calculates

- Validates `CoreInfoRecord` and `CountryInfoRecord`-style rows from the supplied schemas.
- Loads NCCR/CRR PD mappings from `nccr_mapping.csv`.
- Calculates Basel 3.0 current IRB-style RW/RWA.
- Calculates Basel 3.1 foundation IRB RW/RWA.
- Calculates Basel 3.1 standardised RW/RWA.
- Applies a 72.5% exposure-level output floor for the final Basel 3.1 RW/RWA.
- Returns row-level validation errors instead of failing an entire batch.
- Can include audit trace steps for PD lookup, LGD/maturity selection and final risk-weight selection.

This is a working pre-production calculator for the files in this repository, not a regulatory golden source.

## Install Microservice Dependencies

```powershell
python -m pip install -r requirements.txt
```

Installed capabilities:

- `FastAPI` and `uvicorn` expose the service as an HTTP microservice.
- `Pydantic` validates JSON API contracts using `rwa_pydantic_schemas.py`.
- `Pandas` and `Pandera` validate uploaded CSV batches before calculation.
- `SciPy` supplies the normal CDF/PPF adapter used by IRB formulas.

## Run as FastAPI Microservice

```powershell
python rwa_backend.py serve-fastapi --host 127.0.0.1 --port 8000
```

OpenAPI docs:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/openapi.json`

Endpoints:

- `GET /health`
- `GET /readiness`
- `GET /reference/nccr`
- `GET /reference/manifest`
- `GET /reference/baseline`
- `GET /reference/jurisdictions/{jurisdiction_id}`
- `GET /countries`
- `POST /rwa/calculate`
- `POST /rwa/calculate/csv`

The regulatory seed package lives in [reference_data](reference_data). It contains a BCBS baseline and three initial European overlays:

- `EU_CRR3_EBA`
- `UK_PRA_BASEL_3_1`
- `CH_FINMA_BASEL_III_FINAL`

The package is deliberately marked `production_ready: false`. It is structured seed data that must be reconciled against binding legal text, local regulator rulebooks, ECAI mapping and bank-specific supervisory permissions before production use.

## Run as CLI

```powershell
python rwa_backend.py calculate `
  --core preprod_core_info_1000.csv `
  --country preprod_country_info.csv `
  --nccr nccr_mapping.csv `
  --out rwa_output.json
```

With audit trace:

```powershell
python rwa_backend.py calculate --trace --out rwa_output_with_trace.json
```

## Run Restricted HTTP Backend

```powershell
python rwa_backend.py serve --host 127.0.0.1 --port 8000
```

This fallback uses `http.server`, not FastAPI. Keep it for environments where third-party dependencies cannot be installed.

Endpoints:

- `GET /health`
- `GET /reference/nccr`
- `GET /countries`
- `POST /calculate`

Example request body:

```json
{
  "include_trace": true,
  "projection_date": "2026-12-31",
  "core_info": [
    {
      "id": "EXP000001",
      "counterparty_gid": "CP00161",
      "hsbc_intragroup_flag": "Y",
      "counterparty_fcy_internal_rating": "5.2",
      "counterparty_lcy_internal_rating": "3.3",
      "incorporation_country": "IT",
      "lgd_classification": "LGD_CORP",
      "pd_classification": "PD_CORP",
      "entity_class": "CORP",
      "sub_class": "PROJECT_FINANCE",
      "counterparty_dlgd": "0.4083",
      "govt_guarantee_flag": "Y",
      "trade_external_rating": "",
      "counterparty_external_rating": "B+",
      "avc": "1.0",
      "pra_io_mdb_3_1_flag": "N",
      "exposure_ccy": "EUR",
      "bond_or_loan_flag": "L",
      "original_maturity": "9.58",
      "residual_maturity": "5.61",
      "exposure_amount": "39041666.94",
      "expected_yield": "0.0427",
      "counterparty_credit_quality_grade": "HIGH_YIELD"
    }
  ]
}
```

## Tests

```powershell
python -m unittest discover -s tests -v
```

The test suite covers the restricted calculator, FastAPI JSON calculation, FastAPI CSV batch calculation, Pandera batch validation and SciPy-backed normal distribution reporting.
