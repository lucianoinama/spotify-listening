FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 \
    DBT_PROFILES_DIR=/dbt

RUN pip install "dbt-core~=1.11.0" "dbt-postgres~=1.11.0"

WORKDIR /dbt
COPY . /dbt

ENTRYPOINT ["dbt"]
CMD ["build"]
