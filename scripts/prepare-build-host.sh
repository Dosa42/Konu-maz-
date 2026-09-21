#!/usr/bin/env bash
# Prepare the Linux host for the real privileged Arch ISO builder.
# Arch package/build dependencies are installed by builder/build-iso.sh inside
# its container; this script only manages the host-side command-line tools.
set -euo pipefail

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ $(uname -s) == Linux ]] || die 'The ISO builder requires a Linux host.'
case "$(uname -m)" in
  x86_64 | amd64) ;;
  *) die 'This Omarchy ISO profile requires an x86_64 host.' ;;
esac

root_cmd=()
if ((EUID != 0)); then
  if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    root_cmd=(sudo -n)
  fi
fi

require_root() {
  if ((EUID != 0 && ${#root_cmd[@]} == 0)); then
    die 'Installing missing packages or cleaning the hosted runner requires root or noninteractive sudo.'
  fi
}

# A Docker client without a reachable daemon cannot run mkarchiso. Do not
# install a replacement client/daemon or change host Docker permissions here.
command -v docker >/dev/null 2>&1 || die 'Docker CLI is missing. Install Docker Engine before running this build.'
docker_cmd=(docker)
if ! docker_error=$(docker info --format '{{.ServerVersion}}' 2>&1); then
  if ((${#root_cmd[@]} > 0)) && sudo_docker_error=$("${root_cmd[@]}" docker info --format '{{.ServerVersion}}' 2>&1); then
    docker_cmd=("${root_cmd[@]}" docker)
  else
    printf 'Docker daemon check failed:\n%s\n' "$docker_error" >&2
    if [[ -n ${sudo_docker_error:-} ]]; then
      printf 'Docker check with sudo also failed:\n%s\n' "$sudo_docker_error" >&2
    fi
    die 'A running, accessible Docker Engine is required; no Docker settings were changed.'
  fi
fi

docker_os=$("${docker_cmd[@]}" info --format '{{.OSType}}')
docker_arch=$("${docker_cmd[@]}" info --format '{{.Architecture}}')
[[ $docker_os == linux ]] || die "Docker must use Linux containers; daemon reports: $docker_os"
case "$docker_arch" in
  x86_64 | amd64) ;;
  *) die "Docker must run this ISO build on x86_64; daemon reports: $docker_arch" ;;
esac

required_tools=(git curl jq xorriso zstd python3 rsync)
missing_tools=()
for tool in "${required_tools[@]}"; do
  command -v "$tool" >/dev/null 2>&1 || missing_tools+=("$tool")
done

if ((${#missing_tools[@]} > 0)); then
  if ! command -v apt-get >/dev/null 2>&1; then
    printf 'Missing host tools: %s\n' "${missing_tools[*]}" >&2
    die 'Install these tools with your Linux distribution package manager, then rerun this script.'
  fi
  require_root
  "${root_cmd[@]}" apt-get update
  "${root_cmd[@]}" apt-get install --yes --no-install-recommends \
    ca-certificates git curl jq xorriso zstd python3 rsync
fi

for tool in "${required_tools[@]}"; do
  command -v "$tool" >/dev/null 2>&1 || die "Required host tool is still missing: $tool"
done
if command -v shellcheck >/dev/null 2>&1; then
  printf 'Optional ShellCheck: %s\n' "$(command -v shellcheck)"
else
  printf 'Optional ShellCheck is not installed; it is not required to build the ISO.\n'
fi

# These SDKs are unrelated to the ISO build. Only reclaim their space on a
# disposable GitHub-hosted runner, never on a local or self-hosted machine.
if [[ ${RUNNER_ENVIRONMENT:-} == github-hosted ]]; then
  cleanup_dirs=(
    /usr/local/lib/android
    /opt/ghc
    /usr/local/.ghcup
    /usr/share/dotnet
    /opt/hostedtoolcache/CodeQL
  )
  for unused_dir in "${cleanup_dirs[@]}"; do
    if [[ -e $unused_dir ]]; then
      require_root
      printf 'Reclaiming disposable runner space: %s\n' "$unused_dir"
      "${root_cmd[@]}" rm -rf -- "$unused_dir"
    fi
  done
fi

printf '\nDocker build environment:\n'
"${docker_cmd[@]}" version --format 'Client={{.Client.Version}} Server={{.Server.Version}}'
"${docker_cmd[@]}" info --format 'Driver={{.Driver}} DockerRootDir={{.DockerRootDir}} Architecture={{.Architecture}}'

report_space() {
  local space_path=$1
  local space_label=$2
  local space_output available_kib
  printf '\n%s storage:\n' "$space_label"
  if space_output=$(df -Pk -- "$space_path" 2>&1); then
    printf '%s\n' "$space_output"
    available_kib=$(awk 'NR == 2 {print $4}' <<< "$space_output")
    if [[ $available_kib =~ ^[0-9]+$ ]] && ((available_kib < 35 * 1024 * 1024)); then
      printf 'Advisory: %s has less than 35 GiB free. The ISO, offline mirror and container build share disk space; monitor the actual build.\n' "$space_label" >&2
    fi
  else
    printf 'Could not inspect %s on this host: %s\n' "$space_path" "$space_output" >&2
  fi
}

report_space "$PWD" 'Workspace'
docker_root=$("${docker_cmd[@]}" info --format '{{.DockerRootDir}}')
if [[ -n $docker_root ]]; then
  report_space "$docker_root" 'Docker'
fi

printf '\nHost dependencies are ready. The ISO builder installs its Arch dependencies inside the container.\n'
