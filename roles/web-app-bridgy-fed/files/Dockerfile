# Runtime image for Bridgy Fed (Flask), built from a clone of upstream.
#
# Both stages carry /usr/local over rather than reinstalling, so the
# python-version-specific site-packages path never has to be hardcoded, and
# gunicorn is present at runtime instead of the entrypoint dying with
# `gunicorn: not found` in a restart loop.
#
# Upstream serves oauth_dropins assets from /app/oauth_dropins_static and ships
# no such directory, so the package's own static tree is linked in.
#
# BRIDGY_REF is a commit, because upstream publishes no tags. `git clone
# --branch` refuses a commit, hence the fetch of the single ref instead.
ARG PY_BASE
FROM ${PY_BASE} AS build

ARG BRIDGY_REPO_URL
ARG BRIDGY_REF

RUN rm -rf /var/lib/apt/lists/* && \
    apt-get -o Acquire::Retries=3 update && apt-get -o Acquire::Retries=3 install -y --no-install-recommends \
    git build-essential pkg-config autoconf automake libtool curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN git init -q . && \
    git remote add origin "${BRIDGY_REPO_URL}" && \
    git fetch -q --depth=1 origin "${BRIDGY_REF}" && \
    git checkout -q --detach FETCH_HEAD

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY link_oauth_dropins_static.py /tmp/link_oauth_dropins_static.py
RUN python - < /tmp/link_oauth_dropins_static.py

FROM ${PY_BASE}

ARG CONTAINER_PORT
ENV PORT=${CONTAINER_PORT}

WORKDIR /app
COPY --from=build /app /app
COPY --from=build /usr/local /usr/local

RUN useradd -r -m -d /nonroot appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE ${PORT}
CMD ["sh", "-lc", "exec gunicorn -w 2 -k gthread -b 0.0.0.0:${PORT} flask_app:app"]
