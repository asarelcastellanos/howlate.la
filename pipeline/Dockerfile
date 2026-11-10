# The pipeline, packaged to run as a Cloud Run job and on a backfill VM.
#
# Build from the repository root, so the context can hold pipeline/ alone:
#   docker build -f pipeline/Dockerfile -t howlate-pipeline .
#
# Pinned by digest as well as tag. A tag can be moved to different contents
# after this file was reviewed; a digest cannot.
FROM python:3.14.10-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Only the pipeline. The collector and the site have no business in an image
# whose job is grading days, and leaving them out keeps it small.
COPY pipeline/pyproject.toml /src/pipeline/pyproject.toml
COPY pipeline/src /src/pipeline/src
RUN pip install /src/pipeline && rm -rf /src

# Runs as an unprivileged user in a directory it owns. The raw cache and the
# output go under /work, which on Cloud Run is memory, so a job's memory limit
# has to cover a few days of raw files.
RUN useradd --create-home --uid 10001 howlate && mkdir /work && chown howlate /work
USER howlate
WORKDIR /work

ENTRYPOINT ["python", "-m", "howlate_pipeline"]
