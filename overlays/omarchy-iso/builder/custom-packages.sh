#!/bin/bash
# Data-only package lists shared by both stages of the local ISO builder.
CUSTOM_LOCAL_PACKAGES=()
CUSTOM_BUILD_DEPENDENCIES=()
CUSTOM_BUILD_INSTALL_PACKAGES=()

read_custom_package_list() {
  local list_path=$1
  local -n names=$2
  local entry existing
  while IFS= read -r entry || [[ -n $entry ]]; do
    [[ -n $entry && $entry != \#* ]] || continue
    if [[ ! $entry =~ ^[A-Za-z0-9][A-Za-z0-9@._+-]*$ ]]; then
      printf 'Invalid package name in %s: %s\n' "$list_path" "$entry" >&2
      return 1
    fi
    for existing in "${names[@]}"; do
      if [[ $existing == "$entry" ]]; then
        printf 'Duplicate package in %s: %s\n' "$list_path" "$entry" >&2
        return 1
      fi
    done
    names+=("$entry")
  done < "$list_path"
}

read_custom_package_list /builder/custom-local.packages CUSTOM_LOCAL_PACKAGES
read_custom_package_list /builder/custom-build-dependencies.packages CUSTOM_BUILD_DEPENDENCIES
read_custom_package_list /builder/custom-build-install.packages CUSTOM_BUILD_INSTALL_PACKAGES
for provider in "${CUSTOM_BUILD_INSTALL_PACKAGES[@]}"; do
  found=0
  for local_name in "${CUSTOM_LOCAL_PACKAGES[@]}"; do
    [[ $provider != "$local_name" ]] || found=1
  done
  if (( ! found )); then
    printf 'Local build provider is not in custom-local.packages: %s\n' "$provider" >&2
    exit 1
  fi
done
