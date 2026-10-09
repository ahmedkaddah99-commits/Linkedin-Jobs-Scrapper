"""Small no-credit probe of the free CompanyEnrich logo and autocomplete APIs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_companyenrich_credits import checked_tokens, proxy_pool, session_for
from scripts.populate_free_companyenrich_logos import image_dimensions


def main() -> None:
    token = dict(checked_tokens()[0])["Company_Enrich_API_URL_v17"]
    proxies = proxy_pool()
    operations = [
        ("logo", "rational-ag.com"),
        ("logo", "definitely-not-a-real-company-3489283.invalid"),
        ("autocomplete", "wintershall dea"),
        ("autocomplete", "stadt hilden"),
    ]
    for index, (kind, term) in enumerate(operations):
        with session_for(proxies[30 + index]) as session:
            if kind == "logo":
                response = session.get(f"https://api.companyenrich.com/logo/{term}", headers={"Authorization": f"Bearer {token}", "Accept": "image/*"}, timeout=(10, 20))
                item = {"kind": kind, "term": term, "status": response.status_code, "content_type": response.headers.get("content-type"), "dimensions": image_dimensions(response.content, response.headers.get("content-type", "")), "bytes": len(response.content), "credit_cost": response.headers.get("x-credit-cost")}
            else:
                response = session.get("https://api.companyenrich.com/companies/autocomplete", params={"query": term}, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=(10, 20))
                data = response.json() if response.status_code == 200 else []
                item = {"kind": kind, "term": term, "status": response.status_code, "items": [{"name": x.get("name"), "domain": x.get("domain"), "logoUrl": x.get("logoUrl")} for x in data[:5]] if isinstance(data, list) else [], "credit_cost": response.headers.get("x-credit-cost")}
            print(json.dumps(item, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
