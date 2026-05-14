# Basel III Final Reforms Application

Executive Plan and Technical Specification

Source document: `basell_2.pdf`, Basel Committee on Banking Supervision, "Basel III: Finalising post-crisis reforms", December 2017.

Prepared for: design and implementation of a Python application that calculates and reports Basel III final reform metrics using validated input and output data contracts.

Important implementation note: this specification is based on the provided PDF. Before production use, the implementation must be reconciled with the applicable local regulatory implementation and the current consolidated Basel Framework.

---

## 1. Executive Plan

### 1.1 Objective

Build a modular, auditable Python application that ingests banking exposure, capital, loss, counterparty, collateral, hedge and accounting data, validates all incoming and outgoing payloads with Pydantic, and calculates Basel III final reform outputs described in the source document:

- Standardised approach for credit risk.
- Internal ratings-based approach for credit risk.
- Minimum capital requirements for CVA risk.
- Minimum capital requirements for operational risk.
- Output floor.
- Leverage ratio.

The application must make it clear, for every reported number, which input records, assumptions, reference tables, formulas and national discretions were used.

### 1.2 Required Deliverables

The project must deliver the following items:

1. Python package named `basel3_final_reforms`.
2. Pydantic v2 data contracts for all inbound and outbound data.
3. Versioned regulatory parameter library containing all risk weights, credit conversion factors, floors, coefficients, correlations, transition dates and national discretion switches.
4. Calculation engine modules for credit risk standardised approach, credit risk IRB, CVA, operational risk, output floor and leverage ratio.
5. API layer exposing calculation endpoints and batch processing.
6. CLI for local batch runs and regression tests.
7. Result reporting layer that outputs JSON, CSV and human-readable calculation summaries.
8. Audit trail engine that explains every material classification, adjustment and calculation.
9. Test suite with unit tests, golden examples, boundary tests, validation tests and reconciliation tests.
10. Technical documentation, including this document, API contract reference, model reference and operational runbook.

### 1.3 Delivery Phases

Phase 0 - Regulatory interpretation and parameter inventory:

- Convert the PDF requirements into versioned machine-readable reference tables.
- Identify all national discretions and supervisory permissions as configuration switches.
- Define calculation scope boundaries for items referenced but not fully specified in the PDF, such as securitisation, SA-CCR, market risk, external ECAI mapping and local legal implementation.

Phase 1 - Data contracts and validation:

- Define strict Pydantic models for inbound exposure records, ratings, collateral, guarantees, derivatives, SFTs, operational loss events, financial statement items and capital measures.
- Define strict Pydantic models for outbound calculation results.
- Enforce decimal precision, currency consistency, date validity, non-negative monetary values, allowed enum values and regulatory scope validation.

Phase 2 - Calculation engine:

- Implement pure calculation modules with no API or database dependency.
- Keep classification, validation, reference lookup and arithmetic separated.
- Return detailed trace objects with each calculation.

Phase 3 - Interfaces and workflow:

- Implement REST API or service layer.
- Implement CLI batch runner.
- Implement import/export adapters for JSON and CSV.
- Add deterministic run IDs and reproducible calculation snapshots.

Phase 4 - Reporting and audit:

- Implement portfolio-level summaries, exposure-level details, exception reports and disclosure-ready extracts.
- Include rule references to source sections and PDF pages.

Phase 5 - Verification:

- Build golden datasets from examples in the source document and internally curated cases.
- Validate formulas, floors, caps, transitions, maturity adjustments, CCFs and national discretion paths.
- Add property-style tests for monotonicity and boundary behavior where applicable.

Phase 6 - Deployment:

- Package the application with pinned dependencies.
- Add CI checks, static typing, linting, security scanning and documentation build.
- Provide configuration templates for jurisdiction-specific deployments.

### 1.4 Definition of Done

The application is complete only when:

- Every accepted input payload is validated by Pydantic before calculation.
- Every output payload is validated by Pydantic before persistence or API response.
- Every regulatory lookup is versioned and traceable.
- Every capital metric includes a reproducible calculation trace.
- All modules can be tested independently.
- The output floor can combine internally modelled and standardised RWA consistently.
- The leverage ratio can be calculated independently from risk-weighted assets.
- The application can run a full portfolio batch and produce exposure-level and portfolio-level reports.

---

## 2. Application Scope

### 2.1 In Scope

The Python application must implement the following source-document sections.

#### Credit risk - standardised approach

Source: PDF pages 7-56.

The application must classify and risk-weight individual exposures including:

- Sovereigns and central banks.
- Non-central government public sector entities.
- Multilateral development banks.
- Banks under ECRA and SCRA.
- Covered bonds.
- Securities firms and other financial institutions.
- Corporates.
- Specialised lending.
- Subordinated debt, equity and other capital instruments.
- Retail exposures.
- Real estate exposures.
- Currency mismatch multiplier for certain retail and residential real estate exposures.
- Off-balance sheet items and credit conversion factors.
- Defaulted exposures.
- Other assets.
- External rating recognition and mapping rules.
- Credit risk mitigation for standardised exposures, including collateral, netting, guarantees and credit derivatives.

#### Credit risk - IRB approach

Source: PDF pages 57-112.

The application must support:

- IRB exposure categorisation.
- Foundation IRB and advanced IRB eligibility restrictions.
- Corporate and bank risk-weight functions.
- SME firm-size adjustment.
- Specialised lending slotting.
- HVCRE formula and slotting.
- PD, LGD, EAD and maturity inputs and floors.
- Retail residential mortgage, QRRE and other retail formulas.
- Purchased receivables default and dilution risk.
- Expected loss and provision comparison.
- Minimum requirement status flags and validation evidence.

#### CVA risk

Source: PDF pages 113-131.

The application must support:

- Materiality threshold option for banks with aggregate non-centrally cleared derivative notional up to EUR 100bn.
- BA-CVA reduced version.
- BA-CVA full version with eligible hedge recognition.
- SA-CVA input validation and capital aggregation structure.
- CVA hedging eligibility.
- CVA risk weights, correlations, buckets and multipliers as versioned reference data.

#### Operational risk

Source: PDF pages 132-140.

The application must calculate:

- Business Indicator (BI).
- Business Indicator Component (BIC).
- Internal Loss Multiplier (ILM).
- Operational Risk Capital (ORC).
- Operational risk RWA equal to 12.5 times ORC.
- Loss data quality eligibility.
- Bucket treatment and national discretion options.

#### Output floor

Source: PDF pages 141-143.

The application must calculate:

- Pre-floor RWA.
- Standardised-only RWA.
- Applicable output floor calibration by date.
- Floored RWA.
- Optional transitional cap of 25% increase over pre-floor RWA where supervisor permits.
- Capital ratios with and without the floor.

#### Leverage ratio

Source: PDF pages 144-162.

The application must calculate:

- Tier 1 capital numerator.
- Leverage ratio exposure measure denominator.
- On-balance sheet exposures.
- Derivative exposures.
- Securities financing transaction exposures.
- Off-balance sheet exposure equivalents.
- G-SIB leverage ratio buffer.
- Leverage ratio minimum and distribution constraint indicators.

### 2.2 Out of Scope Unless Added Later

The PDF refers to several external frameworks. The first application release must not silently implement partial versions of them. Instead, it must create integration boundaries:

- SA-CCR detailed derivative exposure engine.
- Securitisation framework.
- Market risk framework.
- Central counterparty exposure framework.
- Equity investments in funds framework.
- Local ECAI recognition and mapping databases.
- Jurisdiction-specific legal netting enforceability opinions.

For these items, the application must either:

- Receive validated external results as input, or
- Use an explicitly implemented adapter with its own specification and tests.

