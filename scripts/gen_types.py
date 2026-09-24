"""Export the OpenAPI schema (no running server needed) and generate frontend types.

    uv run --project apps/api python scripts/gen_types.py
Writes apps/api/openapi.json and apps/web/src/api/schema.d.ts (both committed).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import _bootstrap


def main() -> None:
    os.environ.setdefault("BOT_MODE", "disabled")
    from app.main import create_app

    schema = create_app().openapi()
    target = _bootstrap.API_DIR / "openapi.json"
    target.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OpenAPI → {target.relative_to(_bootstrap.REPO_ROOT)}")

    npx = shutil.which("npx")
    if npx is None:
        sys.exit("npx not found: install Node.js 20+ to generate TypeScript types")
    out = _bootstrap.WEB_DIR / "src" / "api" / "schema.d.ts"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [npx, "--yes", "openapi-typescript", str(target), "-o", str(out)],
        check=True,
        cwd=_bootstrap.WEB_DIR,
        shell=sys.platform == "win32",
    )
    print(f"Types → {out.relative_to(_bootstrap.REPO_ROOT)}")


if __name__ == "__main__":
    main()
