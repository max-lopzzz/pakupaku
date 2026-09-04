# Food data sources — licence & attribution register

This is the definitive register of every national / regional food-composition
dataset used by the offline multi-country averaged food database
(`scripts/build_food_db/`, spec:
`docs/superpowers/specs/2026-09-03-multi-country-food-database-design.md`).

**Inclusion rule.** A source is included only if its licence permits, without a
separate paid or per-request permission:

1. **redistribution** (we ship the aggregated values inside `data/foods.sqlite`
   in a public repo), **and**
2. **commercial use** (PakuPaku has a paid membership tier), **and**
3. attribution on terms we can meet (a credit line in this file and in the
   in-app "Food data sources" surface).

Any dataset that is CC BY-NC / BY-NC-SA / BY-NC-ND, "research or educational use
only", "no redistribution", or "commercial use by permission / fee" is
**rejected** — even though we could afford the fee, the point is a clean,
redistributable artifact with no per-source negotiation.

The aggregated output is a **median/mean of numeric nutrient values across ≥ 2
sources**, not a reproduction of any single table. Attribution is still carried
for every non-public-domain source below.

Legend for `included`:

- `yes` — licence verified to allow redistribution + commercial use + attribution.
- `no — <reason>` — rejected; no extractor is written, `sources/<id>.py` is not wired into `ALL_SOURCES`.

---

## Included sources (`ALL_SOURCES` for Task 4)

### `usda` — USDA FoodData Central

| field | value |
|---|---|
| **included** | yes |
| **dataset** | FoodData Central — Foundation Foods, SR Legacy, and FNDDS (Food and Nutrient Database for Dietary Studies). "Full Download of All Data Types" CSV release. |
| **edition / year** | Full Download of All Data Types, **2026-04-30** release (CSV). This single release already bundles Foundation, SR Legacy, Branded, and Survey/FNDDS data (including household-measure portions), so no separate FNDDS download is needed. |
| **download URL** | https://fdc.nal.usda.gov/download-datasets/ — "Full Download of All Data Types" → CSV. |
| **licence** | Public domain — U.S. Government work, **CC0 1.0 Universal**. https://fdc.nal.usda.gov/faq/ ("USDA FoodData Central data are in the public domain … no copyright"), CC0: https://creativecommons.org/publicdomain/zero/1.0/ |
| **required attribution** | None legally required. USDA *requests* the credit line: `U.S. Department of Agriculture, Agricultural Research Service. FoodData Central, 2025. fdc.nal.usda.gov.` — carried in this file and in-app anyway. |
| **file format** | Multi-file CSV release (ZIP). Sub-files used: `food.csv`, `food_nutrient.csv`, `nutrient.csv`, `food_portion.csv`. FNDDS release used only for household-measure portions. |

### `cofid` — UK CoFID (McCance & Widdowson's *The Composition of Foods*)

| field | value |
|---|---|
| **included** | yes |
| **dataset** | McCance and Widdowson's *The Composition of Foods* Integrated Dataset (CoFID) |
| **edition / year** | CoFID **2021** (published 19 March 2021; PHE gateway GW-2010) — latest edition. |
| **download URL** | https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid — "McCance and Widdowson's The Composition of Foods Integrated Dataset 2021" (Excel, ~4.4 MB) + "old foods" legacy Excel. |
| **licence** | **Open Government Licence v3.0** (OGL v3). https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/ — permits copying, publishing, distributing, adapting, and **commercial exploitation**, with attribution. |
| **required attribution** | OGL v3 attribution statement: `Contains public sector information licensed under the Open Government Licence v3.0.` Plus source credit: `McCance and Widdowson's The Composition of Foods Integrated Dataset 2021. © Crown copyright 2021. Public Health England / Department of Health and Social Care.` |
| **file format** | xlsx (single workbook, multiple sheets) + separate "old foods" xlsx. |

### `ciqual` — France CIQUAL (ANSES)