---

## 3. Target Architecture

### 3.1 Package Layout

The recommended package structure is:

```text
basel3_final_reforms/
  __init__.py
  api/
    app.py
    dependencies.py
    routers/
      credit_standardised.py
      credit_irb.py
      cva.py
      operational_risk.py
      output_floor.py
      leverage_ratio.py
      portfolio.py
  cli/
    main.py
    commands/
      calculate.py
      validate.py
      explain.py
      export_reference_data.py
  config/
    settings.py
    jurisdiction.py
    feature_flags.py
  core/
    decimal_math.py
    normal_distribution.py
    money.py
    dates.py
    errors.py
    audit.py
  schemas/
    common.py
    reference_data.py
    credit_standardised.py
    credit_irb.py
    cva.py
    operational_risk.py
    output_floor.py
    leverage_ratio.py
    portfolio.py
    results.py
  reference_data/
    loader.py
    repository.py
    versions/
      basel_iii_final_reforms_2017/
        credit_standardised.yaml
        credit_irb.yaml
        cva.yaml
        operational_risk.yaml
        output_floor.yaml
        leverage_ratio.yaml
  engines/
    credit_standardised/
      classifier.py
      risk_weights.py
      crm.py
      off_balance_sheet.py
      defaulted.py
      calculator.py
    credit_irb/
      classifier.py
      formulas.py
      slotting.py
      risk_components.py
      expected_loss.py
      calculator.py
    cva/
      materiality.py
      ba_cva.py
      sa_cva.py
      hedges.py
      calculator.py
    operational_risk/
      business_indicator.py
      loss_component.py
      calculator.py
    output_floor/
      calculator.py
    leverage_ratio/
      on_balance_sheet.py
      derivatives.py
      sfts.py
      off_balance_sheet.py
      calculator.py
    portfolio/
      aggregation.py
      reconciliation.py
      calculator.py
  reporting/
    json_report.py
    csv_export.py
    disclosure.py
    explain.py
  persistence/
    models.py
    repositories.py
  tests/
    unit/
    golden/
    integration/
    fixtures/
```

### 3.2 Separation Principles

Each module must have a single responsibility:

- `schemas`: Pydantic validation only. No regulatory arithmetic.
- `reference_data`: load and validate versioned tables.
- `classifier`: determine exposure class and regulatory treatment.
- `risk_weights`: map classified exposure and attributes to risk weight.
- `calculator`: orchestrate calculation inside a risk type.
- `portfolio`: aggregate risk-type outputs.
- `reporting`: format already validated results.
- `api`: transport layer only.

Calculation functions must be deterministic and side-effect free. Persistence, logging and API response formatting must occur outside the calculation engine.

### 3.3 Numeric Precision

Use `Decimal` for all monetary amounts, percentages and regulatory factors.

Rules:

- Store percentages internally as decimals, e.g. 20% as `Decimal("0.20")`.
- Monetary values must include currency.
- Do not use binary floating point for regulatory arithmetic.
- Quantization must occur only at configured output boundaries, never inside intermediate calculations unless required by policy.
- Normal CDF and inverse normal CDF are required for IRB formulas. Use a tested scientific library adapter or a validated implementation behind `core.normal_distribution`.

---

## 4. Core Data Model

### 4.1 Common Enums

The application must define enums for:

- `CurrencyCode`.
- `JurisdictionCode`.
- `ExposureClass`.
- `ApproachType`.
- `RatingScaleBucket`.
- `ExternalRating`.
- `CreditQuality`.
- `CounterpartySector`.
- `CollateralType`.
- `GuaranteeType`.
- `CreditDerivativeType`.
- `RealEstateType`.
- `RepaymentDependency`.
- `SFTTransactionType`.
- `DerivativeProductType`.
- `OperationalLossEventType`.
- `CapitalMeasureType`.

Enums must be stable and serializable. Regulatory labels from the PDF should be mapped into internal enum values, not embedded as free text in calculations.

### 4.2 Base Pydantic Rules

All request and domain models must use:

```python
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class StrictBaselModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        use_enum_values=False,
    )
```

Required validation patterns:

- IDs must be non-empty strings.
- Monetary values must be non-negative unless explicitly allowed.
- Percentages must be bounded by regulatory logic, normally `0 <= x <= 1`, unless risk weights above 100% are allowed.
- Dates must be ISO dates.
- Currency-dependent calculations must reject mixed currencies unless a permitted FX conversion or currency mismatch haircut is explicitly supplied.
- A calculation request must include a `regulatory_reference_version`.

### 4.3 Money Model

```python
class Money(StrictBaselModel):
    amount: Decimal = Field(ge=Decimal("0"))
    currency: str = Field(min_length=3, max_length=3)
```

For aggregation, all amounts must be converted to a reporting currency through a validated FX rate table. The FX conversion module must add audit trace lines and must never silently convert.

### 4.4 Audit Trace Model

Every result must include a machine-readable trace:

```python
class RuleReference(StrictBaselModel):
    source_document: str
    section: str
    pdf_page: int | None = None
    paragraph: str | None = None
    table: str | None = None


class CalculationTraceStep(StrictBaselModel):
    step_id: str
    description: str
    input_values: dict[str, str]
    formula: str | None = None
    output_values: dict[str, str]
    rule_reference: RuleReference | None = None
```

The trace must allow a reviewer to reproduce the path from raw exposure to final capital metric.

---

## 5. Reference Data Requirements

### 5.1 Versioning

Reference data must be stored in versioned YAML or JSON files. Each file must include:

- `version_id`.
- `source_document`.
- `effective_from`.
- `effective_to`.
- `tables`.
- `national_discretion_flags`.
- `validation_hash`.

Example:

```yaml
version_id: basel_iii_final_reforms_2017
source_document: Basel III Finalising post-crisis reforms, December 2017
effective_from: 2022-01-01
tables:
  sovereign_external_rating_risk_weights:
    source_pdf_page: 8
    source_table: Table 1
    values:
      AAA_TO_AA_MINUS: "0.00"
      A_PLUS_TO_A_MINUS: "0.20"
      BBB_PLUS_TO_BBB_MINUS: "0.50"
      BB_PLUS_TO_B_MINUS: "1.00"
      BELOW_B_MINUS: "1.50"
      UNRATED: "1.00"
```

### 5.2 Mandatory Parameter Tables

The reference data repository must include at least:

Credit standardised:

- Sovereign external rating risk weights.
- Sovereign ECA score risk weights.
- PSE option 1 and option 2 risk weights.
- MDB risk weights.
- Bank ECRA risk weights and short-term risk weights.
- Bank SCRA grade risk weights and short-term risk weights.
- Covered bond rated and unrated risk weights.
- Corporate external rating risk weights.
- Corporate unrated, investment grade and SME risk weights.
- Specialised lending unrated risk weights.
- Equity and subordinated debt risk weights.
- Retail risk weights.
- Residential real estate LTV bucket risk weights.
- Commercial real estate LTV bucket risk weights.
- ADC risk weights.
- Currency mismatch multiplier.
- Off-balance sheet CCFs.
- Defaulted exposure risk weights.
- Other asset risk weights.
- CRM haircuts, haircut floors and currency mismatch haircuts.

IRB:

- Corporate/bank PD floors.
- Retail PD floors.
- LGD floors by exposure and collateral type.
- Supervisory LGD values.
- Supervisory CCFs for foundation EAD.
- Specialised lending UL and EL slotting risk weights.
- HVCRE UL and EL slotting risk weights.
- Maturity floors and caps.
- SME sales thresholds and firm-size adjustment limits.

CVA:

