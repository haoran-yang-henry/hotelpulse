FROM apache/airflow:3.3.2-python3.12

# Runtime dependencies of the hotelpulse package (psycopg 3, PyYAML, httpx) already ship
# with the base image. Only test tooling is added so DAG integrity tests run in the same
# image that runs the DAGs.
RUN pip install --no-cache-dir "pytest>=8.3,<9"

# Project code is mounted at runtime (see docker-compose.yml) for a fast edit-run loop.
ENV PYTHONPATH=/opt/hotelpulse/src \
    HOTELPULSE_ROOT=/opt/hotelpulse
