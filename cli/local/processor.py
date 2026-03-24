"""Local data processor for analytics calculations."""

from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd
from rich.console import Console

console = Console()


class DataProcessor:
    """Process local data for analytics."""

    @staticmethod
    def parse_period(period: str) -> tuple[datetime, datetime]:
        """Parse period string to date range."""
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        period_map = {
            "today": (today, now),
            "1d": (today - timedelta(days=1), now),
            "7d": (today - timedelta(days=7), now),
            "14d": (today - timedelta(days=14), now),
            "30d": (today - timedelta(days=30), now),
            "90d": (today - timedelta(days=90), now),
            "180d": (today - timedelta(days=180), now),
            "365d": (today - timedelta(days=365), now),
            "ytd": (datetime(now.year, 1, 1), now),
        }

        if period in period_map:
            return period_map[period]

        # Try to parse as number of days
        if period.endswith("d") and period[:-1].isdigit():
            days = int(period[:-1])
            return (today - timedelta(days=days), now)

        raise ValueError(f"Invalid period format: {period}")

    @staticmethod
    def filter_by_date(
        df: pd.DataFrame,
        date_column: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Filter dataframe by date range."""
        if date_column not in df.columns:
            return df

        df = df.copy()
        df[date_column] = pd.to_datetime(df[date_column], errors="coerce")

        if start_date:
            df = df[df[date_column] >= start_date]
        if end_date:
            df = df[df[date_column] <= end_date]

        return df

    @staticmethod
    def calculate_overview(
        customers_df: pd.DataFrame,
        orders_df: pd.DataFrame,
        period: str = "7d",
    ) -> dict[str, Any]:
        """Calculate analytics overview from local data."""
        start_date, end_date = DataProcessor.parse_period(period)

        # Filter orders by period
        orders_filtered = DataProcessor.filter_by_date(
            orders_df, "created_at", start_date, end_date
        )

        # Filter customers by creation date for "new" count
        new_customers = DataProcessor.filter_by_date(
            customers_df, "created_at", start_date, end_date
        )

        total_revenue = orders_filtered["amount"].sum() if "amount" in orders_filtered.columns else 0
        total_orders = len(orders_filtered)
        avg_order_value = total_revenue / total_orders if total_orders > 0 else 0

        return {
            "period": period,
            "total_customers": len(customers_df),
            "new_customers": len(new_customers),
            "active_customers": orders_filtered["customer_id"].nunique() if "customer_id" in orders_filtered.columns else 0,
            "total_orders": total_orders,
            "total_revenue": round(total_revenue, 2),
            "average_order_value": round(avg_order_value, 2),
        }

    @staticmethod
    def calculate_retention(
        orders_df: pd.DataFrame,
        days_list: list[int],
    ) -> list[dict[str, Any]]:
        """Calculate customer retention rates."""
        results = []
        now = datetime.now()

        for days in days_list:
            cohort_start = now - timedelta(days=days * 2)
            cohort_end = now - timedelta(days=days)

            # Get cohort (customers who made first purchase in the window)
            orders_sorted = orders_df.sort_values("created_at")
            first_purchases = orders_sorted.groupby("customer_id")["created_at"].first()

            cohort_customers = first_purchases[
                (first_purchases >= cohort_start) & (first_purchases < cohort_end)
            ].index.tolist()

            if not cohort_customers:
                results.append({
                    "period_days": days,
                    "cohort_size": 0,
                    "retained_count": 0,
                    "retention_rate": 0.0,
                })
                continue

            # Check for repeat purchases
            retained = 0
            for customer_id in cohort_customers:
                customer_orders = orders_df[orders_df["customer_id"] == customer_id]
                if len(customer_orders) > 1:
                    order_dates = customer_orders["created_at"].sort_values()
                    if (order_dates.iloc[-1] - order_dates.iloc[0]).days >= days:
                        retained += 1

            retention_rate = (retained / len(cohort_customers)) * 100

            results.append({
                "period_days": days,
                "cohort_size": len(cohort_customers),
                "retained_count": retained,
                "retention_rate": round(retention_rate, 2),
            })

        return results

    @staticmethod
    def calculate_order_metrics(
        orders_df: pd.DataFrame,
        period: str = "30d",
        metric: str = "sales",
    ) -> dict[str, Any]:
        """Calculate order metrics."""
        start_date, end_date = DataProcessor.parse_period(period)
        orders_filtered = DataProcessor.filter_by_date(
            orders_df, "created_at", start_date, end_date
        )

        total_sales = orders_filtered["amount"].sum() if "amount" in orders_filtered.columns else 0
        total_orders = len(orders_filtered)
        unique_customers = orders_filtered["customer_id"].nunique() if "customer_id" in orders_filtered.columns else 0

        # Calculate repurchase rate
        customer_order_counts = orders_filtered["customer_id"].value_counts() if "customer_id" in orders_filtered.columns else pd.Series()
        repeat_customers = (customer_order_counts > 1).sum()
        repurchase_rate = (repeat_customers / unique_customers * 100) if unique_customers > 0 else 0

        return {
            "period": period,
            "total_sales": round(total_sales, 2),
            "total_orders": total_orders,
            "unique_customers": unique_customers,
            "average_order_value": round(total_sales / total_orders, 2) if total_orders > 0 else 0,
            "orders_per_customer": round(total_orders / unique_customers, 2) if unique_customers > 0 else 0,
            "repurchase_rate": round(repurchase_rate, 2),
        }

    @staticmethod
    def group_by_channel(
        orders_df: pd.DataFrame,
        period: str = "30d",
    ) -> pd.DataFrame:
        """Group orders by channel."""
        start_date, end_date = DataProcessor.parse_period(period)
        orders_filtered = DataProcessor.filter_by_date(
            orders_df, "created_at", start_date, end_date
        )

        if "channel" not in orders_filtered.columns:
            return pd.DataFrame()

        grouped = orders_filtered.groupby("channel").agg({
            "id": "count",
            "amount": "sum",
            "customer_id": "nunique",
        }).rename(columns={
            "id": "order_count",
            "amount": "total_sales",
            "customer_id": "customer_count",
        })

        grouped["avg_order_value"] = grouped["total_sales"] / grouped["order_count"]
        return grouped.round(2)

    @staticmethod
    def group_by_province(
        orders_df: pd.DataFrame,
        period: str = "30d",
    ) -> pd.DataFrame:
        """Group orders by province."""
        start_date, end_date = DataProcessor.parse_period(period)
        orders_filtered = DataProcessor.filter_by_date(
            orders_df, "created_at", start_date, end_date
        )

        if "province" not in orders_filtered.columns:
            return pd.DataFrame()

        grouped = orders_filtered.groupby("province").agg({
            "id": "count",
            "amount": "sum",
            "customer_id": "nunique",
        }).rename(columns={
            "id": "order_count",
            "amount": "total_sales",
            "customer_id": "customer_count",
        })

        return grouped.sort_values("total_sales", ascending=False).round(2)
