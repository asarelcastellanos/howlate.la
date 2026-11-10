# The pipeline, packaged to run as a Cloud Run job and on a backfill VM.
#
# Build from the repository root, so the context can hold pipeline/ alone.
# Cloud Run is x86, so build for linux/amd64 on an Apple Silicon Mac:
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
#
# Dependencies come from the hashed lock alone. Then the package installs with
# no index and no build isolation, so pip cannot fetch anything unpinned, and it
# fails if the lock lacks a dependency pyproject.toml declares.
COPY pipeline/requirements.lock /src/pipeline/requirements.lock
RUN pip install --require-hashes --only-binary :all: --no-deps -r /src/pipeline/requirements.lock
COPY pipeline/pyproject.toml /src/pipeline/pyproject.toml
COPY pipeline/src /src/pipeline/src
RUN pip install --no-index --no-build-isolation /src/pipeline && rm -rf /src

# Runs as an unprivileged user in a directory it owns. On Cloud Run /work is
# memory, and it holds the raw cache (three UTC partitions, about 3 GB), the
# unpacked timetables (about 0.3 GB, more when an older copy is tried), DuckDB's
# working memory (by default 80% of the limit, which does not count the files),
# and DuckDB's spill directory (.tmp under the working directory). A job's
# memory limit, and DuckDB's own, have to be set with all of them in mind.
RUN useradd --create-home --uid 10001 howlate && mkdir /work && chown howlate /work
USER howlate
WORKDIR /work

# The commit the image was built from, so every run's log names the code it
# ran. Set late, so changing it does not invalidate the dependency layers.
ARG COMMIT=unknown
ENV HOWLATE_COMMIT=$COMMIT

ENTRYPOINT ["python", "-m", "howlate_pipeline"]
