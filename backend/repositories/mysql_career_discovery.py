from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Iterable

from backend.connectors.company_career_discovery import CareerDiscoveryResult, domain_from_url


def _serialize(payload) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _validate_identifier(identifier: str) -> str:
    value = str(identifier or "").strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Invalid MySQL identifier: {identifier!r}")
    return value


def _source_key(result: CareerDiscoveryResult) -> str:
    stable_value = (
        result.company_domain
        or domain_from_url(result.homepage_url)
        or result.homepage_url
        or result.company_name
        or "unknown"
    ).strip().lower()
    digest = hashlib.sha256(stable_value.encode("utf-8")).hexdigest()[:24]
    return f"{stable_value[:220]}:{digest}"


@dataclass(frozen=True, slots=True)
class MySqlCareerDiscoveryConfig:
    host: str
    user: str
    password: str
    database: str
    port: int = 3306
    table: str = "company_career_url_discoveries"

    @classmethod
    def from_env(cls) -> "MySqlCareerDiscoveryConfig":
        return cls(
            host=os.getenv("CAREER_DISCOVERY_MYSQL_HOST") or os.getenv("MYSQL_HOST", ""),
            port=int(os.getenv("CAREER_DISCOVERY_MYSQL_PORT") or os.getenv("MYSQL_PORT") or "3306"),
            user=os.getenv("CAREER_DISCOVERY_MYSQL_USER") or os.getenv("MYSQL_USER", ""),
            password=os.getenv("CAREER_DISCOVERY_MYSQL_PASSWORD") or os.getenv("MYSQL_PASSWORD", ""),
            database=os.getenv("CAREER_DISCOVERY_MYSQL_DATABASE") or os.getenv("MYSQL_DATABASE", ""),
            table=os.getenv("CAREER_DISCOVERY_MYSQL_TABLE") or "company_career_url_discoveries",
        )

    def validate(self) -> None:
        missing = [
            name
            for name, value in {
                "host": self.host,
                "user": self.user,
                "database": self.database,
            }.items()
            if not str(value or "").strip()
        ]
        if missing:
            raise ValueError(f"Missing MySQL configuration: {', '.join(missing)}")
        _validate_identifier(self.table)


class MySqlCareerDiscoveryStore:
    def __init__(self, config: MySqlCareerDiscoveryConfig):
        config.validate()
        self.config = config
        self.table = _validate_identifier(config.table)

    def _connect(self):
        try:
            import pymysql
        except Exception as exc:
            raise RuntimeError(
                "PyMySQL is required for MySQL storage. Install dependencies with "
                "`pip install -r requirements.txt`."
            ) from exc

        return pymysql.connect(
            host=self.config.host,
            port=int(self.config.port),
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
            charset="utf8mb4",
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def initialize(self) -> None:
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self.table} (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            source_key VARCHAR(256) NOT NULL,
            company_domain VARCHAR(255) NOT NULL DEFAULT '',
            company_name VARCHAR(512) NOT NULL DEFAULT '',
            homepage_url TEXT NOT NULL,
            primary_career_url TEXT NOT NULL,
            secondary_candidate_urls_json LONGTEXT NOT NULL,
            ats_type VARCHAR(100) NOT NULL DEFAULT '',
            validation_evidence_json LONGTEXT NOT NULL,
            candidates_json LONGTEXT NOT NULL,
            confidence_score DECIMAL(6,4) NOT NULL DEFAULT 0,
            crawl_status VARCHAR(80) NOT NULL DEFAULT '',
            last_checked_at VARCHAR(40) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_company_career_source_key (source_key),
            KEY idx_company_domain (company_domain),
            KEY idx_crawl_status (crawl_status),
            KEY idx_ats_type (ats_type)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(ddl)

    def upsert_result(self, result: CareerDiscoveryResult) -> None:
        sql = f"""
        INSERT INTO {self.table} (
            source_key,
            company_domain,
            company_name,
            homepage_url,
            primary_career_url,
            secondary_candidate_urls_json,
            ats_type,
            validation_evidence_json,
            candidates_json,
            confidence_score,
            crawl_status,
            last_checked_at
        ) VALUES (
            %(source_key)s,
            %(company_domain)s,
            %(company_name)s,
            %(homepage_url)s,
            %(primary_career_url)s,
            %(secondary_candidate_urls_json)s,
            %(ats_type)s,
            %(validation_evidence_json)s,
            %(candidates_json)s,
            %(confidence_score)s,
            %(crawl_status)s,
            %(last_checked_at)s
        )
        ON DUPLICATE KEY UPDATE
            company_domain = VALUES(company_domain),
            company_name = VALUES(company_name),
            homepage_url = VALUES(homepage_url),
            primary_career_url = VALUES(primary_career_url),
            secondary_candidate_urls_json = VALUES(secondary_candidate_urls_json),
            ats_type = VALUES(ats_type),
            validation_evidence_json = VALUES(validation_evidence_json),
            candidates_json = VALUES(candidates_json),
            confidence_score = VALUES(confidence_score),
            crawl_status = VALUES(crawl_status),
            last_checked_at = VALUES(last_checked_at)
        """
        payload = {
            "source_key": _source_key(result),
            "company_domain": result.company_domain or domain_from_url(result.homepage_url),
            "company_name": result.company_name,
            "homepage_url": result.homepage_url,
            "primary_career_url": result.primary_career_url,
            "secondary_candidate_urls_json": _serialize(result.secondary_candidate_urls),
            "ats_type": result.ats_type,
            "validation_evidence_json": _serialize(result.validation_evidence),
            "candidates_json": _serialize([candidate.to_dict() for candidate in result.candidates]),
            "confidence_score": float(result.confidence_score or 0),
            "crawl_status": result.crawl_status,
            "last_checked_at": result.discovered_at,
        }
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, payload)

    def upsert_results(self, results: Iterable[CareerDiscoveryResult]) -> int:
        count = 0
        for result in results:
            self.upsert_result(result)
            count += 1
        return count


__all__ = [
    "MySqlCareerDiscoveryConfig",
    "MySqlCareerDiscoveryStore",
]
