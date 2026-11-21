"""Where prices come from. `PriceSource` is an interface so the bundled JSON snapshot can later
be swapped for the live AWS Pricing API (optional, off by default — D2) without touching
the calculators or agents."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Protocol

SNAPSHOT_FILE = Path(__file__).resolve().parent / "aws_prices_snapshot.json"
DEFAULT_REGION = "us-east-1"


class PriceSource(Protocol):
    hours_per_month: float

    def hourly(
        self, family: str, size: str | None = None, region: str = DEFAULT_REGION
    ) -> float | None:
        """USD per hour, e.g. hourly("ec2", "m5.large"). None if unknown."""
        ...

    def monthly_fixed(self, item: str, region: str = DEFAULT_REGION) -> float | None: ...

    def per_million_requests(self, service: str, region: str = DEFAULT_REGION) -> float | None: ...

    def describe(self) -> str: ...


class JsonPriceSource:
    def __init__(self, path: Path = SNAPSHOT_FILE):
        data = json.loads(path.read_text(encoding="utf-8"))
        self._data = data
        self.hours_per_month = float(data["hours_per_month"])
        self._base_region = data["region"]
        self._other_region = float(data["other_region_multiplier"])

    def _regional(self, price: float | None, region: str) -> float | None:
        if price is None:
            return None
        return price if region == self._base_region else round(price * self._other_region, 6)

    def hourly(
        self, family: str, size: str | None = None, region: str = DEFAULT_REGION
    ) -> float | None:
        entry = self._data["hourly"].get(family)
        # families with sizes are dicts ({"m5.large": 0.096}); flat items are plain numbers
        price = entry.get(size or "") if isinstance(entry, dict) else entry
        return self._regional(price, region)

    def monthly_fixed(self, item: str, region: str = DEFAULT_REGION) -> float | None:
        return self._regional(self._data["monthly_fixed"].get(item), region)

    def per_million_requests(self, service: str, region: str = DEFAULT_REGION) -> float | None:
        return self._regional(self._data["per_million_requests"].get(service), region)

    def describe(self) -> str:
        return f"{self._data['source']} Snapshot {self._data['snapshot_date']}."


@lru_cache(maxsize=1)
def default_price_source() -> JsonPriceSource:
    return JsonPriceSource()
