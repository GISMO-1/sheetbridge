schema:
	python -m sheetbridge.openapi_tool --out openapi.json

schema-check:
	python -m sheetbridge.openapi_tool --check --out openapi.json
