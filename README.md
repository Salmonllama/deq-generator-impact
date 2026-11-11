# DEQ Generator Impact

> [!WARNING]
> **The data in this repository is a work in progress and is not yet accurate.** The current generator count (12,707 rows in `data/processed/all_nova_generators.csv`) is known to be wrong. Do not cite or reuse these figures until the issues below are fixed and the validation checks have passed. See [Known data issues](#known-data-issues).

## Goal

This project catalogs permitted diesel generators in the Virginia Department of Environmental Quality (DEQ) Northern Region and asks who lives and works near them. The planned work is:

1. **Catalog** every permitted generator from DEQ air permits: unit counts, ratings, EPA tier, controls, and permitted emission limits.
2. **Map hotspots** of permitted generator capacity against vulnerable communities (CDC Social Vulnerability Index and the Virginia Environmental Justice Act definitions) and sensitive sites such as schools, community centers, and hospitals.
3. **Request actual emissions** from permit holders through Virginia FOIA, since permits only show what is allowed, not what is emitted.
4. **Write a two-page policy brief** on emissions or zoning rules for advocacy groups and environmental nonprofits.

"Northern Region" here means DEQ's own Northern Regional Office area, as labeled on DEQ's permit list. It is wider than what most people call Northern Virginia and includes Caroline, Louisa, Spotsylvania, and Stafford counties.

## How to run it

The pipeline has two steps, both run from `notebooks/01_extract_test.ipynb`:

1. **Scrape and download.** `src/scraper.py` reads DEQ's permit table, keeps Northern Region permits, keeps only the latest permit per registration number, writes `data/processed/deq_issued_air_permits_index.csv`, and downloads any missing PDFs into `data/raw_pdfs/`.
2. **Extract and compile.** The notebook sends each PDF to the Gemini API with the Pydantic schema in `src/schema.py`, caches each result as JSON in `data/processed/json_cache/`, and unrolls the cached JSON into one row per generator in `data/processed/all_nova_generators.csv`.

### Setup

There is no `requirements.txt` yet, so install the packages the code imports:

```bash
python -m venv .venv
source .venv/bin/activate
pip install requests beautifulsoup4 pandas pydantic google-genai python-dotenv jupyter
```

Create a `.env` file in the repository root with a Gemini API key (it is gitignored):

```
GEMINI_API_KEY=your-key-here
```

Then start Jupyter from the repository root, open `notebooks/01_extract_test.ipynb`, and run the cells in order. The notebook expects to run from inside `notebooks/`, since it treats the parent folder as the project root.

Notes:

- The PDFs are gitignored. The scraper downloads them again on the first run.
- Extraction is skipped for any permit that already has a JSON file in `json_cache/`. Delete a cached file to re-extract it.
- Model output is not deterministic, even at temperature 0, so a rerun may not reproduce the committed JSON exactly.

## Data sources

| Source | What it provides | Retrieved |
| --- | --- | --- |
| [DEQ: Issued air permits for data centers](https://www.deq.virginia.gov/news-info/shortcuts/permits/air/issued-air-permits-for-data-centers) | Permit list (site, registration number, issue date, program type, locality, region) and links to permit PDFs | Not recorded. The committed data was retrieved on or before 2026-11-11. |
| Permit PDFs linked from that page | Equipment lists, ratings, and emission limits, extracted into `json_cache/` | Not recorded. Same as above. |

The pipeline does not yet record when the page or each PDF was fetched. Adding retrieval timestamps and PDF hashes is part of the fixes below.

## Known data issues

These are the problems found in a review of the pipeline and data at commit `054c206`. Each one changes the headline numbers.

- **Unit unrolling invents generators.** The schema stores each group of generators as one start number and one end number, then creates a row for every number in between. Permits often list scattered IDs, so a list like "EG1 through EG26 and EG193 through EG260" (94 units) becomes 260 rows. Across the dataset this adds roughly 1,000 units that do not exist, out of 12,707 rows. Letter-based IDs are also rewritten as numbers (for example, "DCD-D, DCD-E, DCD-R" becomes DCD-4, DCD-5, DCD-6), so some generator IDs in the CSV do not appear in any permit.
- **One facility is counted twice.** DEQ's permit page links the same PDF (Amazon IAD-45, registration 74333-1, Prince William County) to two different permits. Because of that, IAD-45's generators appear twice in the dataset.
- **One permit is missing.** The second permit sharing that link is Westfax Property Owner A LP (registration 74331-1, Fairfax County). Its actual permit was never downloaded, so its generators are absent. Only 155 of 157 permits extracted to distinct facilities.
- **The source covers data centers only.** The scraper reads DEQ's list of data center air permits. Hospitals, schools, universities, utilities, government campuses, and industrial sources are not included, so this is not yet a list of *all* permitted diesel generators in the region.

Other limits to keep in mind:

- Units listed as "new or modified" are counted as active, but a permit authorizes construction and does not prove a generator was built. Treat counts as **permitted** capacity, not installed capacity.
- One facility in the data (74172-3) runs natural gas engines, not diesel.
- Facility-level limits repeat on every generator row in the CSV. Do not sum facility columns across rows.

## How it is being addressed

These issues are being fixed. None of the fixes below is done yet. They are planned in this order:

- **Settle scope and wording.** Decide between "data center generators" and "all generators," label counts as permitted rather than installed, and state which counties are included.
- **Fix how generator groups are stored.** Change the schema so a scattered list of unit IDs is kept exactly as written instead of being forced into one range, and let missing values be blank instead of guessed. Then re-extract every permit.
- **Record provenance before re-extracting.** Save retrieval dates, PDF hashes, an archived copy of each PDF, and the model, prompt, and schema version with each extraction.
- **Stop the run on bad input.** Fail loudly on duplicate PDF links, registration numbers that do not match DEQ's list, permits with zero generators, and unit counts that do not match the permit text. This catches the IAD-45 / Westfax problem.
- **Split facility and generator tables and clean up locality names** before building the map.
- **Run the validation checks and the manual spot-check** described below.

## Planned validations

Five automated checks, all writing to one shared results table (record, check, pass/flag/fail, reason, source citation):

1. **Range validation.** Confirm each group's unit IDs and unit count match the permit text, including scattered lists and wording like "and," "through," and "except."
2. **Physics bounds.** Check ratings, hours, and emission limits against EPA engine standards and manufacturer specs to catch column shifts, rounding errors, and totals mistaken for per-unit values.
3. **Unit normalization.** Record whether each rating is in kW, MW, bhp, or kVA and convert to a common basis, flagging values that look like the wrong unit.
4. **AI extraction check.** Compare the extracted registration number, permit number, and locality against DEQ's own permit list from the scraper. Any mismatch is a failure.
5. **Campus capacity and unit counts.** Compare each facility's emission cap with what its listed units could emit, to catch missed pages, missed groups of units, or total-versus-per-unit mix-ups.

### Manual spot-check

- Pick a random sample of at least 30 permits (5 to 10% of permits, whichever is larger), weighted toward permits whose unit ID text contains "and," commas, or letters.
- For each, check the unit count, IDs, ratings, and emission limits by hand against the source PDF.
- Log every discrepancy in the shared results table and publish the resulting error rate alongside the data.

## License

All code, data, and documentation in this repository are released under the [MIT License](LICENSE).

Copyright (c) 2026 Alyx Batte.

## How to cite

If you use this code or data, please cite it as:

> Batte, Alyx. *DEQ Generator Impact: Permitted diesel generators in Virginia DEQ's Northern Region.* 2026. GitHub repository, https://github.com/Salmonllama/deq-generator-impact

Because the data is still being corrected (see [Known data issues](#known-data-issues)), please also note the commit hash or date of the version you used.

## Contact

For questions, corrections, or feedback, please [open an issue](https://github.com/Salmonllama/deq-generator-impact/issues) on this repository.
