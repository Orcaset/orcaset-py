# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Operating-revenue statement layout for the Southwest TSA nowcast."""

from model import (
    ancillary,
    freight,
    loyalty_air_transport,
    other,
    passenger_non_loyalty,
    passenger_revenue,
    total_operating_revenue,
)

from orcaset import Stmt, Total


def operating_revenue_stmt() -> Stmt:
    return Stmt(
        Total(
            total_operating_revenue,
            [
                Total(
                    passenger_revenue,
                    [
                        passenger_non_loyalty,
                        loyalty_air_transport,
                        ancillary,
                    ],
                ),
                freight,
                other,
            ],
        )
    )
