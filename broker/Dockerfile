# Broker sidecar — holds API credentials so they never enter the Claude container.
# Build context is the repo root so we can COPY init-firewall.sh from there.
#   docker build -t clau-broker -f broker/Dockerfile .
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates iptables ipset dnsutils dnsmasq-base sudo \
    && rm -rf /var/lib/apt/lists/*

# Non-root broker user. Sudo only for init-firewall.sh.
RUN useradd --uid 1000 -ms /bin/bash broker \
    && echo "broker ALL=(ALL) NOPASSWD: /usr/local/bin/init-firewall.sh" \
        >> /etc/sudoers

COPY init-firewall.sh /usr/local/bin/init-firewall.sh
COPY broker/entrypoint.sh /entrypoint.sh
RUN chmod +x /usr/local/bin/init-firewall.sh /entrypoint.sh

WORKDIR /app
COPY broker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY broker/app /app/app

# Per-request log file written by app.request_log; surfaced at /dashboard.
RUN mkdir -p /var/log/broker && chown broker:broker /var/log/broker

USER broker
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
