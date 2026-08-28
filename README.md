# ecos-release

Generates and publishes the POSIX ECC installer. End users still install with `curl | sh`; they do not need Nix.

Supported platform: Linux x86_64, glibc ≥ 2.34.

## Install ECC

```sh
curl -fsSL https://ecc-install-script.oss-cn-beijing.aliyuncs.com/installers/ecc/latest/ecc-installer.sh | sh
```

With OSS CAD Suite and the ICS55 PDK:

```sh
curl -fsSL https://ecc-install-script.oss-cn-beijing.aliyuncs.com/installers/ecc/latest/ecc-installer.sh | sh -s -- --with-toolchain
```

`--download-source auto|github|cnb` selects the mirror (`auto` tries GitHub, then CNB). The PDK base archive is GitHub-only.

If GitHub is unreachable, set a prefix that replaces `https://github.com`:

```sh
export ECC_GITHUB_BASE_URL=https://ghfast.top/https://github.com
curl -fsSL https://ecc-install-script.oss-cn-beijing.aliyuncs.com/installers/ecc/latest/ecc-installer.sh | sh
```

CNB URLs are not rewritten.

Data lands in `$XDG_DATA_HOME/ecc` (or `~/.local/share/ecc`). The wrapper goes to `$XDG_BIN_HOME` or `~/.local/bin`. `ECC_INSTALL_DIR` overrides the data root and must be an absolute path.

## Generate and publish

Pins live in `metadata/toolchain.toml`. The installer source is `templates/ecc-installer.sh.in`.

```sh
nix build .#ecc-installer          # write ecc-installer.sh; does not fetch real archives
nix run .#update-ecc -- v<tag>     # prefetch the ECC GitHub asset and update the [ecc] pin
nix run .#publish-oss -- v<tag>    # PUT the immutable versioned object; advance latest by SemVer 2.0.0
```

`update-ecc` only rewrites ECC pins. Bump OSS CAD Suite or PDK by editing the TOML.

Publishing needs `OSS_ACCESS_KEY_ID` and `OSS_ACCESS_KEY_SECRET`. A versioned object cannot be overwritten with different bytes. `latest` never moves to an older SemVer.

## `nix flake check`

Default checks do not download the real ECC, OSS CAD Suite, or PDK archives.

| check | What it covers |
|---|---|
| `semver` | SemVer 2.0.0 order: `0.1.0-alpha.10` < `alpha.11` < `0.1.0`; numeric ident `0`; build metadata ignored |
| `generate` | Render the installer from the current TOML; reject darwin / empty Liberty lists; no leftover placeholders |
| `publish` | `latest` policy: missing → advance, older → keep, same version + same bytes → keep, same version + different bytes → reject, malformed `ECC_VERSION` → reject |
| `archive` | `tarfile` safety on synthetic tars: traversal, absolute paths, control characters, escaping links, FIFOs, empty Liberty inventories |
| `installer-syntax` | `dash -n`, `bash -n`, and `shellcheck -s dash -S error` on the generated script |
| `installer-e2e` | Fake archives over local HTTP: GitHub success, GitHub failure then CNB, checksum mismatch, unsupported platform, wrapper env, lock, receipt, toolchain fallback |

`nix develop` provides `nixfmt`, `dash`, and `shellcheck`.