- BA-CVA correlation parameter rho.
- BA-CVA alpha.
- BA-CVA beta.
- BA-CVA sector and credit quality risk weights.
- BA-CVA hedge correlation values.
- SA-CVA multiplier.
- SA-CVA risk buckets, risk weights and correlations.
- Materiality threshold of EUR 100bn.

Operational risk:

- BI component definitions.
- BIC buckets and marginal coefficients.
- ILM exponent.
- Loss Component multiplier.
- Loss inclusion threshold.
- ORC to RWA multiplier.

Output floor:

- Phase-in calibration schedule.
- Final floor calibration.
- Transitional cap.

Leverage ratio:

- Minimum leverage ratio.
- G-SIB leverage buffer multiplier.
- OBS CCFs.
- Derivative replacement cost formula settings.
- PFE multiplier fixed at one.
- SFT netting criteria parameters.

---

## 6. Credit Risk - Standardised Approach

### 6.1 Required Inputs

The standardised credit risk engine must accept:

- Exposure ID.
- Legal entity ID.
- Counterparty ID.
- Exposure amount net of specific provisions where required.
- Exposure class candidate.
- Product type.
- On-balance or off-balance sheet indicator.
- Maturity information.
- Currency of exposure and funding.
- External ratings and rating provider.
- Internal due diligence override result.
- Jurisdiction flags for external rating use and national discretions.
- Collateral data.
- Guarantee and credit derivative data.
- Real estate property value and lien information.
- Default status and provisions.

### 6.2 Processing Workflow

The standardised engine must execute these steps:

1. Validate input payload.
2. Classify exposure into one regulatory exposure class.
3. Determine whether external ratings may be used.
4. Apply due diligence override when risk characteristics imply a higher risk bucket.
5. Calculate exposure amount or credit equivalent amount.
6. Apply credit risk mitigation where permitted.
7. Determine risk weight.
8. Apply floors, caps and multipliers.
9. Calculate RWA as exposure amount times risk weight.
10. Return validated exposure-level result and trace.

### 6.3 Sovereigns and Central Banks

Source: PDF pages 8-9.

The application must implement:

- External rating risk weights:
  - AAA to AA-: 0%.
  - A+ to A-: 20%.
  - BBB+ to BBB-: 50%.
  - BB+ to B-: 100%.
  - Below B-: 150%.
  - Unrated: 100%.
- ECA score risk weights:
  - 0 to 1: 0%.
  - 2: 20%.
  - 3: 50%.
  - 4 to 6: 100%.
  - 7: 150%.
- Zero risk weight eligibility for named supranational entities listed in the PDF, including BIS, IMF, ECB, EU, ESM and EFSF.
- National discretion for domestic currency sovereign exposures funded in domestic currency.

Validation:

- If both external rating and ECA score are supplied, configuration must specify the permitted hierarchy.
- Domestic currency preferential treatment must require `exposure_currency == sovereign_domestic_currency` and corresponding domestic currency funding evidence.

### 6.4 Public Sector Entities

Source: PDF pages 9-10.

The application must support two national-discretion options:

- Option 1 based on sovereign external rating:
  - AAA to AA-: 20%.
  - A+ to A-: 50%.
  - BBB+ to BBB-: 100%.
  - BB+ to B-: 100%.
  - Below B-: 150%.
  - Unrated: 100%.
- Option 2 based on PSE external rating:
  - AAA to AA-: 20%.
  - A+ to A-: 50%.
  - BBB+ to BBB-: 50%.
  - BB+ to B-: 100%.
  - Below B-: 150%.
  - Unrated: 50%.

The module must also support treatment of certain domestic PSEs as sovereign exposures where configured.

### 6.5 Multilateral Development Banks

Source: PDF pages 10-11.

The application must support:

- 0% risk weight for MDBs meeting eligibility criteria and listed in configuration.
- For other MDBs in jurisdictions allowing external ratings:
  - AAA to AA-: 20%.
  - A+ to A-: 30%.
  - BBB+ to BBB-: 50%.
  - BB+ to B-: 100%.
  - Below B-: 150%.
  - Unrated: 50%.
- 50% risk weight for other MDBs where external ratings are not allowed.

### 6.6 Bank Exposures

Source: PDF pages 11-14.

The application must implement ECRA and SCRA.

ECRA applies where external ratings are permitted and the bank exposure is rated:

- AAA to AA-: base 20%, short-term 20%.
- A+ to A-: base 30%, short-term 20%.
- BBB+ to BBB-: base 50%, short-term 20%.
- BB+ to B-: base 100%, short-term 50%.
- Below B-: base 150%, short-term 150%.

SCRA applies where external ratings are not permitted, or to unrated bank exposures:

- Grade A: base 40%, short-term 20%.
- Grade B: base 75%, short-term 50%.
- Grade C: base 150%, short-term 150%.

Additional SCRA Grade A concession:

- Unrated bank exposures may receive 30% if the counterparty bank has CET1 ratio at least 14% and Tier 1 leverage ratio at least 5%, subject to all other conditions in the reference data.

The module must validate:

- Whether original maturity qualifies as short-term.
- Whether trade-related bank exposure with original maturity up to six months qualifies for short-term treatment.
- Whether implicit government support is excluded from ratings unless permitted during transition.
- Whether sovereign floor applies for transfer and convertibility risk under SCRA.

### 6.7 Covered Bonds

Source: PDF pages 14-16.

The application must validate covered bond eligibility:

- Issuer is a bank or mortgage institution subject to special public supervision.
- Cover pool contains permitted asset types.
- Residential real estate cover assets meet criteria and LTV no higher than 80%.
- Commercial real estate cover assets meet criteria and LTV no higher than 60%.
- Bank claims in the cover pool qualifying for 30% or lower risk weight do not exceed the applicable limit.
- Nominal cover pool value exceeds nominal outstanding covered bonds by at least 10%.
- Required portfolio disclosures are available at least semi-annually.

Rated covered bonds:

- AAA to AA-: 10%.
- A+ to A-: 20%.
- BBB+ to BBB-: 20%.
- BB+ to B-: 50%.
- Below B-: 100%.

Unrated covered bonds by issuer bank risk weight:

- Issuer 20% -> covered bond 10%.
- Issuer 30% -> 15%.
- Issuer 40% -> 20%.
- Issuer 50% -> 25%.
- Issuer 75% -> 35%.
- Issuer 100% -> 50%.
- Issuer 150% -> 100%.

### 6.8 Securities Firms and Other Financial Institutions

Source: PDF page 16.

The application must classify these exposures:

- Treat as bank exposures only if the entity is subject to prudential standards and supervision equivalent to banks.
- Otherwise treat as corporate exposures.

This must be a configurable jurisdiction-level determination, not free-text user choice.

### 6.9 Corporates

Source: PDF pages 16-18.

Where external ratings are allowed:

- AAA to AA-: 20%.
- A+ to A-: 50%.
- BBB+ to BBB-: 75%.
- BB+ to BB-: 100%.
- Below BB-: 150%.
- Unrated: 100%, except qualifying SME treatment.

Where external ratings are not allowed:

- General corporate default risk weight: 100%.
- Investment grade corporate: 65%, if the definition is satisfied and securities are outstanding on a recognised securities exchange.
- Corporate SME: 85% if reported annual sales for the consolidated group are no more than EUR 50m.

The module must include a due diligence adjustment that can only increase, never decrease, the risk weight implied by external rating.

### 6.10 Specialised Lending

Source: PDF pages 18-19.

The application must classify:

- Project finance.
- Object finance.
- Commodities finance.

If issue-specific external rating exists and ratings are allowed, use the corporate external rating table. Issuer ratings must not be used.

If no issue-specific rating is available:

