# RWA Regulatory Reference Data Seed

This folder contains a seed reference-data package for Basel III final reforms.

It is intentionally split into:

- `bcbs/` - global BCBS baseline tables.
- `jurisdictions/` - jurisdiction overlays.
- `manifest.json` - package manifest.

The three initial European overlays are:

- `EU_CRR3_EBA` - EU/EEA CRR3 and CRD6 implementation.
- `UK_PRA_BASEL_3_1` - United Kingdom PRA Basel 3.1 implementation.
- `CH_FINMA_BASEL_III_FINAL` - Swiss FINMA / Capital Adequacy Ordinance implementation.

These three were selected because they are major European banking regimes and can diverge materially in application dates, transition calendars, national discretions, reporting templates and local overlays.

Important: this package is not marked production-ready. It is a structured implementation seed. Before production use, each overlay must be reconciled against the applicable binding legal text, local regulator rulebook, ECAI mapping and bank-specific supervisory permissions.
