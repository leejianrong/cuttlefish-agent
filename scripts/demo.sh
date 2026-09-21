#!/usr/bin/env bash
# Bring up a fleet daemon + the dashboard together, one command:  make demo
# (or directly: ./scripts/demo.sh). Ctrl-C stops both.
#
# dev-playbook's own "runnable in one command" guidance: this is meant to be the
# first thing a newcomer (or an agent) runs to actually see the dashboard, not a
# recipe for assembling two separate commands by hand. `cuttlefish serve` itself
# already auto-picks a free port if its default is taken (find_free_port,
# cuttlefish.fleet.server) -- this script doesn't need its own port-juggling logic
# for that half; it only has to read back whichever port/token the daemon printed.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
daemon_log="$(mktemp)"
daemon_pid=""

cleanup() {
	if [ -n "$daemon_pid" ] && kill -0 "$daemon_pid" 2>/dev/null; then
		kill "$daemon_pid" 2>/dev/null || true
		wait "$daemon_pid" 2>/dev/null || true
	fi
	rm -f "$daemon_log"
}
trap cleanup EXIT INT TERM

if [ ! -d "$repo_root/frontend/node_modules" ]; then
	echo "Installing dashboard dependencies (frontend/node_modules missing)…"
	( cd "$repo_root/frontend" && npm install )
fi

echo "Starting the fleet daemon…"
( cd "$repo_root" && exec uv run cuttlefish serve ) >"$daemon_log" 2>&1 &
daemon_pid=$!

# Bounded wait for the daemon's own startup line -- never an indefinite hang.
daemon_line=""
for _ in $(seq 1 50); do
	if ! kill -0 "$daemon_pid" 2>/dev/null; then
		echo "cuttlefish serve exited before starting -- see output below:" >&2
		cat "$daemon_log" >&2
		exit 1
	fi
	daemon_line="$(grep '^cuttlefish serve:' "$daemon_log" 2>/dev/null || true)"
	[ -n "$daemon_line" ] && break
	sleep 0.2
done

if [ -z "$daemon_line" ]; then
	echo "cuttlefish serve didn't print its startup line in time -- see output below:" >&2
	cat "$daemon_log" >&2
	exit 1
fi

echo
echo "  $daemon_line"
echo
echo "Starting the dashboard (npm run dev)…"
echo "Open the URL it prints, then paste the base URL and token above into the"
echo "connect screen -- or click \"See the sprites first\" to preview the pixel-art"
echo "sprites with no daemon connection at all."
echo

cd "$repo_root/frontend"
npm run dev
