import os, json, argparse


def _load_app():
    # avoid import-time Settings errors
    os.environ.setdefault("GOOGLE_SHEET_ID", "schema_check")
    from sheetbridge.main import app
    return app


def _spec_text():
    app = _load_app()
    spec = app.openapi()
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def _write(path: str) -> str:
    text = _spec_text()
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def _check(path: str) -> bool:
    want = _spec_text()
    try:
        have = open(path, "r", encoding="utf-8").read()
    except FileNotFoundError:
        return False
    return have == want


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="openapi.json")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        ok = _check(a.out)
        if not ok:
            print(
                "openapi.json out of date. Regenerate with:\n  python -m sheetbridge.openapi_tool --out {a.out}"
            )
            raise SystemExit(1)
        print("openapi.json up-to-date")
    else:
        text = _write(a.out)
        print(f"Wrote {a.out} ({len(text)} bytes)")


if __name__ == "__main__":
    main()