- Object finance: 100%.
- Commodities finance: 100%.
- Project finance during operational phase: 100%.
- Project finance before operational phase: 130%.
- High-quality project finance in operational phase: 80%, when all required eligibility criteria are satisfied.

The eligibility validator for high-quality project finance must check reserve funds, creditor protections, revenue structure, main counterparty quality, pledged assets and creditor control rights.

### 6.11 Subordinated Debt, Equity and Other Capital Instruments

Source: PDF pages 19-21.

The application must implement:

- Speculative unlisted equity: 400%.
- Other equity holdings: 250%.
- Certain legislated programme equity holdings: 100%, subject to national discretion and aggregate cap of 10% of combined Tier 1 and Tier 2 capital.
- Subordinated debt and capital instruments other than equities: 150%.

The equity classifier must use economic substance, not only legal form.

### 6.12 Retail Exposures

Source: PDF pages 21-22.

The application must identify regulatory retail exposures using:

- Borrower is individual or qualifying regulatory retail SME.
- Exposure is one of a large pool of similarly managed exposures.
- Product orientation and granularity requirements are satisfied.
- Aggregated exposure to one counterparty or connected counterparties does not exceed EUR 1m, where applicable.

Risk weights:

- Regulatory retail transactor: 45%.
- Other regulatory retail: 75%.
- Other retail exposure to individual not meeting all regulatory retail criteria: 100%.
- SME not meeting retail criteria: corporate treatment.

### 6.13 Real Estate Exposures

Source: PDF pages 22-28.

The application must calculate LTV:

```text
LTV = loan_amount / property_value
```

The property value must be measured prudently and must not be adjusted upward after origination unless permitted by the standard. All liens with equal or higher ranking must be considered when determining LTV bucket and risk weight.

Residential real estate where repayment is not materially dependent on property cash flows:

- LTV <= 50%: 20%.
- 50% < LTV <= 60%: 25%.
- 60% < LTV <= 80%: 30%.
- 80% < LTV <= 90%: 40%.
- 90% < LTV <= 100%: 50%.
- LTV > 100%: 70%.

Alternative loan-splitting approach, if jurisdiction permits:

- Apply 20% to the part of exposure up to 55% of property value.
- Apply counterparty risk weight to residual exposure.

Residential real estate where repayment is materially dependent on property cash flows:

- LTV <= 50%: 30%.
- 50% < LTV <= 60%: 35%.
- 60% < LTV <= 80%: 45%.
- 80% < LTV <= 90%: 60%.
- 90% < LTV <= 100%: 75%.
- LTV > 100%: 105%.

Commercial real estate where repayment is not materially dependent on property cash flows:

- LTV <= 60%: min(60%, counterparty risk weight).
- LTV > 60%: counterparty risk weight.

Alternative loan-splitting approach, if jurisdiction permits:

- Apply min(60%, counterparty risk weight) to the part of exposure up to 55% of property value.
- Apply counterparty risk weight to the residual exposure.

Commercial real estate where repayment is materially dependent on property cash flows:

- LTV <= 60%: 70%.
- 60% < LTV <= 80%: 90%.
- LTV > 80%: 110%.

ADC exposures:

- Land acquisition, development and construction exposures: 150%.
- Qualifying residential ADC may receive 100% if the conditions specified by the framework and jurisdiction are met.

The real estate module must validate:

- Finished property status or enforceable completion criteria where relevant.
- Legal enforceability of mortgage claim.
- Property valuation source and date.
- Lien seniority and pari passu ranking.
- Repayment dependency on property cash flows.

### 6.14 Currency Mismatch Multiplier

Source: PDF page 29.

For unhedged retail and residential real estate exposures to individuals where lending currency differs from the borrower's income currency:

- Apply 1.5 multiplier to the applicable risk weight.
- Cap the resulting risk weight at 150%.

The application must determine whether the exposure is hedged through natural or financial hedge evidence. Hedge evidence must be explicit input.

### 6.15 Off-Balance Sheet Items

Source: PDF pages 29-31.

The application must convert undrawn or notional amounts using credit conversion factors:

- 100% CCF for direct credit substitutes, certain transaction commitments, forward asset purchases, forward forward deposits, partly paid shares and securities, and other specified items.
- 50% CCF for note issuance facilities and revolving underwriting facilities.
- 50% CCF for certain transaction-related contingent items.
- 40% CCF for commitments unless lower CCF applies.
- 20% CCF for issuing and confirming banks of short-term self-liquidating trade letters of credit arising from movement of goods.
- 10% CCF for unconditionally cancellable commitments.

Where there is an undertaking to provide a commitment on an off-balance sheet item, use the lower of the two applicable CCFs.

### 6.16 Defaulted Exposures

Source: PDF pages 31-32.

The application must implement defaulted exposure handling:

- Default definition must align to the regulatory default definition.
- Unsecured portion of defaulted exposure:
  - 150% risk weight when specific provisions are less than 20% of the outstanding amount.
  - 100% risk weight when specific provisions are at least 20% of the outstanding amount.
- Defaulted residential real estate exposures not materially dependent on property cash flows: 100%.
- Supervisory discretion may reduce risk weight to 50% where provisions are at least 50%, if configured.

### 6.17 Other Assets

Source: PDF page 32.

The application must implement:

- Standard other assets: 100%.
- Cash owned and held at bank or in transit: 0%.
- Gold bullion held in own vaults or allocated basis backed by bullion liabilities: 0%.
- Cash items in process of collection: 20%.

### 6.18 Credit Risk Mitigation

Source: PDF pages 37-56.

The CRM module must support:

- Collateralised transactions.
- Simple approach.
- Comprehensive approach.
- On-balance sheet netting.
- Guarantees.
- Credit derivatives.
- Maturity mismatches.
- Currency mismatches.
- SFT haircut floors.

Key rules:

- CRM must not increase capital requirement.
- CRM effects must not be double-counted.
- Legal enforceability evidence is required.
- Maturity mismatch adjustment:

```text
Pa = P * (t - 0.25) / (T - 0.25)
```

Where:

- `Pa` is adjusted credit protection.
- `P` is credit protection amount adjusted for haircuts.
- `t` is minimum of protection residual maturity and T, floored by the standard.
- `T` is minimum of exposure residual maturity and 5 years.

Guarantee currency mismatch:

```text
GA = G * (1 - HFX)
```

Where HFX is 8% for 10-business-day holding period with daily mark-to-market, scaled by square root of time where required.

The CRM output must separately show:

- Gross exposure.
- Eligible collateral/protection.
- Haircut-adjusted exposure.
- Covered portion.
- Uncovered portion.
- Risk weight of protection provider.
- Final RWA.

---

## 7. Credit Risk - IRB Approach

### 7.1 Required Inputs

The IRB engine must accept:

- Exposure ID and counterparty ID.
- IRB asset class and sub-class.
- Supervisor-approved approach.
- PD.
- LGD.
- EAD.
- Effective maturity M.
- Default status.
- Best estimate of expected loss for defaulted exposures.
- Borrower sales and total assets for SME adjustment.
- Financial institution indicator and total assets.
- Collateral and guarantee data.
- Slotting category for specialised lending where applicable.
- Provision data.

### 7.2 IRB Eligibility and Approach Restrictions

Source: PDF pages 57-65.

The application must enforce:

- IRB categories: corporate, sovereign, bank, retail, equity.
- Corporate specialised lending sub-classes: PF, OF, CF, IPRE, HVCRE.
- Retail sub-classes: residential mortgage, QRRE, other retail.
- Equity exposures are not permitted under IRB and must use standardised approach.
- Advanced IRB is not permitted for:
  - General corporates belonging to a group with total consolidated annual revenues greater than EUR 500m.
  - Bank asset class exposures.
  - Securities firms and other financial institutions treated as bank or financial corporate exposures.
