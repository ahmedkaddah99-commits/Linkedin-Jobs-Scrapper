from __future__ import annotations

import os


_SAFE_TEST_ENV = {
    "RUNR_ENV": "test",
    "DATABASE_BACKEND": "sqlite",
    "TURSO_DATABASE_URL": "",
    "TURSO_AUTH_TOKEN": "",
    "OBJECT_STORAGE_BACKEND": "local",
    "RUNR_DISABLE_QUOTAS": "1",
    "S3_ENDPOINT_URL": "",
    "S3_ACCESS_KEY_ID": "",
    "S3_SECRET_ACCESS_KEY": "",
    "S3_BUCKET": "",
}


for _name, _value in _SAFE_TEST_ENV.items():
    os.environ[_name] = _value
