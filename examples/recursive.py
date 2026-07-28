from collections.abc import Iterable
from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta

from orcaset import Context, Period, Rule, Step, fetch


class IterableRule(Rule[Any, Iterable[Period]]):
    def __init__(self, iterable: Iterable[Period]):
        super().__init__("IterableRule")
        self.iterable = iterable

    def compute(self, key: Any) -> Iterable[Period]:
        # TODO: Wrap this in a something so that the cached version is replayable?
        # See Replayable in examples/series.py, which buffers a lazy source so the
        # cached iterable can be re-iterated safely.
        return self.iterable


class Revenue(Rule[Period, float | None]):
    def __init__(self, start: date, initial: float, freq: relativedelta, growth: float):
        super().__init__("Revenue")
        self.start = start
        self.initial = initial
        self.freq = freq
        self.growth = growth

    def compute(self, key: Period) -> Step[float | None]:
        if key == Period(self.start, self.start + self.freq):
            return self.initial

        prior_key = key.shift(-self.freq)
        prev = yield from fetch(self, prior_key)
        if prev is None:
            return None
        return prev * (1 + self.growth)


ctx = Context()
revenue = Revenue(start=date(2026, 1, 1), initial=100, freq=relativedelta(months=1), growth=0.01)

print(ctx.demand(revenue, Period(date(2026, 1, 1), date(2026, 2, 1))))
print(ctx.demand(revenue, Period(date(2026, 2, 1), date(2026, 3, 1))))
print(ctx.demand(revenue, Period(date(2527, 3, 1), date(2527, 4, 1))))
print(ctx.dependencies(revenue, Period(date(2026, 3, 1), date(2026, 4, 1))))
