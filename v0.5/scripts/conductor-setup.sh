#!/bin/sh
# Project-scoped setup; no interactive shell initialization or global installs.
set -u
fail() { printf '%s\n' "Playbook setup: $*" >&2; exit 2; }
case "${CONDUCTOR_IS_LOCAL-}" in
  0|1) ;;
  *) fail 'restore CONDUCTOR_IS_LOCAL=1 (local) or 0 (Cloud) from the host, then retry.' ;;
esac
command -v python3 >/dev/null 2>&1 || fail 'Python 3.9+ is missing from PATH; restore the noninteractive setup toolchain and retry.'
python3 -B -c 'import sys, json, zipfile, pathlib, subprocess; sys.exit(0 if sys.version_info >= (3,9) else 2)' >/dev/null 2>&1 || fail 'Python 3.9+ and its standard-library dependencies are required; restore a compatible noninteractive toolchain and retry.'
case "$#:${1-}" in
  0:) set -- .playbook/provision.pyz --project . ;;
  1:--candidate) set -- v0.5/scripts/recover-playbook-source.py --project . --source . --candidate ;;
  *) fail 'use the adopted consumer hook without arguments, or explicit --candidate in the maintainer checkout.' ;;
esac
[ -f "$1" ] && [ ! -L "$1" ] || fail 'restore the regular adopted launcher or maintainer setup entry; preserve conflicting endpoints before retrying.'
if [ "$1" = .playbook/provision.pyz ]; then
  cache_root=${XDG_CACHE_HOME:-${HOME:+$HOME/.cache}}
  if [ "$CONDUCTOR_IS_LOCAL" = 0 ]; then
    [ -n "$cache_root" ] || fail 'restore HOME or an absolute XDG_CACHE_HOME for the separate exact-source cache.'
    case "$cache_root" in /*) ;; *) fail 'use an absolute HOME/XDG_CACHE_HOME for the separate exact-source cache.' ;; esac
    set -- "$@" --acquire --cache-dir "$cache_root/agentic-engineering-playbook/sources"
  else
    # Local discovery may reuse an explicitly recovered exact source; it never downloads.
    case "$cache_root" in /*) set -- "$@" --cache-dir "$cache_root/agentic-engineering-playbook/sources" ;; esac
  fi
fi
python3 -B "$@" setup
result=$?
[ "$result" -eq 0 ] || printf '%s\n' 'Playbook setup incomplete; follow the source/inventory repair above, or restore the adopted launcher if it could not start. Preserve project customizations and retry; runtime qualification remains unverified.' >&2
exit "$result"
