from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from ai_classifier.nz.tools import nz_tariff_chapter_lookup


async def run(code: str = '8517') -> None:
    """Fetch, sanitize, print, and save NZ tariff data for the given 4+ digit HS code."""
    res = await nz_tariff_chapter_lookup(code)
    # Print sanitized JSON to stdout
    print(json.dumps(res, ensure_ascii=False, indent=2))

    # Also write to a file for inspection
    out_dir = Path(__file__).resolve().parents[1] / 'ai_classifier' / 'nz'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'sample_sanitized_{code}.json'
    out_path.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\nSanitized JSON written to: {out_path}")


if __name__ == '__main__':
    hs_code = sys.argv[1] if len(sys.argv) > 1 else '8517'
    asyncio.run(run(hs_code))