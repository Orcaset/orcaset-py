from collections.abc import Iterable
from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta

from orcaset import Context, Fetch, Period, Rule


class IterableRule(Rule[Any, Iterable[Period]]):
    def __init__(self, iterable: Iterable[Period]):
        super().__init__("IterableRule")
        self.iterable = iterable

    def compute(self, fetch: Fetch, key: Any) -> Iterable[Period]:
        # TODO: Wrap this in a something so that the cached version is replayable?
        # Or pass self to the fetch function, wrap the response in a replayable object/tee and return it?
        # That would be a bit meta and not sure it would ever resolve since it would just loop infinitely,
        # but the idea is that you somehow cache the iterable the first time it's called, then everytime after
        # that you'd return a tee of the cached iterable from the ctx. So wrapping/replaying logic would be defined here.
        return self.iterable


class Revenue(Rule[Period, float | None]):
    def __init__(self, start: date, initial: float, freq: relativedelta, growth: float):
        super().__init__("Revenue")
        self.start = start
        self.initial = initial
        self.freq = freq
        self.growth = growth

    def compute(self, fetch: Fetch, key: Period) -> float | None:
        if key == Period(self.start, self.start + self.freq):
            return self.initial

        prior_key = key.shift(-self.freq)
        prev = fetch(self, prior_key)
        if prev is None:
            return None
        return prev * (1 + self.growth)


ctx = Context()
revenue = Revenue(start=date(2026, 1, 1), initial=100, freq=relativedelta(months=1), growth=0.01)

print(ctx.demand(revenue, Period(date(2026, 1, 1), date(2026, 2, 1))))
print(ctx.demand(revenue, Period(date(2026, 2, 1), date(2026, 3, 1))))
print(ctx.demand(revenue, Period(date(2227, 3, 1), date(2227, 4, 1))))
print(ctx.dependencies(revenue, Period(date(2026, 3, 1), date(2026, 4, 1))))
