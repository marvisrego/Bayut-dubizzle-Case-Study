# Exact inventory deduplication and embedding audit

Generated from both sheets of Cars_data.xlsx by scripts/prepare_inventory.py.
The original workbook and original text fields are unchanged.

## Summary

- Rows before deduplication: 200
- Exact duplicate groups found: 8
- Rows merged: 11
- Final canonical rows: 189
- Remaining duplicate fingerprints: 0
- Embedding text rows created: 189
- Rows with URL/contact patterns in embedding text: 0
- Distinct candidate blocks retained for review: 10
- Source photo variations logged: 10

Fingerprint inputs are normalized year, make, model, trim, title, and description.
The fingerprint excludes photo URL, sheet, source row, and canonical ID.
Candidate blocks use year + make + model only; different fingerprints stay separate.
Embedding text removes contact, link, address, social, and dealer boilerplate
patterns. It is separate from the preserved source and clean descriptions.

## Exact merges

| Canonical ID | Primary source | Merged source | Fingerprint |
| --- | --- | --- | --- |
| CAR_0005 | raw:6 | raw:97 | fde4e9d80c7f9ef0 |
| CAR_0007 | raw:8 | raw:40 | 8c06711330846bb2 |
| CAR_0007 | raw:8 | raw:41 | 8c06711330846bb2 |
| CAR_0007 | raw:8 | raw:42 | 8c06711330846bb2 |
| CAR_0007 | raw:8 | raw:77 | 8c06711330846bb2 |
| CAR_0013 | raw:14 | raw:63 | 2ef7c49937208733 |
| CAR_0040 | raw:44 | raw:84 | ba31160f2f9fe052 |
| CAR_0058 | cleaned:60 | raw:62 | fed6aba41d3c962d |
| CAR_0064 | raw:69 | raw:70 | f22715fddddaf943 |
| CAR_0070 | raw:76 | raw:82 | 363dda1fa3643bf2 |
| CAR_0073 | raw:80 | raw:96 | c99e3ddb7742c661 |

## Candidate blocks kept separate

| Year | Make | Model | Canonical IDs |
| ---: | --- | --- | --- |
| 2012 | Ford | Explorer | ["CAR_0088", "CAR_0145"] |
| 2017 | Mercedes-Benz | C-Class | ["CAR_0061", "CAR_0095"] |
| 2019 | Mercedes-Benz | C-Class | ["CAR_0033", "CAR_0092", "CAR_0161"] |
| 2020 | Mercedes-Benz | C-Class | ["CAR_0104", "CAR_0123"] |
| 2021 | Dodge | Challenger | ["CAR_0021", "CAR_0154"] |
| 2022 | BMW | M4 | ["CAR_0023", "CAR_0026"] |
| 2022 | Bentley | Bentayga | ["CAR_0068", "CAR_0099"] |
| 2022 | Lincoln | Aviator | ["CAR_0116", "CAR_0160"] |
| 2023 | Nissan | Sunny | ["CAR_0017", "CAR_0039"] |
| 2024 | Ford | Territory | ["CAR_0003", "CAR_0044"] |

## Photo variations within exact groups

Photos did not affect matching. Full source rows remain in the Excel merge log.

| Canonical ID | Field | Resolution |
| --- | --- | --- |
| CAR_0005 | photo_url | Primary photo retained; secondary photo preserved in merge log. Photos were not used for deduplication. |
| CAR_0007 | photo_url | Primary photo retained; secondary photo preserved in merge log. Photos were not used for deduplication. |
| CAR_0007 | photo_url | Primary photo retained; secondary photo preserved in merge log. Photos were not used for deduplication. |
| CAR_0007 | photo_url | Primary photo retained; secondary photo preserved in merge log. Photos were not used for deduplication. |
| CAR_0007 | photo_url | Primary photo retained; secondary photo preserved in merge log. Photos were not used for deduplication. |
| CAR_0013 | photo_url | Primary photo retained; secondary photo preserved in merge log. Photos were not used for deduplication. |
| CAR_0040 | photo_url | Primary photo retained; secondary photo preserved in merge log. Photos were not used for deduplication. |
| CAR_0064 | photo_url | Primary photo retained; secondary photo preserved in merge log. Photos were not used for deduplication. |
| CAR_0070 | photo_url | Primary photo retained; secondary photo preserved in merge log. Photos were not used for deduplication. |
| CAR_0073 | photo_url | Primary photo retained; secondary photo preserved in merge log. Photos were not used for deduplication. |
