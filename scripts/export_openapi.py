"""Export the live OpenAPI spec to backend/contracts/openapi.json (contract freeze)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "contracts" / "openapi.json"


def main() -> None:
    spec = app.openapi()
    OUT.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"exported {OUT}")


if __name__ == "__main__":
    main()
