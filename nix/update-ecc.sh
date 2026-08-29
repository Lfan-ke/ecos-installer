#!/usr/bin/env bash
set -euo pipefail

tag="${1:?usage: update-ecc <github-tag>}"
version="${tag#v}"

root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
toml="$root/metadata/toolchain.toml"
if [[ ! -f $toml ]]; then
  echo "metadata/toolchain.toml not found (run from the ecos-release checkout)" >&2
  exit 1
fi

toml_get() {
  sed -n "s/^$1 = \"\\(.*\\)\"/\\1/p" "$toml" | head -n1
}

repo="$(toml_get github_repo)"
name="$(toml_get asset_name)"
template="$(toml_get cnb_url_template)"
url="https://github.com/${repo}/releases/download/${tag}/${name}"
cnb="${template//\{tag\}/$tag}"
cnb="${cnb//\{name\}/$name}"

prefetch="$(nix-prefetch-url --print-path --type sha256 --name "$name" "$url")"
nix32="$(printf '%s\n' "$prefetch" | sed -n '1p')"
store_path="$(printf '%s\n' "$prefetch" | sed -n '2p')"
sha="$(nix hash convert --from nix32 --to base16 --hash-algo sha256 "$nix32" | tr 'A-F' 'a-f')"
size="$(stat -c '%s' "$store_path")"

tmp="$(mktemp)"
awk -v ver="$version" -v url="$url" -v cnb="$cnb" -v sha="$sha" -v size="$size" '
  function key_of(line,   k) {
    k = line
    sub(/[ \t]*=.*/, "", k)
    gsub(/^[ \t]+|[ \t]+$/, "", k)
    return k
  }
  $0 == "[ecc]" { in_ecc = 1; print; next }
  in_ecc && /^\[/ { in_ecc = 0 }
  in_ecc && $0 ~ /^[ \t]*[A-Za-z0-9_]+[ \t]*=/ && $0 !~ /^[ \t]*#/ {
    k = key_of($0)
    if (k == "version") { print "version = \"" ver "\""; seen[k] = 1; next }
    if (k == "url") { print "url = \"" url "\""; seen[k] = 1; next }
    if (k == "cnb_url") { print "cnb_url = \"" cnb "\""; seen[k] = 1; next }
    if (k == "sha256") { print "sha256 = \"" sha "\""; seen[k] = 1; next }
    if (k == "size") { print "size = " size; seen[k] = 1; next }
  }
  { print }
  END {
    n = split("version url cnb_url sha256 size", keys, " ")
    for (i = 1; i <= n; i++) {
      if (!seen[keys[i]]) {
        printf "missing [ecc] key %s\n", keys[i] > "/dev/stderr"
        err = 1
      }
    }
    exit err
  }
' "$toml" >"$tmp"
mv "$tmp" "$toml"
echo "updated $toml for $tag"
