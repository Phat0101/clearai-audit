"""Run AU audit for first 10 AU jobs from the grouped folder (test run)."""
import asyncio
import os
import sys
import csv
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
os.chdir(Path(__file__).parent)

from dotenv import load_dotenv
load_dotenv()

from ai_classifier.au_audit import (
    run_au_audit, create_csv_row, write_audit_xlsx,
    write_classification_detail_xlsx,
    _load_existing_csv_results,
)


GROUPED_FOLDER = Path("/Users/pat/Desktop/clearai-audit/input/grouped_2026-03-08_222914")
OUTPUT_DIR = Path("/Users/pat/Desktop/clearai-audit/output/au_audit_test_20")
MAX_CONCURRENT = 5


def find_au_jobs(grouped: Path, limit: int = 10) -> list[Path]:
    """Find AU job folders (entry prints with GTW_099 pattern)."""
    au_jobs = []
    for job_folder in sorted(grouped.iterdir()):
        if not job_folder.is_dir() or not job_folder.name.startswith("job_"):
            continue
        pdfs = list(job_folder.glob("*.pdf")) + list(job_folder.glob("*.PDF"))
        if any("GTW_099" in p.name for p in pdfs):
            au_jobs.append(job_folder)
            if len(au_jobs) >= limit:
                break
    return au_jobs


async def process_one_job(job_folder: Path, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        job_id = job_folder.name.replace("job_", "")
        pdfs = list(job_folder.glob("*.pdf")) + list(job_folder.glob("*.PDF"))
        if not pdfs:
            print(f"⚠️  Job {job_id}: No PDFs", flush=True)
            return {"success": False, "job_id": job_id, "error": "No PDFs"}

        out_job = OUTPUT_DIR / f"job_{job_id}"
        out_job.mkdir(parents=True, exist_ok=True)

        try:
            result, usage = await run_au_audit(job_id, pdfs, "", out_job)
            row = create_csv_row(result)

            # Save individual CSV
            job_csv = out_job / f"au_audit_{job_id}.csv"
            with open(job_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                writer.writeheader()
                writer.writerow(row)

            # Write classification detail XLSX if line details exist
            if result.header_validation.class_line_details:
                detail_path = out_job / f"classification_detail_{job_id}.xlsx"
                write_classification_detail_xlsx(job_id, result.header_validation.class_line_details, detail_path)

            print(f"✅ Job {job_id} — CLASS: \"{row.get('CLASS', '')}\" | UOM/QTY: \"{row.get('UOM/QTY', '')}\"", flush=True)
            return {"success": True, "job_id": job_id, "row": row}
        except Exception as e:
            print(f"❌ Job {job_id} failed: {e}", flush=True)
            return {"success": False, "job_id": job_id, "error": str(e)}


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    au_jobs = find_au_jobs(GROUPED_FOLDER, limit=20)
    print(f"\n{'='*80}")
    print(f"🇦🇺 AU AUDIT TEST RUN — {len(au_jobs)} jobs")
    print(f"   Output: {OUTPUT_DIR}")
    print(f"{'='*80}\n")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [process_one_job(f, semaphore) for f in au_jobs]
    results = await asyncio.gather(*tasks)

    # Collect successful rows
    all_rows = [r["row"] for r in results if r.get("success") and r.get("row")]
    all_rows.sort(key=lambda x: x.get("WAYBILL #", ""))

    # Write combined CSV
    csv_path = OUTPUT_DIR / "au_audit_test_20.csv"
    if all_rows:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            writer.writeheader()
            writer.writerows(all_rows)

    # Write combined XLSX
    xlsx_path = OUTPUT_DIR / "au_audit_test_20.xlsx"
    write_audit_xlsx(all_rows, xlsx_path)

    succeeded = sum(1 for r in results if r.get("success"))
    failed = sum(1 for r in results if not r.get("success"))

    print(f"\n{'='*80}")
    print(f"🏁 DONE — {succeeded} succeeded, {failed} failed")
    print(f"   CSV:  {csv_path}")
    print(f"   XLSX: {xlsx_path}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
