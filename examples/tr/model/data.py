import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from dateutil.relativedelta import relativedelta

from orcaset import Period

DATA_DIR = Path(__file__).resolve().parent / "data"

type SpanData = list[tuple[Period, float | None]]
type PointData = list[tuple[date, float | None]]


def load_span_data(path: Path) -> dict[str, SpanData]:
    """
    Load span data from a CSV file.

    First row should contain CQ end dates in YYYY-MM-DD format.
    """
    response = {}
    with open(path) as f:
        reader = csv.reader(f)
        header = next(reader)
        end_dates = [date.fromisoformat(h.strip()) for h in header[1:]]
        periods = [Period(dt + relativedelta(months=-3, day=31), dt) for dt in end_dates]
        for row in reader:
            label = row[0]
            values = [float(v) if v else None for v in row[1:]]
            response[label] = list(zip(periods, values))
    return response


def load_point_data(path: Path) -> dict[str, PointData]:
    """
    Load point data from a CSV file.

    First row should contain dates in YYYY-MM-DD format.
    """
    response = {}
    with open(path) as f:
        reader = csv.reader(f)
        header = next(reader)
        dates = [date.fromisoformat(h.strip()) for h in header[1:]]
        for row in reader:
            label = row[0]
            values = [float(v) if v else None for v in row[1:]]
            response[label] = list(zip(dates, values))
    return response


def span_field(label: str, data: dict[str, SpanData]) -> Any:
    def factory() -> SpanData:
        try:
            return data[label]
        except KeyError:
            raise ValueError(f"No data found for label: {label}")

    return field(default_factory=factory)


def point_field(label: str, data: dict[str, PointData]) -> Any:
    def factory() -> PointData:
        try:
            return data[label]
        except KeyError:
            raise ValueError(f"No data found for label: {label}")

    return field(default_factory=factory)


INCOME_DATA = load_span_data(DATA_DIR / "historical-income.csv")
CASH_FLOW_DATA = load_span_data(DATA_DIR / "historical-cash-flow.csv")
BALANCE_SHEET_DATA = load_point_data(DATA_DIR / "historical-balance-sheet.csv")


@dataclass(slots=True)
class Income:
    product_sales: SpanData = span_field("Net product sales", INCOME_DATA)
    rental_revenue: SpanData = span_field("Rental and royalty revenue", INCOME_DATA)
    product_cogs: SpanData = span_field("Product cost of goods sold", INCOME_DATA)
    rental_cogs: SpanData = span_field("Rental and royalty cost", INCOME_DATA)
    sga: SpanData = span_field("Selling, marketing and administrative expenses", INCOME_DATA)
    other_income_net: SpanData = span_field("Other income, net", INCOME_DATA)
    tax_provision: SpanData = span_field("Provision for income taxes", INCOME_DATA)
    nci_net_income: SpanData = span_field(
        "Less: net income attributable to noncontrolling interests", INCOME_DATA
    )
    dividends_per_share: SpanData = span_field("Dividends per share", INCOME_DATA)
    shares_outstanding: SpanData = span_field("Average number of shares outstanding", INCOME_DATA)