- Retail has no foundation approach: banks provide PD, LGD and EAD.

### 7.3 Corporate and Bank Formula

Source: PDF pages 66-68.

For non-defaulted corporate and bank exposures:

```text
R = 0.12 * (1 - exp(-50 * PD)) / (1 - exp(-50))
    + 0.24 * (1 - (1 - exp(-50 * PD)) / (1 - exp(-50)))

b = (0.11852 - 0.05478 * ln(PD)) ^ 2

K = [LGD * N((G(PD) + sqrt(R) * G(0.999)) / sqrt(1 - R)) - PD * LGD]
    * [(1 + (M - 2.5) * b) / (1 - 1.5 * b)]

RWA = 12.5 * K * EAD
```

Where:

- `N` is the standard normal cumulative distribution function.
- `G` is the inverse standard normal cumulative distribution function.
- PD and LGD are decimals.
- EAD is monetary amount.

For defaulted exposures:

```text
K = max(0, LGD - best_estimate_expected_loss)
RWA = 12.5 * K * EAD
```

Financial institution correlation multiplier:

- Apply multiplier 1.25 to correlation parameter R for qualifying regulated financial institutions with total assets at least USD 100bn and for unregulated financial institutions regardless of size.

### 7.4 SME Firm-Size Adjustment

Source: PDF page 68.

For corporate SME borrowers with consolidated group sales less than EUR 50m:

```text
S = min(max(annual_sales_millions_eur, 5), 50)
firm_size_adjustment = 0.04 * (1 - (S - 5) / 45)
R_adjusted = R - firm_size_adjustment
```

If allowed by national discretion, total assets may substitute for sales where sales are not meaningful.

### 7.5 Specialised Lending Slotting

Source: PDF pages 68-69.

For PF, OF, CF and IPRE where PD estimation requirements are not met:

- Strong: 70%.
- Good: 90%.
- Satisfactory: 115%.
- Weak: 250%.
- Default: 0%.

Preferential treatment where national discretion allows and maturity or underwriting quality conditions are met:

- Strong: 50%.
- Good: 70%.

For HVCRE:

- Strong: 95%.
- Good: 120%.
- Satisfactory: 140%.
- Weak: 250%.
- Default: 0%.

Preferential HVCRE treatment where allowed:

- Strong: 70%.
- Good: 95%.

For HVCRE formula approach, use:

```text
R = 0.12 * (1 - exp(-50 * PD)) / (1 - exp(-50))
    + 0.30 * (1 - (1 - exp(-50 * PD)) / (1 - exp(-50)))
```

### 7.6 IRB Risk Component Rules

Source: PDF pages 69-78.

PD:

- Corporate and bank exposure PD must be one-year PD.
- Defaulted borrowers have PD = 100%.
- Minimum PD for corporate and bank exposures: 0.05%.

Foundation LGD:

- Senior unsecured claims on banks, securities firms and financial institutions: 45%.
- Senior unsecured claims on other corporates: 40%.
- Subordinated claims on corporates and banks: 75%.

Foundation collateral recognition:

- Eligible financial collateral: LGDS = 0%, haircut per comprehensive approach.
- Eligible receivables: LGDS = 20%, haircut 40%.
- Eligible residential/commercial real estate: LGDS = 20%, haircut 40%.
- Other eligible physical collateral: LGDS = 25%, haircut 40%.
- Ineligible collateral: haircut 100%.

Collateralised LGD:

```text
LGD* = LGDU * (EU / (E * (1 + HE))) + LGDS * (ES / (E * (1 + HE)))
```

Where `ES` is capped at `E * (1 + HE)` and `EU = E * (1 + HE) - ES`.

EAD:

- On-balance sheet EAD is gross of provisions and partial write-offs.
- Foundation off-balance sheet EAD uses standardised approach CCFs.
- Advanced EAD may use own estimates where permitted, but floor equals on-balance sheet amount plus 50% of the off-balance sheet exposure calculated using applicable standardised CCF.

Effective maturity:

- Foundation corporate default M = 2.5 years, except repo-style transactions M = 0.5 years unless supervisor requires calculation.
- Advanced IRB must calculate M.
- M floor = 1 year and cap = 5 years unless specified short-term exceptions apply.
- For determined cash flows:

```text
M = sum(t * CF_t) / sum(CF_t)
```

### 7.7 Retail IRB Formulas

Source: PDF pages 78-80.

Residential mortgage:

```text
R = 0.15
K = LGD * N((G(PD) + sqrt(R) * G(0.999)) / sqrt(1 - R)) - PD * LGD
RWA = 12.5 * K * EAD
```

QRRE:

```text
R = 0.04
K = LGD * N((G(PD) + sqrt(R) * G(0.999)) / sqrt(1 - R)) - PD * LGD
RWA = 12.5 * K * EAD
```

Other retail:

```text
R = 0.03 * (1 - exp(-35 * PD)) / (1 - exp(-35))
    + 0.16 * (1 - (1 - exp(-35 * PD)) / (1 - exp(-35)))

K = LGD * N((G(PD) + sqrt(R) * G(0.999)) / sqrt(1 - R)) - PD * LGD
RWA = 12.5 * K * EAD
```

Retail PD floors:

- QRRE revolvers: 0.10%.
- All other retail: 0.05%.

Retail LGD floors:

- Mortgages secured: 5%.
- QRRE unsecured: 50%.
- Other retail unsecured: 30%.
- Other retail secured:
  - Financial collateral: 0%.
  - Receivables: 10%.
  - Commercial or residential real estate: 10%.
  - Other physical collateral: 15%.

### 7.8 Purchased Receivables

Source: PDF pages 81-84.

The application must support:

- Purchased retail receivables using retail IRB standards.
- Purchased corporate receivables using bottom-up or top-down procedure where eligible.
- Default risk calculation.
- Dilution risk calculation.

Dilution risk:

```text
PD = estimated one-year EL for dilution risk
LGD = 100%
Use corporate risk-weight function
```

Where dilution is monitored and resolved within one year, supervisor may allow one-year maturity.

### 7.9 Expected Loss and Provisions

Source: PDF pages 84-86.

Expected loss:

- Non-defaulted corporate, bank and retail exposures:

```text
EL = PD * LGD
EL_amount = EL * EAD
```

- Defaulted exposures:
  - Advanced: use best estimate of expected loss.
  - Foundation: use supervisory LGD.

Specialised lending EL slotting risk weights:

- Non-HVCRE:
  - Strong: 5%.
  - Good: 10%.
  - Satisfactory: 35%.
  - Weak: 100%.
  - Default: 625%.
- HVCRE:
  - Strong: 5%.
  - Good: 5%.
  - Satisfactory: 35%.
  - Weak: 100%.
  - Default: 625%.

Provision treatment:

- Calculate total eligible provisions.
- Compare total eligible provisions to total EL amount.
- Return surplus or shortfall for capital treatment outside this module.

---

## 8. CVA Risk Module

### 8.1 Required Inputs

The CVA module must accept:

- Covered transaction portfolio.
- Counterparty data.
- Netting set data.
- EAD by netting set.
- Effective maturity by netting set.
- IMM usage flag.
- Counterparty sector.
- Counterparty credit quality.
- CVA hedge inventory.
- Derivative notional totals for materiality threshold.
- SA-CVA sensitivities by risk factor, bucket and risk type.
- Supervisor approval flags for SA-CVA.

### 8.2 Approach Selection

Source: PDF page 113.

Selection logic:

