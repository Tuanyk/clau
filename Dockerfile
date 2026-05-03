# syntax=docker/dockerfile:1.7
FROM debian:bookworm-slim

# Keep apt's downloaded .deb files in the BuildKit cache mount.
# (debian:*-slim ships a docker-clean hook that wipes them otherwise.)
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' \
       > /etc/apt/apt.conf.d/keep-cache

# Tools cơ bản + firewall + git tools + python
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg git sudo bash gosu \
    iptables ipset bubblewrap dnsutils dnsmasq-base tcpdump \
    fzf ripgrep \
    python3 python3-pip python3-venv

# Node.js 22 LTS. Debian Bookworm ships Node 18, which is too old for
# current Next.js releases.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
      | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
      > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs

# GitHub CLI (gh)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | tee /etc/apt/keyrings/githubcli.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh

# Delta (git diff đẹp hơn)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    DELTA_VERSION="0.18.2" \
    && ARCH=$(dpkg --print-architecture) \
    && curl -fsSL "https://github.com/dandavison/delta/releases/download/${DELTA_VERSION}/git-delta_${DELTA_VERSION}_${ARCH}.deb" -o /tmp/delta.deb \
    && apt-get install -y /tmp/delta.deb && rm /tmp/delta.deb

# Non-root user
ARG USER_UID=1000
ARG USER_GID=1000
RUN groupadd --gid $USER_GID dev 2>/dev/null || true \
    && useradd --uid $USER_UID --gid $USER_GID -ms /bin/bash dev

USER dev
WORKDIR /home/dev
RUN mkdir -p /home/dev/.pip-user/bin /home/dev/.codex /home/dev/.gemini /home/dev/.history-store /home/dev/.npm
ENV PATH="/opt/clau-tools/bin:/home/dev/.pip-user/bin:/home/dev/.local/bin:${PATH}"

# ─── Pip toolbelt (baked into image) ────────────────────────
# Installed system-wide (/usr/local/lib/python3.*/dist-packages) so the
# clau-pip volume at /home/dev/.pip-user/ doesn't shadow them.
#
# Two RUN layers so edits to the FAST list don't re-download HEAVY deps:
#   HEAVY = big/slow (numpy, pandas, ...). Edit rarely.
#   FAST  = small/quick tools. Edit freely — rebuild is cached.
#
# To add a package: add a new line with a trailing backslash. Keep the
#                   LAST line in each block WITHOUT a trailing backslash.
# To remove:        delete its line (and add a backslash to the new last
#                   line if needed).
# Then: ./install.sh   (credentials + volumes survive the rebuild)

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --break-system-packages \
        numpy \
        pandas \
        httpx \
        requests \
        python-dotenv \
        pydantic \
        ruff \
        mypy \
        pytest \
        bs4 \
        google-auth \
        google-auth-oauthlib \
        google-api-python-client \
        pyyaml \
        python-dateutil \
        lxml \
        html5lib \
        jinja2 \
        tenacity \
        tqdm \
        sqlalchemy \
        openpyxl \
        matplotlib \
        pyarrow \
        aiohttp \
        pypdf \
        markdown \
        fastapi \
        uvicorn[standard] \
        python-multipart \
        google-analytics-data


USER dev

# Git config cho delta
RUN git config --global core.pager "delta" \
    && git config --global interactive.diffFilter "delta --color-only" \
    && git config --global delta.navigate true

# Scripts + clau-internal dirs
USER root
COPY --chown=dev:dev entrypoint.sh /entrypoint.sh
COPY init-firewall.sh /usr/local/bin/init-firewall.sh
RUN chmod +x /entrypoint.sh /usr/local/bin/init-firewall.sh \
    && mkdir -p /etc/clau/hooks /var/log/clau /opt/clau-tools/bin /run/clau-secrets \
    && chown -R dev:dev /opt/clau-tools /var/log/clau \
    && chmod 755 /etc/clau /etc/clau/hooks \
    && chmod 755 /var/log/clau /run/clau-secrets

# ─── DEV SCRATCHPAD ─────────────────────────────────────────
# Append one-liners here while iterating. Everything above stays
# cached, so a rebuild = just the new layer + the entrypoint tail.
# When a tool proves useful, MOVE it into its proper section
# above (apt block, pip block, etc.) and DELETE it from here.
#
# Each tool gets its OWN RUN line so removing one doesn't bust the
# others. Templates:
#   RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
#       --mount=type=cache,target=/var/lib/apt,sharing=locked \
#       apt-get update && apt-get install -y --no-install-recommends <pkg>
#   RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
#       pip install --break-system-packages <pkg>
#   RUN npm install -g <pkg>
USER root
# (append RUN lines here)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends imagemagick
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends ffmpeg
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --break-system-packages Pillow
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends jq
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends pandoc
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends tesseract-ocr
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends poppler-utils
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends libimage-exiftool-perl
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends sqlite3
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --break-system-packages yq
# manim build deps: gcc + Cairo/Pango headers for pycairo/manimpango
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential pkg-config python3-dev \
        libcairo2-dev libpango1.0-dev
# manim LaTeX rendering (Tex / MathTex). Slim subset (~1.5 GB) instead of
# texlive-full (~5 GB); covers latex-base, common math/science packages,
# Computer Modern fonts, TikZ, and dvisvgm (Manim uses dvi → svg).
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        texlive-latex-base \
        texlive-latex-extra \
        texlive-fonts-recommended \
        texlive-fonts-extra \
        texlive-science \
        texlive-pictures \
        cm-super \
        dvisvgm
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --break-system-packages \
        'manim>=0.18' \
        'jsonschema>=4' \
        'sympy>=1.12'
# ────────────────────────────────────────────────────────────

# AI CLIs (claude / codex / gemini) are NOT installed in this image.
# They live in the persistent `clau-tools` Docker volume mounted at
# /opt/clau-tools at run time (already first on PATH). Install/refresh
# them with `clau-update`, which runs an ephemeral container against
# the volume.

USER root
WORKDIR /workspace
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
