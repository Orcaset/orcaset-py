class Assumptions:
    class Income:
        product_sales_growth_rate = 0.05
        rental_revenue_growth_rate = 0.05
        product_cogs_margin = 0.50
        rental_cogs_margin = 0.50
        sga_growth_rate = 0.05
        other_income_growth_rate = 0.05
        income_tax_rate = 0.25
        nci_net_income_rate = -0.005

    class PPE:
        building_capex_share: float | None = None
        buildings_remaining_life_years = 30
        buildings_useful_life_years = 35
        machinery_remaining_life_years = 10
        machinery_useful_life_years = 12

    class Leases:
        remaining_life_years: float | None = None
        current_liability_quarters = 4