1. If aggregate notional amount of non-centrally cleared derivatives <= EUR 100bn and the bank elects the materiality option, CVA capital may equal 100% of CCR capital requirement. Hedges are not recognised.
2. Else if supervisor has approved SA-CVA and input sensitivities are supplied, SA-CVA may be used.
3. Otherwise BA-CVA must be used.
4. If SA-CVA carve-outs exist, carved-out netting sets must be calculated under BA-CVA and combined consistently.

### 8.3 BA-CVA Reduced Version

Source: PDF pages 114-116.

Reduced BA-CVA:

```text
K_reduced = sqrt((rho * sum_c SCVA_c)^2 + (1 - rho^2) * sum_c SCVA_c^2)
rho = 0.50
```

Stand-alone CVA capital:

```text
SCVA_c = (1 / alpha) * RW_c * sum_NS(M_NS * EAD_NS * DF_NS)
alpha = 1.4
```

Discount factor:

- `DF_NS = 1` for IMM banks.
- For non-IMM:

```text
DF_NS = (1 - exp(-0.05 * M_NS)) / (0.05 * M_NS)
```

Risk weights by sector and credit quality must be loaded from reference data. Mandatory sector groups include:

- Sovereigns including central banks and MDBs.
- Local government, government-backed non-financials, education and public administration.
- Financials including government-backed financials.
- Basic materials, energy, industrials, agriculture, manufacturing, mining and quarrying.
- Consumer goods and services, transportation and storage, administrative and support service activities.
- Technology and telecommunications.
- Health care, utilities, professional and technical activities.
- Other sector.

### 8.4 BA-CVA Full Version

Source: PDF pages 116-118.

Full BA-CVA recognises eligible hedges:

```text
K_full = beta * K_reduced + (1 - beta) * K_hedged
beta = 0.25
```

The module must calculate:

- `SNH_c` for single-name hedges.
- `IH` for index hedges.
- `HMA_c` for hedge misalignment.
- `K_hedged`.

Eligible hedges:

- Single-name CDS.
- Single-name contingent CDS.
- Index CDS.

Single-name hedge correlation:

- Direct reference to counterparty: 100%.
- Legal relation with counterparty: 80%.
- Same sector and region: 50%.

### 8.5 SA-CVA

Source: PDF pages 118-131.

SA-CVA eligibility requires:

- Monthly CVA and CVA sensitivity calculation capability.
- Dedicated CVA desk or equivalent function.
- Exposure model meeting regulatory CVA requirements.
- Supervisor approval.

SA-CVA capital:

- Sum delta capital requirements across:
  - Interest rate.
  - Foreign exchange.
  - Counterparty credit spread.
  - Reference credit spread.
  - Equity.
  - Commodity.
- Sum vega capital requirements across:
  - Interest rate.
  - Foreign exchange.
  - Reference credit spread.
  - Equity.
  - Commodity.

Sensitivity processing:

```text
WS_k_CVA = RW_k * s_k_CVA
WS_k_Hdg = RW_k * s_k_Hdg
WS_k = WS_k_CVA + WS_k_Hdg
```

Within-bucket aggregation:

```text
K_b = sqrt(sum_k WS_k^2 + sum_{k != l} rho_kl * WS_k * WS_l + R * sum_k (WS_k_Hdg)^2)
R = 0.01
```

Across-bucket aggregation:

```text
K_risk_type = m_CVA * sqrt(sum_b K_b^2 + sum_{b != c} gamma_bc * K_b * K_c)
m_CVA = 1.25 unless supervisor sets higher value
```

The SA-CVA module must not hard-code risk weights and correlations. They must be loaded by risk type, bucket and regulatory version.

---

## 9. Operational Risk Module

### 9.1 Required Inputs

The operational risk module must accept:

- Three years of financial statement data for BI components.
- Ten years of annual operational risk loss data, or validated shorter transition period.
- Bucket and jurisdiction settings.
- Loss data quality flag.
- Loss exclusions approved by supervisor.
- Divested activity exclusions approved by supervisor.
- M&A inclusion data.

### 9.2 Business Indicator

Source: PDF page 132.

The Business Indicator is:

```text
BI = ILDC + SC + FC
```

Interest, leases and dividend component:

```text
ILDC = min(abs(interest_income - interest_expense),
           0.0225 * interest_earning_assets)
       + dividend_income
```

Services component:

```text
SC = max(other_operating_income, other_operating_expense)
     + max(fee_income, fee_expense)
```

Financial component:

```text
FC = abs(net_p_and_l_trading_book)
     + abs(net_p_and_l_banking_book)
```

The overbar in the source formula means a three-year average. The application must calculate absolute values year by year first, then average.

### 9.3 Business Indicator Component

Source: PDF page 133.

Marginal coefficients:

- Bucket 1, BI <= EUR 1bn: 12%.
- Bucket 2, EUR 1bn < BI <= EUR 30bn: 15%.
- Bucket 3, BI > EUR 30bn: 18%.

Calculation is marginal, not a flat rate:

```text
BIC = 12% * min(BI, 1bn)
    + 15% * min(max(BI - 1bn, 0), 29bn)
    + 18% * max(BI - 30bn, 0)
```

### 9.4 Internal Loss Multiplier

Source: PDF pages 133-134.

Loss Component:

```text
LC = 15 * average_annual_operational_risk_losses
```

Internal Loss Multiplier:

```text
ILM = ln(exp(1) - 1 + (LC / BIC) ^ 0.8)
```

Operational Risk Capital:

```text
ORC = BIC * ILM
```

Operational risk RWA:

```text
Operational_RWA = 12.5 * ORC
```

Special cases:

- Bucket 1 banks normally have ILM = 1.
- Supervisors may allow loss data inclusion for Bucket 1.
- Supervisors may set ILM = 1 for all banks in a jurisdiction.
- If loss data standards are not met, capital must be at least 100% of BIC and supervisor may require ILM > 1.

### 9.5 Loss Data Rules

Source: PDF pages 134-137.

The application must validate:

- Observation period is ten years, or at least five years during transition where permitted.
- Minimum loss event threshold is EUR 20,000 unless national discretion increases it to EUR 100,000 for Bucket 2 and 3.
- Loss data includes gross loss amount, recoveries, accounting date, discovery date where available, occurrence date where available and narrative drivers.
- Recoveries reduce losses only after payment is received.
- Operational losses related to credit risk and already included in credit RWA are excluded.
- Operational losses related to credit risk but not included in credit RWA are included.
- Operational risk losses related to market risk are included.
- Exclusions require supervisory approval and disclosure.

---

## 10. Output Floor Module

### 10.1 Required Inputs

The output floor module must accept:

- Calculation date.
- Pre-floor RWA by risk type and asset class.
- Standardised-only RWA by risk type and asset class.
- Capital amounts: CET1, Tier 1, Total Capital.
- Capital buffers where available.
- Transitional cap flag and supervisor permission.

### 10.2 Formula

Source: PDF pages 141-143.

Applicable RWA:

```text
floor_amount = floor_percentage * standardised_total_rwa
floored_rwa_before_cap = max(pre_floor_total_rwa, floor_amount)
```

Phase-in calibration:

- 1 Jan 2022: 50%.
- 1 Jan 2023: 55%.
- 1 Jan 2024: 60%.
- 1 Jan 2025: 65%.
- 1 Jan 2026: 70%.
- 1 Jan 2027 onward: 72.5%.

Optional transitional cap:

```text
capped_rwa = min(floored_rwa_before_cap, pre_floor_total_rwa * 1.25)
```

Apply cap only where configured as national discretion.

Capital ratios:

```text
CET1_ratio = CET1 / applicable_rwa
Tier1_ratio = Tier1 / applicable_rwa
Total_capital_ratio = Total_capital / applicable_rwa
```

