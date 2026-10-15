"""Data assets produced by the pipelines. Downstream DAGs schedule on these."""

from airflow.sdk import Asset

FCT_ROOM_NIGHT = Asset("postgres://postgres:5432/dwh/core/fct_room_night")
MARTS_REVENUE = Asset("postgres://postgres:5432/dwh/marts/hotel_daily_kpi")
