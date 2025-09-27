import os
import json

from sheetbridge.openapi_tool import _spec_text


def test_spec_is_deterministic():
    os.environ["GOOGLE_SHEET_ID"] = "schema_check"
    a = _spec_text()
    b = _spec_text()
    assert a == b
    assert json.loads(a)["openapi"].startswith("3.")