The module must return ratios both excluding and including the output floor.

---

## 11. Leverage Ratio Module

### 11.1 Required Inputs

The leverage ratio module must accept:

- Tier 1 capital.
- On-balance sheet assets.
- Derivative transactions and netting sets.
- Cash variation margin data.
- SFT transactions and qualifying master netting agreement data.
- OBS items and undrawn commitments.
- Specific and general provisions reducing Tier 1 capital.
- G-SIB indicator and higher-loss absorbency requirement.
- Central bank reserve exemption flag where jurisdiction permits.

### 11.2 Ratio and Minimum

Source: PDF pages 144-146.

Formula:

```text
Leverage_ratio = Tier1_capital / exposure_measure
```

Minimum:

- 3% at all times.

G-SIB leverage ratio buffer:

```text
leverage_buffer = 50% * G-SIB_higher_loss_absorbency_requirement
```

Example:

- If G-SIB higher loss absorbency requirement is 2%, leverage ratio buffer is 1%.

### 11.3 Exposure Measure

Source: PDF pages 147-158.

Total leverage exposure measure:

```text
Exposure_measure =
    on_balance_sheet_exposures
  + derivative_exposures
  + SFT_exposures
  + OBS_equivalent_exposures
```

General rules:

- Use gross accounting values unless specified otherwise.
- Do not reduce by physical or financial collateral, guarantees or CRM unless the leverage ratio framework explicitly permits.
- Do not net assets and liabilities unless explicitly permitted.
- Items deducted from Tier 1 capital may be deducted from exposure measure where specified.
- Liability items must not be deducted.

### 11.4 On-Balance Sheet Exposures

The application must include all balance sheet assets except on-balance sheet derivative and SFT assets handled in their dedicated modules.

On-balance sheet non-derivative assets:

```text
included_amount = accounting_value - associated_specific_provisions - eligible_general_provisions
```

Unsettled trades and cash pooling require dedicated validators for the conditions listed in the source document.

### 11.5 Derivative Exposures

Source: PDF pages 149-155 and annex pages 159-160.

Derivative exposure amount:

```text
derivative_exposure = replacement_cost + potential_future_exposure
```

Replacement cost:

```text
RC = max(V - CVM_received + CVM_provided, 0)
```

Potential future exposure:

```text
PFE = multiplier * AddOn
```

For leverage ratio purposes:

- Multiplier is fixed at 1.
- Written options must be included even where risk-based framework allows zero EAD.
- Bilateral netting requires legal enforceability and no walkaway clause.
- Cash variation margin recognition requires all regulatory conditions to be satisfied.
- Written credit derivatives require additional effective notional treatment.

### 11.6 Securities Financing Transactions

Source: PDF pages 155-157 and annex pages 160-161.

For bank acting as principal, include:

1. Gross SFT assets adjusted by permitted accounting netting of cash payables and receivables.
2. Counterparty credit risk current exposure.

With qualifying master netting agreement:

```text
E_star = max(0, sum(E_i) - sum(C_i))
```

Without qualifying master netting agreement:

```text
E_i_star = max(0, E_i - C_i)
```

The module must separately handle:

- Sale accounting transactions.
- Bank acting as agent.
- Indemnities and guarantees.
- Netting between banking book and trading book positions only where conditions are met.

### 11.7 Off-Balance Sheet Items

Source: PDF pages 157-162.

OBS exposure equivalent:

```text
OBS_equivalent = committed_undrawn_amount * CCF
```

Then deduct eligible specific and general provisions that reduced Tier 1 capital, but the result cannot be less than zero.

CCFs:

- 100% for direct credit substitutes, forward asset purchases, forward forward deposits, partly paid shares/securities and specified unsettled financial asset purchases.
- 50% for NIFs and RUFs.
- 50% for transaction-related contingent items.
- 40% for commitments unless lower CCF applies.
- 20% for short-term self-liquidating trade letters of credit.
- 10% for unconditionally cancellable commitments.

---

## 12. API Design

### 12.1 Required Endpoints

The API should expose:

```text
POST /v1/credit-risk/standardised/calculate
POST /v1/credit-risk/irb/calculate
POST /v1/cva/calculate
POST /v1/operational-risk/calculate
POST /v1/output-floor/calculate
POST /v1/leverage-ratio/calculate
POST /v1/portfolio/calculate
POST /v1/validate
GET  /v1/reference-data/{version_id}
GET  /v1/runs/{run_id}
GET  /v1/runs/{run_id}/explain
```

### 12.2 API Response Pattern

All calculation responses must contain:

```json
{
  "run_id": "string",
  "status": "SUCCESS",
  "regulatory_reference_version": "basel_iii_final_reforms_2017",
  "calculation_date": "2026-05-13",
  "reporting_currency": "EUR",
  "results": {},
  "validation_warnings": [],
  "audit_trace": []
}
```

Errors must be structured:

```json
{
  "status": "FAILED_VALIDATION",
  "errors": [
    {
      "field": "exposures[0].pd",
      "code": "PD_BELOW_FLOOR",
      "message": "PD is below the regulatory floor for the selected IRB exposure class.",
      "rule_reference": {
        "source_document": "basell_2.pdf",
        "section": "IRB risk components",
        "pdf_page": 69,
        "paragraph": "68"
      }
    }
  ]
}
```

---

## 13. Output Models

### 13.1 Exposure Result

```python
class ExposureCapitalResult(StrictBaselModel):
    exposure_id: str
    exposure_class: str
    approach: str
    exposure_amount: Money
    ead: Money | None = None
    risk_weight: Decimal | None = None
    capital_requirement: Money | None = None
    rwa: Money
    expected_loss: Money | None = None
    warnings: list[str] = []
    trace: list[CalculationTraceStep]
```

### 13.2 Portfolio Result

```python
class PortfolioCapitalResult(StrictBaselModel):
    run_id: str
    calculation_date: date
    reporting_currency: str
    credit_rwa_standardised: Money
    credit_rwa_irb: Money | None = None
    cva_rwa: Money
    operational_rwa: Money
    market_rwa: Money | None = None
    securitisation_rwa: Money | None = None
    pre_floor_rwa: Money
    standardised_rwa: Money
    output_floor_amount: Money
    applicable_rwa: Money
    cet1_ratio: Decimal
    tier1_ratio: Decimal
    total_capital_ratio: Decimal
    leverage_ratio: Decimal | None = None
    trace: list[CalculationTraceStep]
```

---

## 14. Persistence and Audit

The application must persist:

- Raw request payload.
- Normalized validated input.
- Reference data version and hash.
- Calculation outputs.
- Trace steps.
- Warnings and overrides.
- User or system identity that initiated the run.
- Timestamp and application version.

The system must support reproducibility:

- Re-running the same payload with the same reference data version must produce the same result.
- Changes to reference data must create a new version.
- Manual overrides must require reason, approver and timestamp.

---

## 15. Testing Strategy

### 15.1 Unit Tests

Required unit test areas:

- Pydantic validation boundaries.
- Rating bucket lookup.
- LTV bucket lookup.
- CCF lookup.
- CRM haircut calculations.
- IRB corporate formula.
- IRB SME adjustment.
- Retail IRB formulas.
- Operational BI, BIC, ILM and ORC.
- BA-CVA reduced and full formulas.
- Output floor phase-in.
- Leverage ratio exposure aggregation.

### 15.2 Golden Tests

Golden tests must include:

- Output floor example from PDF page 142:
  - Pre-floor RWA = 76.
  - Standardised RWA = 140.
  - 72.5% of standardised RWA = 101.5.
  - Applicable RWA = 101.5 before transitional cap.
