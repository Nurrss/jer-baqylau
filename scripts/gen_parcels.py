"""Regenerate packages/seed/parcels.geojson (deterministic).

uv run --project apps/api python scripts/gen_parcels.py
"""

from __future__ import annotations

import _bootstrap

from app.seed.generator import write

if __name__ == "__main__":
    target = _bootstrap.REPO_ROOT / "packages" / "seed" / "parcels.geojson"
    print(f"Wrote {write(target)} parcels to {target}")
