# Strategy 3 BIS CBPOL provenance

## Acquisition and retention

The source is the official BIS bulk archive
`https://data.bis.org/static/bulk/WS_CBPOL_csv_col.zip`, downloaded on
2026-09-11. The downloaded 284,035-byte archive SHA-256 is
`eef383071fe15fa2efdf9235f0123dde77cb2b2b3e56219e6a8d97d4572658cc`.
Its sole member was `WS_CBPOL_csv_col.csv`. The raw archive was used only in a
temporary acquisition location and is not retained. The retained research
extract is `strategy3_data/bis_cbpol_2013_2017.csv`: 14,608 daily records
dated only 2013-01-01 through 2017-12-31. The accompanying machine-readable
source metadata is `strategy3_data/bis_cbpol_provenance.json`.

## Exact mapping and definitions in the retained period

| Currency | BIS daily `REF_AREA` | BIS source | Definition applicable to 2013--17 |
| --- | --- | --- | --- |
| USD | US | US Federal Reserve System | midpoint of the Fed target range |
| EUR | XM | European Central Bank | main refinancing operations fixed rate |
| GBP | GB | Bank of England | official Bank Rate |
| JPY | JP | Bank of Japan | no policy rate from 2013-04-04 through 2016-09-20; -0.1% short-term policy rate from 2016-09-21 |
| AUD | AU | Reserve Bank of Australia | cash-rate target |
| NZD | NZ | Reserve Bank of New Zealand | official cash rate |
| CAD | CA | Bank of Canada | overnight-rate target (midpoint of operating band) |
| CHF | CH | Swiss National Bank | midpoint of SNB target range |

All mappings are daily CBPOL rows; neither monthly rows nor a secondary
provider is used. Blank JP observations remain blank in the retained CSV and
are not forward-filled across the gap. This makes a carry-confirmed signal
ineligible whenever its selected pair needs JPY during the gap. Historical
definition transitions before 2013 (such as Canada's 1994 change) were not
backfilled or used to alter the retained series. The EUR 2024 steering-rate
change and CHF 2019 SNB policy-rate change are outside the retained period and
are not present in research inputs.
