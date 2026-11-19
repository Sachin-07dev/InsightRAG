"""Validate the opt-in sales contract before a version can be published."""
# ruff: noqa: E501

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from insightrag.ingestion.parsers import ParsedDataset

SALES_COLUMNS = frozenset(
    {
        "transaction_id",
        "transaction_date",
        "region",
        "product",
        "revenue",
        "cost",
        "units",
        "returns",
        "currency",
    }
)


@dataclass(frozen=True)
class SalesRow:
    row_number: int
    transaction_id: str
    transaction_date: date
    region: str
    product: str
    revenue: Decimal
    cost: Decimal
    units: int
    returns: int
    currency: str


def _money(value: object) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError("Invalid monetary value") from None
    exponent = number.as_tuple().exponent
    if (
        not number.is_finite()
        or abs(number) >= Decimal("1000000000000000")
        or (isinstance(exponent, int) and exponent < -4)
    ):
        raise ValueError("Monetary value exceeds supported precision")
    return number


def _business_date(value: object) -> date:
    raw = str(value)
    try:
        return date.fromisoformat(raw)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            raise ValueError("Invalid sales date or count") from None
        if parsed.tzinfo is not None or parsed.time() != time.min:
            raise ValueError("Sales dates cannot contain a time or timezone") from None
        return parsed.date()


def validate_sales(dataset: ParsedDataset) -> tuple[SalesRow, ...] | None:
    """Return None for a non-sales schema; reject malformed claimed sales data."""
    columns = set(dataset.columns)
    if not columns.intersection({"transaction_id", "revenue", "currency"}):
        return None
    if columns != SALES_COLUMNS or not dataset.rows:
        raise ValueError("Sales dataset requires the exact approved columns and nonempty rows")
    seen: set[str] = set()
    result: list[SalesRow] = []
    for number, row in enumerate(dataset.rows, 2):
        transaction_id = row["transaction_id"]
        region, product, currency = row["region"], row["product"], row["currency"]
        if (
            not isinstance(transaction_id, str)
            or not 1 <= len(transaction_id) <= 128
            or transaction_id in seen
            or not isinstance(region, str)
            or not 1 <= len(region) <= 128
            or not isinstance(product, str)
            or not 1 <= len(product) <= 128
            or not isinstance(currency, str)
            or len(currency) != 3
            or not currency.isascii()
            or not currency.isupper()
            or not currency.isalpha()
        ):
            raise ValueError("Invalid or duplicate sales identity/dimension")
        seen.add(transaction_id)
        try:
            transaction_date = _business_date(row["transaction_date"])
            units = int(str(row["units"]))
            returns = int(str(row["returns"]))
        except (TypeError, ValueError):
            raise ValueError("Invalid sales date or count") from None
        if (
            str(units) != str(row["units"])
            or str(returns) != str(row["returns"])
            or units < 0
            or returns < 0
        ):
            raise ValueError("Sales counts must be nonnegative integers")
        result.append(
            SalesRow(
                number,
                transaction_id,
                transaction_date,
                region,
                product,
                _money(row["revenue"]),
                _money(row["cost"]),
                units,
                returns,
                currency,
            )
        )
    return tuple(result)
