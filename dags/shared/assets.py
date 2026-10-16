"""Data assets produced by the pipelines. Downstream DAGs schedule on these."""

from airflow.sdk import Asset

FCT_ROOM_NIGHT = Asset("postgres://postgres:5432/dwh/core/fct_room_night")
MARTS_REVENUE = Asset("postgres://postgres:5432/dwh/marts/hotel_daily_kpi")
FCT_WEB_SESSION = Asset("postgres://postgres:5432/dwh/core/fct_web_session")
MARTS_WEB = Asset("postgres://postgres:5432/dwh/marts/web_funnel_daily")
OPERATIONS_STAGED = Asset("postgres://postgres:5432/dwh/staging/inventory_usage")
MARTS_OPERATIONS = Asset("postgres://postgres:5432/dwh/marts/consumables_daily")
