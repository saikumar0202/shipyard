#!/usr/bin/env python3
"""Attack test (f) only, run in the fingerprint job (no AI).
Reads CLAUDE_CODE_OAUTH_TOKEN and writes SHA-256 hashes of every 16-char
window of its random part. The fixed prefix (e.g. "sk-ant-oat01-") is left
out, so every window is all random characters: no window can be guessed,
and windows can't be chained to rebuild the token. Never prints the token.
Usage: token_fingerprint.py <out.json>"""
import hashlib
import json
import os
import re
import sys

WINDOW = 16


def random_part(token):
    m = re.match(r"^(?:[A-Za-z0-9]+-){1,4}", token)
    return token[m.end():] if m and m.end() <= 20 else token


def main():
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    part = random_part(token).encode()
    if len(part) < 32:
        sys.exit("token missing or too short to fingerprint")
    hashes = sorted({hashlib.sha256(part[i:i + WINDOW]).hexdigest() for i in range(len(part) - WINDOW + 1)})
    with open(sys.argv[1], "w") as f:
        json.dump({"window": WINDOW, "hashes": hashes}, f)
    print("fingerprints: %d windows" % len(hashes))


if __name__ == "__main__":
    main()