| field | value |
|---|---|
| **included** | yes |
| **dataset** | Table de composition nutritionnelle des aliments Ciqual (ANSES-CIQUAL) |
| **edition / year** | **Ciqual 2025** (ANSES-CIQUAL table, published 2025-11-19; 3 484 foods, 74 constituents). |
| **download URL** | ciqual.anses.fr itself refused every connection attempt during the build (TLS reset on both `curl` and a browser fetch — looks like a network-level block rather than an access-control page), so the build pulled the same official dataset from its mirror on Recherche Data Gouv instead: https://entrepot.recherche.data.gouv.fr/dataset.xhtml?persistentId=doi:10.57745/RDMHWY (DOI `10.57745/RDMHWY`), file `Table Ciqual 2025_FR_2025_11_03.xlsx`. Etalab 2.0 licence confirmed on that record. |
| **licence** | **Licence Ouverte / Open Licence 2.0** (Etalab 2.0). https://github.com/etalab/licence-ouverte/blob/master/LO.md — permits reuse, redistribution, and **commercial use**, with attribution. Confirmed on the data.gouv.fr dataset page ("Licence Ouverte / Open Licence 2.0"). |
| **required attribution** | `Source : Table de composition nutritionnelle des aliments Ciqual 2025, ANSES (Agence nationale de sécurité sanitaire de l'alimentation, de l'environnement et du travail).` Etalab 2.0 requires naming the source and the date of the last update. |
| **file format** | xls / xlsx (single table) + XML export. |

### `afcd` — Australian Food Composition Database (FSANZ)

| field | value |
|---|---|
| **included** | yes |
| **dataset** | Australian Food Composition Database (AFCD), Food Standards Australia New Zealand |
| **edition / year** | **Release 3** (published 2025-12; the version live on the FSANZ data-files page at build time — Release 2 is superseded). |
| **download URL** | https://www.foodstandards.gov.au/science-data/food-nutrient-databases/afcd/data-files — "Release 3" downloadable files (Excel: Food Details, Nutrient profiles). About/licence: https://www.foodstandards.gov.au/science-data/monitoringnutrients/afcd/datauserlicenceagreement |
| **licence** | **Creative Commons Attribution–ShareAlike 3.0 Australia (CC BY-SA 3.0 AU)**, per the FSANZ Data User Licence Agreement. https://creativecommons.org/licenses/by-sa/3.0/au/ — grants "worldwide, royalty-free, non-exclusive, perpetual" rights to reproduce, adapt, and distribute, **including commercial use**. Two obligations: (a) **ShareAlike** — derivative works distributed under the same licence; (b) the **Limitation of Data Statement** must accompany any distribution. |
| **required attribution** | `Source: Food Standards Australia New Zealand (FSANZ), Australian Food Composition Database, Release 2. Licensed under CC BY-SA 3.0 AU.` — plus the FSANZ Limitation of Data Statement (food composition values are averages; nutrient content varies between batches and brands) reproduced in the in-app credits / docs. |
| **file format** | xlsx (release files: food details, per-100g nutrients, and measures). |
| **note** | ShareAlike applies to *this dataset's* contribution. `data/foods.sqlite` mixes many sources; carry the CC BY-SA 3.0 AU notice on the artifact and in `docs/food-data-sources.md` to satisfy it. |

### `cnf` — Canadian Nutrient File (Health Canada)