@dataclass(slots=True)
class CashFlow:
    depreciation: SpanData = span_field("Depreciation", CASH_FLOW_DATA)
    deferred_income_taxes: SpanData = span_field("Deferred income taxes", CASH_FLOW_DATA)
    sec_premium_amortization: SpanData = span_field(
        "Amortization of marketable security premiums", CASH_FLOW_DATA
    )
    accounts_receivable: SpanData = span_field("Accounts receivable", CASH_FLOW_DATA)
    other_receivables: SpanData = span_field("Other receivables", CASH_FLOW_DATA)
    inventories: SpanData = span_field("Inventories", CASH_FLOW_DATA)
    prepaid_and_other_assets: SpanData = span_field(
        "Prepaid expenses and other assets", CASH_FLOW_DATA
    )
    ap_and_accrued_liabilities: SpanData = span_field(
        "Accounts payable and accrued liabilities", CASH_FLOW_DATA
    )
    income_taxes_payable: SpanData = span_field("Income taxes payable", CASH_FLOW_DATA)
    postretirement_benefits: SpanData = span_field(
        "Postretirement health care benefits", CASH_FLOW_DATA
    )
    deferred_comp_and_other_liabilities: SpanData = span_field(
        "Deferred compensation and other liabilities", CASH_FLOW_DATA
    )
    restricted_cash_change: SpanData = span_field("Change in Restricted Cash", CASH_FLOW_DATA)
    capex: SpanData = span_field("Capital expenditures", CASH_FLOW_DATA)
    split_dollar_life_insurance_repayment: SpanData = span_field(
        "Repayment of Premiums on Split Dollar Life Insurance Policies", CASH_FLOW_DATA
    )
    trading_security_purchases: SpanData = span_field(
        "Purchases of trading securities", CASH_FLOW_DATA
    )
    trading_security_sales: SpanData = span_field("Sales of trading securities", CASH_FLOW_DATA)
    afs_security_purchases: SpanData = span_field(
        "Purchase of available for sale securities", CASH_FLOW_DATA
    )
    afs_security_sales_maturities: SpanData = span_field(
        "Sale and maturity of available for sale securities", CASH_FLOW_DATA
    )
    share_repurchases: SpanData = span_field("Shares purchased and retired", CASH_FLOW_DATA)
    dividends_paid: SpanData = span_field("Dividends paid in cash", CASH_FLOW_DATA)
    bank_loan_proceeds: SpanData = span_field("Proceeds from bank loans", CASH_FLOW_DATA)
    bank_loan_repayments: SpanData = span_field("Repayment of bank loans", CASH_FLOW_DATA)
    fx_effect_on_cash: SpanData = span_field(
        "Effect of exchange rate changes on cash", CASH_FLOW_DATA
    )


