from pathlib import Path
import re
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import pandas as pd
import requests

URL = "https://www.deq.virginia.gov/news-info/shortcuts/permits/air/issued-air-permits-for-data-centers"


def sanitize_filename(name: str) -> str:
    # 1. Replace non-breaking spaces (\xa0) with a standard space
    name = name.replace("\xa0", " ")
    # 2. Replace Unicode en-dash (\u2013) and em-dash (\u2014) with a standard ASCII hyphen
    name = name.replace("\u2013", "-").replace("\u2014", "-")
    # 3. Strip any remaining non-ASCII characters and illegal filesystem chars
    clean_ascii = name.encode("ascii", "ignore").decode("ascii")
    return re.sub(r'[\\/*?:"<>|\s]+', " ", clean_ascii).strip()


def ensure_project_dirs(base_dir: Path) -> dict[str, Path]:
    """Auto-creates the project folder structure and returns paths."""
    dirs = {
        "raw_pdfs": base_dir / "data" / "raw_pdfs",
        "json_cache": base_dir / "data" / "processed" / "json_cache",
        "processed": base_dir / "data" / "processed",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def sync_deq_permits(
    base_dir: Path,
    region_filter: str = "Northern",
    only_latest_per_facility: bool = True,
) -> pd.DataFrame:
    """
    Scrapes the Virginia DEQ Data Center Permits table, saves metadata to CSV,
    and downloads missing PDFs into data/raw_pdfs/.
    """
    dirs = ensure_project_dirs(base_dir)
    pdf_dir = dirs["raw_pdfs"]
    index_csv_path = dirs["processed"] / "deq_issued_air_permits_index.csv"

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    print("Fetching Virginia DEQ permit table...")
    response = requests.get(URL, headers=headers, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table")
    if not table:
        raise RuntimeError("Could not locate the permits table on the DEQ page.")

    rows = table.find_all("tr")
    records = []

    for idx, row in enumerate(rows[1:], start=1):
        cells = row.find_all(["th", "td"])
        if len(cells) < 6:
            continue

        row_text = [c.get_text(" ", strip=True) for c in cells]
        site_name, reg_app_no, issue_date, program_type, locality, region = row_text[:6]

        # Extract base 5-digit Registration Number (e.g. '73670' from '73670-14')
        base_reg_match = re.match(r"^(\d+)", reg_app_no)
        base_reg_no = base_reg_match.group(1) if base_reg_match else reg_app_no

        link_tag = row.find("a", href=True)
        pdf_url = urljoin(URL, link_tag["href"]) if link_tag else ""

        safe_site = sanitize_filename(site_name)
        safe_reg = sanitize_filename(reg_app_no)
        filename = f"{safe_reg} - {safe_site}.pdf"

        records.append({
            "site_name": site_name,
            "reg_app_no": reg_app_no,
            "base_reg_no": base_reg_no,
            "issue_date": issue_date,
            "issue_date_dt": pd.to_datetime(issue_date, errors="coerce"),
            "program_type": program_type,
            "locality": locality,
            "region": region,
            "pdf_url": pdf_url,
            "local_filename": filename,
            "local_filepath": pdf_dir / filename,
        })

    df = pd.DataFrame(records)

    # Filter to Northern Region if specified
    if region_filter:
        df = df[df["region"].str.contains(region_filter, case=False, na=False)].copy()

    # Sort by base_reg_no and issue_date so we can flag the newest superseding permit per facility
    df = df.sort_values(["base_reg_no", "issue_date_dt"], ascending=[True, False])
    df["is_latest_for_facility"] = ~df.duplicated(subset=["base_reg_no"], keep="first")

    if only_latest_per_facility:
        superseded_count = (~df["is_latest_for_facility"]).sum()
        print(f"Filtered out {superseded_count} older/superseded permits for existing Registration Numbers.")
        df = df[df["is_latest_for_facility"]].copy()

    # Download any missing PDFs for our filtered set
    downloaded, skipped = 0, 0
    for _, rec in df.iterrows():
        filepath: Path = rec["local_filepath"]
        if not rec["pdf_url"]:
            continue
        if filepath.exists():
            skipped += 1
            continue
        try:
            print(f"Downloading {rec['local_filename']}...")
            pdf_resp = requests.get(rec["pdf_url"], headers=headers, timeout=30)
            pdf_resp.raise_for_status()
            filepath.write_bytes(pdf_resp.content)
            downloaded += 1
            time.sleep(0.25)
        except Exception as e:
            print(f"  -> Failed to download {rec['pdf_url']}: {e}")

    # Save clean index CSV
    df.drop(columns=["issue_date_dt", "local_filepath"]).to_csv(index_csv_path, index=False)
    print(f"Sync complete! {downloaded} downloaded, {skipped} already on disk. Total active permits: {len(df)}")
    return df
