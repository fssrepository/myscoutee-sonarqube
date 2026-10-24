#!/usr/bin/env bash
set -euo pipefail

sonar_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
usage() {
  echo 'Usage: run.sh SOURCE_REPOSITORY init|up|stop|down|status|logs|check|scan [all|backend|frontend|components|microservices|runtime] [--source-only]'
}
if [[ $# -lt 2 || ${1:-} == --help || ${1:-} == -h ]]; then
  usage
  [[ $# -lt 2 && ${1:-} != --help && ${1:-} != -h ]] && exit 2
  exit 0
fi

# Resolve the caller's path before changing directory to the central tool.
export SONAR_SOURCE_ROOT="$(cd -- "$1" && pwd -P)"
settings="$(python3 "$sonar_dir/project.py" "$SONAR_SOURCE_ROOT")"
mapfile -t project_settings <<< "$settings"
project_id="${project_settings[0]}"
export SONAR_COMPOSE_PROJECT="${project_settings[1]}" SONAR_PORT="${project_settings[2]}"
export SONAR_STATE_ROOT="$sonar_dir/.state/$project_id"
server_id="${project_settings[8]}"
server_state="$sonar_dir/.state/$server_id"
export SCANNER_UID="$(id -u)" SCANNER_GID="$(id -g)"
action="$2"
shift 2
cd "$sonar_dir"
umask 077
mkdir -p "$SONAR_STATE_ROOT" "$server_state"
chmod 0700 "$sonar_dir/.state" "$SONAR_STATE_ROOT" "$server_state"
compose=(docker compose --project-name "$SONAR_COMPOSE_PROJECT" --project-directory "$sonar_dir"
  --env-file "$server_state/.env" -f "$sonar_dir/compose.yaml")

case "$action" in
  init)
    if [[ -e "$server_state/.env" ]]; then
      echo "Private settings for shared server $server_id already exist; left unchanged."
      exit 0
    fi
    SONAR_SERVER_STATE_ROOT="$server_state" python3 - <<'PY'
import os
from pathlib import Path
import secrets
with (Path(os.environ['SONAR_SERVER_STATE_ROOT']) / '.env').open('x') as env:
    env.write(f'SONAR_DB_PASSWORD={secrets.token_hex(24)}\nSONAR_TOKEN=\n')
PY
    echo "Created private settings for shared server $server_id. Add an analysis token after the first UI login."
    ;;
  up)
    if [[ -r /proc/sys/vm/max_map_count ]] && (( $(</proc/sys/vm/max_map_count) < 524288 )); then
      echo "SonarQube requires vm.max_map_count >= 524288. Run: sudo bash $sonar_dir/setup-host.sh" >&2
      exit 1
    fi
    "${compose[@]}" up -d --wait --wait-timeout 360 database sonarqube
    ;;
  stop) "${compose[@]}" stop ;;
  down) "${compose[@]}" down ;;
  status) "${compose[@]}" ps -a ;;
  logs) "${compose[@]}" logs --tail 100 database sonarqube ;;
  check)
    "${compose[@]}" config --quiet
    echo "Configuration valid: $project_id, Compose $SONAR_COMPOSE_PROJECT, localhost:$SONAR_PORT"
    ;;
  scan)
    source_only=false
    if [[ ${2:-} == --source-only && $# -eq 2 ]]; then
      source_only=true
    elif (( $# > 1 )); then
      usage >&2
      exit 2
    fi
    case "${1:-all}" in
      all)
        modules=()
        module_names=(backend frontend components microservices runtime)
        for index in "${!module_names[@]}"; do
          if [[ -n "${project_settings[$((index + 3))]:-}" ]]; then
            modules+=("${module_names[$index]}")
          fi
        done
        ;;
      backend|frontend|components|microservices|runtime) modules=("$1") ;;
      *) usage >&2; exit 2 ;;
    esac
    for module in "${modules[@]}"; do
      case "$module" in
        backend) source_dir="${project_settings[3]:-}" ;;
        frontend) source_dir="${project_settings[4]:-}" ;;
        components) source_dir="${project_settings[5]:-}" ;;
        microservices) source_dir="${project_settings[6]:-}" ;;
        runtime) source_dir="${project_settings[7]:-}" ;;
      esac
      if [[ -z "$source_dir" ]]; then
        echo "$module is not configured in this source repository; scan its owning repository." >&2
        exit 1
      fi
    done
    # One scan owner across every source project, including preparation and CE polling.
    exec {scan_lock}> "$sonar_dir/.state/scan.lock"
    if ! flock -n "$scan_lock"; then
      echo 'Another central Sonar scan is running. Finish or stop its owner before starting another.' >&2
      exit 1
    fi
    scanner_name=""
    cleanup_scan() {
      local status=$?
      trap - EXIT
      if [[ -n "$scanner_name" ]]; then
        docker stop --timeout 10 "$scanner_name" >/dev/null 2>&1 || true
        docker rm "$scanner_name" >/dev/null 2>&1 || true
      fi
      exit "$status"
    }
    trap cleanup_scan EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    "${compose[@]}" exec -T sonarqube sh -c \
      'curl -fsS http://localhost:9000/api/system/status | grep -q '\''"status":"UP"'\''' || {
      echo 'SonarQube is not ready. Start the shared server explicitly with run.sh SOURCE_REPOSITORY up.' >&2
      exit 1
    }
    mkdir -p "$SONAR_STATE_ROOT/build/analysis" "$SONAR_STATE_ROOT/build/cache"
    for module in "${modules[@]}"; do
      scanner_mounts=()
      scanner_options=()
      # Runtime data is outside the analysis input. Python package discovery also
      # traverses non-source paths, so enforce that boundary at the scanner mount.
      for private_directory in "${project_settings[@]:9}"; do
        if [[ -d "$SONAR_SOURCE_ROOT/$private_directory" ]]; then
          mkdir -p "$SONAR_STATE_ROOT/build/private-runtime"
          scanner_mounts+=(--volume "$SONAR_STATE_ROOT/build/private-runtime:/workspace/$private_directory:ro")
        fi
      done
      case "$module" in
        backend)
          python3 prepare-backend.py
          source_dir="${project_settings[3]}"
          if [[ -n "${BACKEND_COVERAGE_REPORT:-}" ]]; then
            scanner_options+=("-Dsonar.coverage.jacoco.xmlReportPaths=/analysis/backend/coverage.xml")
          fi
          ;;
        frontend) source_dir="${project_settings[4]}" ;;
        components) source_dir="${project_settings[5]}" ;;
        runtime) source_dir="${project_settings[7]}" ;;
        microservices)
          python3 prepare-backend.py microservices
          python3 prepare-helm.py
          scanner_mounts+=(
            --volume "$SONAR_STATE_ROOT/build/helm/values.json:/workspace/config/microservices/chart/values.yaml:ro"
            --volume "$SONAR_STATE_ROOT/build/helm/git:/workspace/.git:ro"
            --volume "$(cat "$SONAR_STATE_ROOT/build/helm/origin-objects.path"):/scm-objects:ro"
          )
          scanner_options+=("-Dsonar.scm.revision=$(cat "$SONAR_STATE_ROOT/build/helm/source-revision")")
          if [[ -n "${MICROSERVICES_COVERAGE_REPORT:-}" ]]; then
            scanner_options+=("-Dsonar.coverage.jacoco.xmlReportPaths=/analysis/microservices/coverage.xml")
          fi
          source_dir="${project_settings[6]}"
          ;;
      esac
      if [[ "$source_only" == true ]]; then
        # A source review must not require or synthesize test artifacts. Normal
        # scans retain the native report paths from the versioned properties.
        scanner_options+=(
          -Dsonar.testExecutionReportPaths=
          -Dsonar.junit.reportPaths=
          -Dsonar.javascript.lcov.reportPaths=
          -Dsonar.coverage.jacoco.xmlReportPaths=
        )
      fi
      scanner_name="$SONAR_COMPOSE_PROJECT-scanner-$$"
      "${compose[@]}" --profile scan run --rm --no-deps --name "$scanner_name" "${scanner_mounts[@]}" \
        --env "SCANNER_WORKDIR_PATH=/analysis/scanner/$module" scanner \
        "-Dproject.settings=/config/$module.properties" \
        "-Dsonar.projectBaseDir=/workspace/$source_dir" \
        "${scanner_options[@]}" &
      scanner_pid=$!
      wait "$scanner_pid"
      scanner_name=""
      "${compose[@]}" --profile scan config --format json | python3 wait-analysis.py "$module"
    done
    ;;
  help|--help|-h) usage ;;
  *) usage >&2; exit 2 ;;
esac