@dataclass(slots=True)
class BalanceSheet:
    cash: PointData = point_field("Cash and cash equivalents", BALANCE_SHEET_DATA)
    restricted_cash: PointData = point_field("Restricted cash", BALANCE_SHEET_DATA)
    current_investments: PointData = point_field("Current investments", BALANCE_SHEET_DATA)
    ar_trade_net: PointData = point_field("Accounts Receivable Trade, Net", BALANCE_SHEET_DATA)
    other_receivables: PointData = point_field("Other receivables", BALANCE_SHEET_DATA)
    finished_goods_wip: PointData = point_field(
        "Finished goods and work-in-process", BALANCE_SHEET_DATA
    )
    raw_materials_supplies: PointData = point_field(
        "Raw materials and supplies", BALANCE_SHEET_DATA
    )
    income_taxes_receivable_prepaid: PointData = point_field(
        "Income Taxes Receivable and Prepaid", BALANCE_SHEET_DATA
    )
    prepaid_expenses: PointData = point_field("Prepaid expenses", BALANCE_SHEET_DATA)
    deferred_income_taxes_current: PointData = point_field(
        "Current - Deferred Income Taxes", BALANCE_SHEET_DATA
    )
    land: PointData = point_field("Land", BALANCE_SHEET_DATA)
    buildings: PointData = point_field("Buildings", BALANCE_SHEET_DATA)
    machinery_equipment: PointData = point_field("Machinery and equipment", BALANCE_SHEET_DATA)
    construction_in_progress: PointData = point_field(
        "Construction in progress", BALANCE_SHEET_DATA
    )
    lease_rou_assets: PointData = point_field(
        "Operating lease right-of-use assets", BALANCE_SHEET_DATA
    )
    accumulated_depreciation: PointData = point_field(
        "Less - accumulated depreciation", BALANCE_SHEET_DATA
    )
    goodwill: PointData = point_field("Goodwill", BALANCE_SHEET_DATA)
    trademarks: PointData = point_field("Trademarks", BALANCE_SHEET_DATA)
    investments: PointData = point_field("Investments", BALANCE_SHEET_DATA)
    split_dollar_life_insurance: PointData = point_field(
        "Split Dollar Officer Life Insurance", BALANCE_SHEET_DATA
    )
    prepaid_and_other_assets: PointData = point_field(
        "Prepaid expenses and other assets", BALANCE_SHEET_DATA
    )
    restricted_cash_other: PointData = point_field(
        "Noncurrent - Restricted Cash", BALANCE_SHEET_DATA
    )
    deferred_income_taxes_noncurrent: PointData = point_field(
        "Noncurrent - Deferred income taxes", BALANCE_SHEET_DATA
    )
    accounts_payable: PointData = point_field("Accounts Payable", BALANCE_SHEET_DATA)
    bank_loans: PointData = point_field("Current - Bank Loans", BALANCE_SHEET_DATA)
    dividends_payable: PointData = point_field("Dividends payable", BALANCE_SHEET_DATA)
    accrued_liabilities: PointData = point_field("Accrued Liabilities", BALANCE_SHEET_DATA)
    postretirement_benefits: PointData = point_field(
        "Current - Postretirement health care benefits", BALANCE_SHEET_DATA
    )
    deferred_income_taxes_current_liab: PointData = point_field(
        "Current - Deferred Income Taxes (liability)", BALANCE_SHEET_DATA
    )
    lease_liabilities: PointData = point_field(
        "Current - Operating lease liabilities", BALANCE_SHEET_DATA
    )
    income_taxes_payable: PointData = point_field("Income taxes payable", BALANCE_SHEET_DATA)
    uncertain_tax_positions_current: PointData = point_field(
        "Current - Liability for Uncertain Tax Positions", BALANCE_SHEET_DATA
    )
    deferred_compensation: PointData = point_field("Deferred compensation", BALANCE_SHEET_DATA)
    deferred_income_taxes_noncurrent_liab: PointData = point_field(
        "Noncurrent - Deferred income taxes (liability)", BALANCE_SHEET_DATA
    )
    bank_loans_noncurrent: PointData = point_field("Noncurrent - Bank Loans", BALANCE_SHEET_DATA)
    postretirement_benefits_noncurrent: PointData = point_field(
        "Noncurrent - Postretirement health care benefits", BALANCE_SHEET_DATA
    )
    industrial_development_bonds: PointData = point_field(
        "Industrial development bonds", BALANCE_SHEET_DATA
    )
    uncertain_tax_positions_noncurrent: PointData = point_field(
        "Noncurrent - Liability for uncertain tax positions", BALANCE_SHEET_DATA
    )
    lease_liabilities_noncurrent: PointData = point_field(
        "Noncurrent - Operating lease liabilities", BALANCE_SHEET_DATA
    )
    deferred_comp_and_other_liabilities: PointData = point_field(
        "Deferred compensation and other liabilities", BALANCE_SHEET_DATA
    )
    common_stock: PointData = point_field("Common stock, $0.694 par value", BALANCE_SHEET_DATA)
    class_b_common_stock: PointData = point_field(
        "Class B common stock, $0.694 par value", BALANCE_SHEET_DATA
    )
    capital_in_excess_of_par: PointData = point_field(
        "Capital in excess of par value", BALANCE_SHEET_DATA
    )
    retained_earnings: PointData = point_field("Retained earnings", BALANCE_SHEET_DATA)
    aoci_loss: PointData = point_field("Accumulated Other Comprehensive Loss", BALANCE_SHEET_DATA)
    treasury_stock: PointData = point_field("Treasury Stock (at Cost)", BALANCE_SHEET_DATA)
    noncontrolling_interests: PointData = point_field(
        "Noncontrolling interests", BALANCE_SHEET_DATA
    )


if __name__ == "__main__":
    income = Income()
    print(income)
    cash_flow = CashFlow()
    print(cash_flow)
    balance_sheet = BalanceSheet()
    print(balance_sheet)
