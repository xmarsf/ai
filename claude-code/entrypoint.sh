#!/bin/sh
# Re-run rtk's installer on every container start so the binary in the
# (volume-backed, user-owned) install dir stays current — rtk has no
# self-update command, this is the auto-update substitute.
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh || true
exec "$@"
