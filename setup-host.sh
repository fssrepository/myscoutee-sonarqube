#!/usr/bin/env bash
set -euo pipefail

# Run on the Linux Docker host. This changes only SonarQube's mmap prerequisite.
if [[ "$(id -u)" != 0 ]]; then
  echo "Run with administrator privileges: sudo bash $0" >&2
  exit 1
fi
if [[ ! -r /proc/sys/vm/max_map_count ]]; then
  echo 'Run this script on the Linux host that runs Docker.' >&2
  exit 1
fi

current="$(</proc/sys/vm/max_map_count)"
target=524288
if (( current > target )); then
  target="$current"
fi
install -d -m 0755 /etc/sysctl.d
config=/etc/sysctl.d/99-myscoutee-sonarqube.conf
if [[ -e "$config" ]]; then
  saved="$(sed -n 's/^vm.max_map_count[[:space:]]*=[[:space:]]*\([0-9]*\)[[:space:]]*$/\1/p' "$config")"
  if [[ "$saved" =~ ^[0-9]+$ ]] && (( saved > target )); then
    target="$saved"
  fi
fi
printf '# Local SonarQube Elasticsearch requirement.\nvm.max_map_count=%s\n' "$target" > "$config"
chmod 0644 "$config"
sysctl -p "$config"
echo "Persisted in $config; active now and after reboot."
