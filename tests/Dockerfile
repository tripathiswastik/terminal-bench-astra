# Python Version: 3.11 (python:3.11-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84)
# Purpose: Isolated verifier container running pytest suite and emitting CTRF JSON and reward scores.
# Runs-in: Verifier container (/tests) in isolated network-restricted separate environment mode.
FROM python:3.11-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84
RUN apt-get update && apt-get install -y --no-install-recommends tmux asciinema \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN mkdir -p /app/data /app/output /logs/verifier
COPY requirements.txt /tests/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tests/requirements.txt
WORKDIR /tests
COPY . /tests/
RUN chmod +x /tests/test.sh