| field | value |
|---|---|
| **included** | yes |
| **dataset** | Canadian Nutrient File (CNF) — compilation of Canadian food composition data |
| **edition / year** | **CNF 2026** (the "Canadian Nutrient File, 2026" open.canada.ca dataset — a full-file CSV release, not the older 2015 dataset's update-only delta files). |
| **download URL** | https://open.canada.ca/data/en/dataset/1b6139bd-ed7e-4043-bc28-ff00e10f3109 — `food_name.csv`, `nutrient_name.csv`, `nutrient_amount.csv` (plus other relational files not used here). |
| **licence** | **Open Government Licence – Canada**. https://open.canada.ca/en/open-government-licence-canada — permits copying, modification, publication, translation, and **commercial exploitation**, with attribution. |
| **required attribution** | `Contains information licensed under the Open Government Licence – Canada.` Plus source credit: `Canadian Nutrient File, Health Canada, 2026.` |
| **file format** | Multi-file relational release. Principal files: `FOOD NAME.csv`, `NUTRIENT AMOUNT.csv`, `NUTRIENT NAME.csv`, `CONVERSION FACTOR.csv`, `MEASURE NAME.csv` (names per the 2015 database-structure guide; confirm exact filenames on download). |

### `frida` — Frida, Danish Food Composition Database (DTU)

| field | value |
|---|---|
| **included** | yes |
| **dataset** | Frida Food Data — the Danish Food Composition Database, National Food Institute, Technical University of Denmark (DTU) |
| **edition / year** | **Frida / FCDB version 6.1**, published via DTU's institutional data repository (data.dtu.dk), DOI `10.11583/DTU.32312844`, dataset title "The Danish Food Composition Database, version 6.1". |
| **download URL** | The in-app "Download dataset" menu item on frida.fooddata.dk resolves to the DOI above (`window.open`, confirmed by instrumenting the page's JS) rather than serving a file directly; the actual file lives on data.dtu.dk (a Figshare-based repository) as `FCDB_6.1_Dataset.xlsx`, resolved via the Figshare API (`api.figshare.com/v2/articles/32312844`) and downloaded from `ndownloader.figshare.com/files/65016537`. |
| **licence** | Free reuse with source acknowledgement. Frida terms (disclaimer / conditions of use): "Data and texts on https://frida.fooddata.dk may not be copied or otherwise reproduced without clear acknowledgement of source. By any use of data from frida.fooddata.dk you must credit upon each display or use of data." No non-commercial restriction and no bar on redistribution *with* attribution — so redistribution + commercial use are permitted. https://frida.fooddata.dk/disclaimer?lang=en |
| **required attribution** | `© Frida Food Data (https://frida.fooddata.dk), version 6.1. National Food Institute, Technical University of Denmark.` Must appear on each display/use of the data (in-app credits surface + this file). |
| **file format** | xlsx (single downloadable spreadsheet, multiple sheets). |
| **note** | Frida publishes no formal open-data licence, only the conditions-of-use text above. It grants reproduction-with-attribution and imposes no NC clause, which clears our inclusion rule. If a stricter reading is ever needed, treat as `licence unclear, needs legal review` — but the plain text permits it. |

---

## Built artifact (2026-09-04)

`data/foods.sqlite`: **2,481 generic foods**, zero branded data, every food
backed by ≥2 independent national sources agreeing on at least one nutrient.
Per-source contribution counts (a food counts once per source that fed at
least one of its nutrient values):

| source | foods contributed to |
|---|---|
| `usda` | 2,076 |
| `cnf` | 2,099 |
| `cofid` | 508 |
| `afcd` | 368 |
| `frida` | 457 |
| `ciqual` | 28 |

**Coverage is far below the ~15k+ hoped for in the design spec, and heavily
skewed toward English-language sources.** The matcher groups foods by
fuzzy-matching their (English) names — it does no translation — so USDA/CNF
(US/Canadian English) and, to a lesser extent, CoFID/AFCD (UK/Australian
English) and Frida (Danish source, but with an English `FoodName` column)
cluster together reasonably well, while CIQUAL (French names only) almost
never textually matches anything from the other five sources and so almost
never clears the ≥2-source bar — hence only 28 of 2,481 foods have any
CIQUAL contribution at all, out of CIQUAL's own 3,484-row table. This is a
direct, measured consequence of the build's design (recorded as a known
limitation, not fixed here — see
`docs/superpowers/plans/2026-09-03-food-db-runtime-cutover.md`'s Known
limitations section for the two related matching-quality issues this also
surfaced, one fixed and one deferred). A real fix needs either per-language
name translation before matching, or per-language canonical-key normalisation
tables — both are build-methodology changes, not a bug fix.

Sanity check (`scripts/build_food_db` Task 9 Step 5): `impossible-kcal: 0`,
`single-source: 0`, `no-portions: 153` (~6%, plausible for a build without
translated/matched portion names for the non-USDA sources). Rebuild
determinism (Task 9 Step 6) verified: an immediate re-run from the same
`raw/` + `review/decisions.csv` produces a byte-identical artifact.

---

## Pending sources — resolved

All four were resolved by reading the licence terms on **2026-09-03**. **All four are excluded** — every one is non-commercial-only or commercial-by-fee. North America + Europe + Oceania coverage (the six included sources above) does not depend on any of them.

### FAO/INFOODS West African Food Composition Table

| field | value |
|---|---|
| **included** | **no — CC BY-NC-SA 3.0 IGO (non-commercial)** |
| **dataset** | FAO/INFOODS Food Composition Table for Western Africa (WAFCT) 2019 (updates the 2012 West African Food Composition Table). |
| **licence checked** | Creative Commons **Attribution-NonCommercial-ShareAlike 3.0 IGO (CC BY-NC-SA 3.0 IGO)**. https://creativecommons.org/licenses/by-nc-sa/3.0/igo/ — item: https://openknowledge.fao.org/items/5fd48322-7e0f-487f-87f1-a5e0ebaf9e3c ; FAO/INFOODS databases: https://www.fao.org/infoods/infoods/tables-and-databases/faoinfoods-databases |
| **reason** | NC clause: "may be copied, redistributed and adapted for **non-commercial** purposes". FAO directs commercial use to a paid licence request (www.fao.org/contact-us/licence-request, copyright@fao.org). Fails the commercial-use rule. |
| **decision date** | 2026-09-03 |

### FAO/INFOODS Food Composition Table for Central & Eastern Africa

| field | value |
|---|---|
| **included** | **no — no distinct openly-licensed FAO regional table; nearest equivalents are CC BY-NC-SA 3.0 IGO or non-redistributable** |
| **dataset** | No standalone "FAO/INFOODS Food Composition Table for Central & Eastern Africa" is published by FAO/INFOODS. Nearest: HarvestPlus *A Food Composition Table for Central and Eastern Uganda* (Technical Monograph 9, 2012), and country tables (Kenya FCT 2018, Tanzania FCT 2008, Mozambique). |
| **licence checked** | HarvestPlus / IFPRI monograph: https://assets.publishing.service.gov.uk/media/57a08a90e5274a27b200066d/Tech_Mono_9_Web_0.pdf — not released under an open licence permitting commercial redistribution. FAO country tables (e.g. Kenya FCT 2018) carry **CC BY-NC-SA 3.0 IGO**. FAO/INFOODS directory: https://www.fao.org/infoods/infoods/tables-and-databases/faoinfoods-databases |
| **reason** | The named dataset does not exist as an FAO product; the substitutes are either NC-licensed (CC BY-NC-SA 3.0 IGO) or have no redistribution grant. Fails both rules. |
| **decision date** | 2026-09-03 |

### FAO/INFOODS ASEAN Food Composition Database

| field | value |
|---|---|
| **included** | **no — ASEANFOODS terms: non-commercial free only, commercial use "may incur fees"** |
| **dataset** | ASEAN Food Composition Database, electronic version 1 (February 2014), ASEANFOODS Regional Centre, Institute of Nutrition, Mahidol University (INMU), Thailand. |
| **licence checked** | ASEANFOODS Terms of Use: http://www.inmu.mahidol.ac.th/aseanfoods/terms_of_use.php — "Non-commercial users are authorized to access and use the data free of charge, provided that appropriate acknowledgement of ASEANFOODS as the source and copyright holder is given. **Reproduction for resale or other commercial uses including educational purposes may incur fees.**" Permission requests: kunchit.jud@mahidol.ac.th. |
| **reason** | Free use is non-commercial only; commercial use requires paid permission. Fails the commercial-use rule. |
| **decision date** | 2026-09-03 |

### South Korea — Korea Food Composition Database (RDA / data.go.kr)

| field | value |
|---|---|
| **included** | **no — KOGL Type 2 (출처표시 + 상업적 이용금지 / Attribution + Non-Commercial)** |
| **dataset** | 국가표준식품성분표 / National Standard Food Composition Table, Rural Development Administration (RDA), National Institute of Agricultural Sciences. Published on 농식품올바로 (koreanfood.rda.go.kr) and the public data portal data.go.kr. |
| **licence checked** | data.go.kr dataset "농촌진흥청 국립식량과학원_국가표준식품성분표" (https://www.data.go.kr/data/15143721/fileData.do): licence stated as **"공공저작물 : 출처표시, 상업적 이용금지 (제2유형)"** = Korea Open Government License (KOGL) **Type 2 — Attribution + No Commercial Use**. https://www.kogl.or.kr/info/license.do |
| **reason** | KOGL Type 2 explicitly prohibits commercial use. (The spec's guess of "likely KOGL Type 1" was wrong for this dataset.) Fails the commercial-use rule. `translations/korea_en.csv` stays as a committed stub but no `korea` extractor is wired in. |
| **decision date** | 2026-09-03 |

---

## Excluded outright (not researched — pre-decided in the spec)

| region | source | why excluded |
|---|---|---|
| Japan | MEXT — Standard Tables of Food Composition in Japan | Cannot redistribute the tabular data under terms allowing a redistributed commercial artifact. |
| China | China CDC — China Food Composition Tables | No redistribution licence; commercial reuse not granted. |
| South Africa | SAFOODS / SAMRC — South African Food Composition Database | Licensed for use, not open redistribution; commercial redistribution not granted. |
| New Zealand | FOODfiles (Manatū Hauora / Plant & Food Research) | Paid/licensed product; no open redistribution or commercial-reuse grant. |

---

## Attribution surfaces

Every non-public-domain included source (`cofid`, `ciqual`, `afcd`, `cnf`,
`frida`) must have its credit line shown in **both**:

1. this file (full detail above), and
2. the in-app **Settings → "Food data sources"** line, listing each source name
   and licence.

`usda` (public domain / CC0) is listed there too, as a courtesy credit.

The `afcd` **Limitation of Data Statement** and the CC BY-SA 3.0 AU notice are
carried alongside `data/foods.sqlite` (this file + the in-app surface) to satisfy
the ShareAlike term.
