FROM python:3.11-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tmux asciinema bash \
    && rm -rf /var/lib/apt/lists/*

COPY data /app/data
COPY docs /app/docs
COPY payroll /app/payroll
COPY output /app/output

RUN chmod 755 /app/payroll/run.sh