- Operational risk BIC example from PDF page 133:
  - BI = EUR 35bn.
  - BIC = EUR 5.37bn.
- Residential mortgage split example from PDF page 25:
  - Loan EUR 70,000.
  - Property EUR 100,000.
  - 20% risk weight on EUR 55,000.
  - 75% risk weight on residual EUR 15,000.
  - RWA EUR 22,250.

### 15.3 Validation Tests

The system must reject:

- Negative monetary amounts unless explicitly allowed.
- Unknown rating labels.
- PD below floor unless auto-flooring policy is explicitly enabled and traced.
- LGD below floor unless auto-flooring policy is explicitly enabled and traced.
- Real estate exposure missing property value.
- CRM claim without legal enforceability flag.
- SA-CVA request without supervisor approval flag.
- Operational risk request with insufficient loss data and no permitted fallback.
- Output floor request missing standardised RWA.
- Leverage ratio request with netted assets and liabilities where not permitted.

### 15.4 Reconciliation Tests

The application must provide reconciliation reports comparing:

- Sum of exposure-level RWA to portfolio-level RWA.
- Pre-floor RWA to floored RWA.
- Standardised RWA used in output floor to standardised module output.
- Operational ORC to operational RWA.
- Leverage exposure components to total exposure measure.

---

## 16. Security and Operational Requirements

### 16.1 Security

- Validate all inbound payloads.
- Do not execute formulas from input data.
- Treat reference data as controlled configuration.
- Protect audit logs from modification.
- Apply role-based access for override approval.
- Avoid storing secrets in configuration files.

### 16.2 Observability

The service must emit:

- Calculation run started/completed events.
- Validation failure metrics.
- Calculation duration by module.
- Record counts by exposure class.
- Warning counts by warning code.
- Reference data version used.

### 16.3 Performance

The engine should support:

- Exposure-level vectorization where possible.
- Batch processing in chunks.
- Deterministic parallel aggregation.
- Streaming CSV ingestion for large portfolios.

The initial performance target should be configurable, but a practical acceptance target is:

- 100,000 standardised credit exposures processed in a batch run without exhausting memory.
- Portfolio aggregation completed in deterministic order.

---

## 17. Key Implementation Decisions

### 17.1 Pydantic Everywhere at Boundaries

Pydantic must be used at:

- API request boundary.
- CLI input boundary.
- Reference data load boundary.
- Internal normalized domain model boundary.
- Output response boundary.

Internal pure calculation functions may receive already validated dataclasses or Pydantic models, but final output must be Pydantic-validated.

### 17.2 Configuration of National Discretions

National discretions must never be hidden in code. They must be explicit configuration, for example:

```yaml
jurisdiction: EU
allow_external_ratings: true
pse_treatment_option: OPTION_1
allow_domestic_sovereign_preferential_rw: true
allow_real_estate_loan_splitting: true
apply_output_floor_transitional_cap: false
operational_risk_ilm_for_all_banks: CALCULATED
```

### 17.3 Explainability as a Product Feature

Every material result must explain:

- Exposure classification.
- Parameter table lookup.
- Formula used.
- Floors, caps and overrides.
- National discretion path.
- Final RWA or ratio.

This is mandatory for supervisory review and internal model governance.

---

## 18. Alignment With Supplied RWA Schemas

The supplied project files `input_schemas.py`, `output_schemas.py` and `nccr_mapping.csv` change the implementation plan in one important way: the first delivery should include a concrete migration layer from the current dataframe-oriented schemas into production-grade Pydantic contracts.

### 18.1 Current Schema Assessment

The supplied Python schema files are not dataclasses and are not yet production Pydantic API contracts:

- `input_schemas.py` defines `pandera.DataFrameModel` classes for `CoreInfo` and `CountryInfo`.
- `output_schemas.py` defines `pandera.DataFrameModel` classes for tabular RWA outputs and uses `BaseSettings` for response-like structures.
- `nccr_mapping.csv` provides a more realistic NCCR/CRR grade mapping than the placeholder rating lists in `input_schemas.py`.

This means the production architecture should keep two separate validation layers:

- Pydantic models for API, CLI, service and record-level validation.
- Optional Pandera models for dataframe and CSV batch validation after records have already passed Pydantic normalization.

### 18.2 Required Schema Migration Changes

The implementation must replace placeholder schema assumptions with strict, versioned contracts:

- Replace placeholder `InternalRating = [1.0, 2.0]` with the full NCCR grade set derived from `nccr_mapping.csv`.
- Treat internal grades such as `0.1`, `1.1` and `8.3` as categorical strings, not floats.
- Replace placeholder external ratings `AAA` and `BBB` with the full external rating scale needed by Basel calculations.
- Replace generic enum placeholders such as `ENT_1`, `SUB_1`, `GRADE_1` with business-readable enums or controlled code fields.
- Use `Decimal` for PD, DLGD, risk weights, RWA, yield, maturity and exposure amounts.
- Do not use `BaseSettings` for ordinary API response models. Use `BaseModel`; reserve settings models for environment/configuration.
- Make `exposure_amount` mandatory in production calculation requests, even if staging files allow null values.
- Enforce maturity logic: residual maturity cannot exceed original maturity.
- Enforce AVC logic: bank and financial institution records must use the configured AVC multiplier path.
- Validate output records before persistence or export.

### 18.3 Concrete Initial Contract

The initial implementation should include a module equivalent to `rwa_pydantic_schemas.py` with these record contracts:

- `CoreInfoRecord`.
- `CountryInfoRecord`.
- `OutputSuccessRecord`.
- `OutputProjectionRecord`.
- `RwaError`.
- `OutputErrorResponse`.
- `OutputSummary`.
- `RequestedFx`.

These models are intentionally record-level. Batch loaders should parse CSV rows into these Pydantic models first, then convert to DataFrame only after validation succeeds.

### 18.4 Pre-Production Data Requirement

The pre-production dataset must:

- Contain at least 1,000 synthetic `CoreInfoRecord` rows.
- Be deterministic and reproducible by seed.
- Use the NCCR/CRR grades from `nccr_mapping.csv`.
- Include varied entity classes, countries, currencies, maturities, ratings, AVC values and exposure sizes.
- Include a small companion country reference CSV for `CountryInfoRecord`.
- Be clearly labelled as synthetic, not production or regulatory golden output.
- Pass Pydantic validation before being accepted into any non-production environment.

---

## 19. Open Items for Business and Regulatory Confirmation

Before implementation starts, the owner must confirm:

1. Target jurisdiction and local implementation rules.
2. Reporting currency.
3. Whether external ratings may be used.
4. Source systems for exposure, collateral, rating, loss and capital data.
5. Required interfaces: API only, CLI only, batch files or database integration.
6. Whether SA-CCR, securitisation and market risk should be implemented or accepted as external validated inputs.
7. Whether SA-CVA approval is assumed or BA-CVA is the default.
8. Operational risk loss data availability and quality.
9. Required disclosure/reporting templates.
10. Required audit retention period.

---

## 20. Summary of What Must Be Delivered

The deliverable is not only a calculator. It is a validated, modular and auditable Basel III final reforms calculation platform.

At minimum, the delivered system must include:

- Clean Python package with separated modules.
- Pydantic models for all inputs and outputs.
- Versioned regulatory reference data.
- Standardised credit risk calculation.
- IRB calculation with formulas, floors and eligibility restrictions.
- CVA calculation with BA-CVA and SA-CVA structure.
- Operational risk calculation.
- Output floor calculation.
- Leverage ratio calculation.
- Portfolio aggregation.
- API and/or CLI execution.
- Detailed audit traces.
- Test suite with golden examples.
- Technical and operational documentation.
