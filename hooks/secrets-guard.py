#!/usr/bin/env python3
"""
clau PreToolUse hook — block obvious secret-reading attempts.

Reads tool-call JSON on stdin. Exit 2 = block (reason on stderr, shown to AI).
Exit 0 = allow. Logs every block to /var/log/clau/secrets-guard.log (root-owned,
AI cannot reach it).

This is defense-in-depth, not primary security. The sidecar broker + firewall
are the load-bearing pieces.
"""
import json
import os
import re
import sys
import time

LOG_PATH = "/var/log/clau/secrets-guard.log"

BLOCKED_READ_PREFIXES = (
    "/root/",
    "/run/secrets/",
    "/run/clau-secrets/",
    "/proc/",
    "/etc/clau/",
)

BASH_RULES = [
    (r"\bprintenv\b", "printenv can dump env vars"),
    (r"(^|[\s;&|])env([\s;&|]|$)", "bare `env` dumps all env vars"),
    (r"(^|[\s;&|])set([\s;&|]|$)", "bare `set` dumps all variables"),
    (r"(^|[\s;&|])declare\b(?!\s+-[arxli]*\s+\w+=)", "`declare` without assignment dumps variables"),
    (r"(^|[\s;&|])export([\s;&|]|$)", "bare `export` dumps exported variables"),
    (r"\bcat\s+(\S*\s+)*/root/", "reading /root/ is forbidden"),
    (r"\bcat\s+(\S*\s+)*/run/secrets/", "reading /run/secrets/ is forbidden"),
    (r"\bcat\s+(\S*\s+)*/run/clau-secrets/", "reading /run/clau-secrets/ is forbidden — reference credential files by path; SDKs open them internally"),
    (r"\bcat\s+(\S*\s+)*/proc/\d+/environ", "reading process env is forbidden"),
    (r"\bcat\s+(\S*\s+)*/etc/clau/", "reading /etc/clau/ is forbidden"),
    (r"\bcat\s+\S*\.pem\b", "reading .pem files is forbidden"),
    (r"\bcat\s+\S*\.key\b", "reading .key files is forbidden"),
    (r"\b(curl|wget)\s.*-d\s.*\$\{?[A-Z_]*(TOKEN|KEY|SECRET|PASSWORD)", "do not POST secret env vars to external hosts"),
    (r"\bnslookup\s+\$", "dynamic DNS lookups can exfiltrate secrets"),
    (r"\bdig\s+\$", "dynamic DNS lookups can exfiltrate secrets"),
]


def log_block(tool: str, payload: dict, reason: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "tool": tool,
                "reason": reason,
                "payload": payload,
            }) + "\n")
    except Exception:
        pass


def block(tool: str, payload: dict, reason: str) -> None:
    log_block(tool, payload, reason)
    print(f"[clau-secrets-guard] BLOCKED: {reason}", file=sys.stderr)
    print("If you legitimately need this, ask the user to adjust the hook or", file=sys.stderr)
    print("use the auth broker (http://broker:9999) instead of reading secrets directly.", file=sys.stderr)
    sys.exit(2)


def check_path(tool: str, payload: dict, path: str) -> None:
    if not path:
        return
    for prefix in BLOCKED_READ_PREFIXES:
        if path.startswith(prefix):
            block(tool, payload, f"{tool} on {path} (matches {prefix})")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool = data.get("tool_name") or data.get("tool") or ""
    inp = data.get("tool_input") or data.get("input") or {}

    if tool == "Bash":
        cmd = inp.get("command", "")
        for pattern, reason in BASH_RULES:
            if re.search(pattern, cmd):
                block(tool, {"command": cmd}, reason)

    elif tool in ("Read", "Edit"):
        check_path(tool, inp, inp.get("file_path", ""))

    elif tool == "Write":
        check_path(tool, inp, inp.get("file_path", ""))
        content = inp.get("content", "")
        if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", content):
            block(tool, {"file_path": inp.get("file_path")}, "writing a private key block to disk")

    sys.exit(0)


if __name__ == "__main__":
    main()
