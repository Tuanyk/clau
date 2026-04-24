FROM debian:bookworm-slim

# Tools cơ bản + firewall + git tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git sudo bash \
    iptables ipset dnsutils \
    fzf \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI (gh)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | tee /etc/apt/keyrings/githubcli.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Delta (git diff đẹp hơn)
RUN DELTA_VERSION="0.18.2" \
    && ARCH=$(dpkg --print-architecture) \
    && curl -fsSL "https://github.com/dandavison/delta/releases/download/${DELTA_VERSION}/git-delta_${DELTA_VERSION}_${ARCH}.deb" -o /tmp/delta.deb \
    && apt-get install -y /tmp/delta.deb && rm /tmp/delta.deb

# Non-root user
ARG USER_UID=1000
ARG USER_GID=1000
RUN groupadd --gid $USER_GID dev 2>/dev/null || true \
    && useradd --uid $USER_UID --gid $USER_GID -ms /bin/bash dev \
    && echo "dev ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Native Claude Code (trước khi switch user để có quyền)
USER dev
WORKDIR /home/dev
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/home/dev/.local/bin:${PATH}"

# Git config cho delta
RUN git config --global core.pager "delta" \
    && git config --global interactive.diffFilter "delta --color-only" \
    && git config --global delta.navigate true

# Scripts
USER root
COPY --chown=dev:dev entrypoint.sh /entrypoint.sh
COPY init-firewall.sh /usr/local/bin/init-firewall.sh
RUN chmod +x /entrypoint.sh /usr/local/bin/init-firewall.sh

USER dev
WORKDIR /workspace
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]