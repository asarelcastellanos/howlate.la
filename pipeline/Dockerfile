# The pipeline, packaged to run as a Cloud Run job and on a backfill VM.
#
# Build from the repository root, so the context can hold pipeline/ alone.
# Cloud Run and the VMs are x86, so say so on an Apple Silicon Mac:
#   docker build --platform linux/amd64 -f pipeline/Dockerfile -t howlate-pipeline .
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

# Runs as an unprivileged user in a directory it owns. On Cloud Run /work is
# memory, and three things share it: the raw cache (three UTC partitions, about
# 3 GB), DuckDB's working memory (by default 80% of the limit, which does not
# count the cache), and DuckDB's spill directory (.tmp under the working
# directory). A job's memory limit, and DuckDB's own, have to be set with all
# three in mind.
RUN useradd --create-home --uid 10001 howlate && mkdir /work && chown howlate /work
USER howlate
WORKDIR /work

ENTRYPOINT ["python", "-m", "howlate_pipeline"]
