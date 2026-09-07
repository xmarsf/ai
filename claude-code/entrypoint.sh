#!/bin/sh
# Re-run rtk's installer on every container start so the binary in the
# (volume-backed, user-owned) install dir stays current — rtk has no
# self-update command, this is the auto-update substitute.
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh || true

# ~/.claude/plugins lives in a volume (claude-plugins or the whole
# /home/node mount), so anything installed at image-build time is
# shadowed at runtime. Install/update skills here instead, on every
# start, same reasoning as rtk above.
claude plugin marketplace add JuliusBrussee/caveman || true
claude plugin install caveman@caveman -y || true
claude plugin marketplace add anthropics/claude-plugins-official || true
claude plugin install superpowers@claude-plugins-official -y || true

exec "$@"
