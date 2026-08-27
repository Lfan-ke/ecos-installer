# ECC Installer Design

## Status

Draft design for review before implementing the public ECC installer.

This document belongs to the standalone `ecos-release` repository. The ECC
source repository remains the producer of the PyInstaller release bundle and
does not own the installer template, generator, tests, or OSS publication.

## Goals

- Provide a browser-readable POSIX shell installer at a stable public URL.
- Install the ECC PyInstaller `onedir` bundle without requiring Python.
- Support a lightweight default install and an optional complete toolchain
  install.
- Prefer GitHub Release assets and fall back to CNB when GitHub is unavailable.
- Follow XDG directory conventions without modifying shell profiles by default.
- Make upgrades transactional and retain the current and immediately previous
  ECC versions.
- Generate one immutable installer per ECC version, with `latest` as a copy of
  the newest successfully published installer.

## Non-Goals

- The first release does not support macOS, Windows, ARM64, musl, or glibc older
  than 2.34.
- The first release does not provide `ecc self update` or an uninstaller.
- The first release does not mirror OSS CAD Suite or the ICS55 PDK to CNB.
- The installer does not modify the ECC source repository or put installer
  tests in that repository.
- The installer does not determine the user's country or geographic region.
- The installer does not make an installed Yosys globally shadow a system
  Yosys command.

## Repository Ownership

The ECC source repository owns:

- `ecc-cli-linux-x86_64.tar.gz` production and smoke testing.
- GitHub Release publication.
- The public Release Asset API contract used to discover the asset URL, size,
  and `sha256:` digest.

The `ecos-release` repository owns:

- The installer template and generator.
- Installer metadata for ECC, OSS CAD Suite, and the ICS55 PDK.
- Installer syntax and behavior tests.
- GitHub and CNB availability checks.
- Versioned installer and `latest` publication to OSS.

The ECC repository does not need to publish a separate `SHA256SUMS` asset.
GitHub's Release Asset API digest is the checksum source for ECC. The generated
installer embeds that digest, so installer execution does not call the GitHub
API.

## Public URLs

The initial OSS host is:

```text
https://ecc-install-script.oss-cn-beijing.aliyuncs.com
```

Installer objects use these paths:

```text
/installers/ecc/v0.1.0-alpha.11/ecc-installer.sh
/installers/ecc/latest/ecc-installer.sh
```

The versioned object is immutable. `latest` is the exact same generated file as
the newest versioned object and is updated only after all publication checks
pass. A future custom domain changes only the publication base URL, not the
object paths or installer behavior.

## Generation Model

Each versioned installer is generated from a template. Generation input is a
validated release model containing:

- ECC version.
- Supported platform and minimum glibc version.
- GitHub and CNB asset URLs.
- ECC asset name, size, and SHA-256 digest.
- OSS CAD Suite version, URL, archive name, and digest.
- ICS55 PDK version, base archive metadata, and seven supplemental asset
  records.

The generated script is self-contained. It does not fetch a manifest at install
time. Repeated generation from identical input must produce identical bytes.

The GitHub ECC metadata comes from the exact tag endpoint:

```text
GET https://api.github.com/repos/openecos-projects/ecc/releases/tags/<tag>
```

Generation selects an uploaded asset named exactly
`ecc-cli-linux-x86_64.tar.gz`. The `digest` must match
`sha256:[0-9a-f]{64}`. CNB must serve an asset for the same tag and name. Before
publication, `ecos-release` verifies that the CNB bytes match the GitHub digest.

## Command Interface

Default installation:

```sh
curl -fsSL \
  https://ecc-install-script.oss-cn-beijing.aliyuncs.com/installers/ecc/latest/ecc-installer.sh \
  | sh
```

ECC plus OSS CAD Suite and ICS55 PDK:

```sh
curl -fsSL \
  https://ecc-install-script.oss-cn-beijing.aliyuncs.com/installers/ecc/latest/ecc-installer.sh \
  | sh -s -- --with-toolchain
```

Supported options:

```text
-h, --help
-v, --verbose
-q, --quiet
--with-toolchain
--modify-path
--download-source auto|github|cnb
```

Supported environment variables:

```text
ECC_WITH_TOOLCHAIN=1
ECC_MODIFY_PATH=1
ECC_DOWNLOAD_SOURCE=auto|github|cnb
ECC_INSTALL_DIR=/absolute/path/to/ecc-data
```

For a pipeline, environment variables that affect the installer must be set on
the shell process:

```sh
curl -fsSL <installer-url> | ECC_DOWNLOAD_SOURCE=cnb sh
```

CLI arguments override environment variables. Unknown options, invalid enum
values, or conflicting quiet and verbose settings fail before filesystem
mutation.

## Shell Compatibility

The generated installer is POSIX `sh` and must run under at least `dash` and
`bash` in POSIX mode. It must not depend on `[[`, `BASH_SOURCE`, arrays,
associative arrays, or the non-POSIX `source` command.

The installer requires `curl`, `uname`, `mktemp`, `mkdir`, `mv`, `rm`, `tar`,
`sha256sum`, `grep`, `sed`, `awk`, `head`, and `tail`. Toolchain installation
also requires `git`, `make`, `bzip2`, `find`, and `cp`. Missing requirements are
reported before starting the relevant phase.

## Platform Detection

The first generated installer supports only Linux x86_64 with glibc 2.34 or
newer. Detection follows the relevant principles from the uv installer while
remaining limited to the one platform ECC actually publishes:

1. Use `uname -s` for the operating system.
2. Use `uname -m` and normalize `x86_64`, `x86-64`, `x64`, and `amd64`.
3. On Linux, inspect the ELF class byte of `/proc/self/exe` to detect the actual
   userland bitness instead of trusting a 64-bit kernel report.
4. Use `ldd --version` to reject musl and obtain the glibc version.
5. Compare glibc major and minor components numerically against 2.34.
6. After extraction, execute the real ECC binary. Runtime smoke tests remain
   authoritative even after a successful preflight check.

Unsupported systems fail with the detected OS, CPU, libc, and libc version in
the error message. There is no automatic pip, source-build, container, or Nix
fallback.

## XDG Layout

Paths are resolved as follows:

```text
ECC data root:
  ${ECC_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/ecc}

Binary directory:
  ${XDG_BIN_HOME:-$HOME/.local/bin}

Cache root:
  ${XDG_CACHE_HOME:-$HOME/.cache}/ecc
```

`XDG_BIN_HOME` is treated as a commonly used extension; the default remains
`$HOME/.local/bin`. An unset or empty `HOME` is an error unless all required
roots are explicitly configured.

The managed data layout is:

```text
<data-root>/
├── v0.1.0-alpha.10/
│   ├── ecc
│   ├── _internal/
│   └── .ecos-release-receipt
├── v0.1.0-alpha.11/
│   ├── ecc
│   ├── _internal/
│   └── .ecos-release-receipt
├── tools/
│   └── oss-cad-suite/
│       └── 20260808/
├── pdks/
│   └── icsprout55/
│       └── v1.10.102/
└── env
```

The cache stores downloads by expected SHA-256 rather than mutable filename:

```text
<cache-root>/downloads/<sha256>.tar.gz
<cache-root>/downloads/<sha256>.tar.bz2
```

## Launcher and Environment Isolation

`<bin-dir>/ecc` is a small generated POSIX launcher rather than a copy of the
PyInstaller executable. It optionally reads the installer-owned `<data-root>/env`
file, then executes the selected version's real binary with all arguments. The
launcher contains an installer-owned, machine-readable version assignment. It is
the only current-version pointer; no parallel state file is maintained.

When the optional toolchain is complete, `env` exports:

```text
CHIPCOMPILER_OSS_CAD_DIR
YOSYS_PLUGINPATH
CHIPCOMPILER_ICS55_PDK_ROOT
PATH=<managed OSS CAD Suite bin>:$PATH
```

These values affect only an ECC process launched through the wrapper. The
installer does not create `<bin-dir>/yosys` and does not globally prepend the
managed Yosys directory. A user who intentionally wants direct tool access may
run:

```sh
. <data-root>/env
yosys --version
```

The launcher and env files use safely quoted absolute paths and are installed
through temporary files followed by same-directory `mv`.

## Shell Profile Policy

The default installation never modifies a shell profile. If `<bin-dir>` is not
already in `PATH`, the installer prints a command for the current shell.

Profile mutation occurs only with `--modify-path` or `ECC_MODIFY_PATH=1`. The
installer uses the basename of `SHELL` to select one file:

```text
sh:    ~/.profile
bash:  ~/.bashrc
zsh:   ~/.zshrc
fish:  ~/.config/fish/conf.d/ecc.env.fish
```

Known Bourne-style profiles receive one marked, idempotent block. Fish receives
equivalent fish syntax. An unknown shell is not modified; the installer prints
manual instructions. Failure to update a requested profile is reported after a
successful install and returns a nonzero status without rolling back ECC.

## Source Selection and Downloading

The installer does not infer geography. `auto` means ordered availability
fallback:

1. Try the exact GitHub Release asset URL, following its redirect to the real
   asset host.
2. On connection failure, HTTP failure, retry exhaustion, or sustained low
   transfer speed, try the exact CNB Release asset URL.
3. Verify the completed file against the one embedded SHA-256 digest.

An optional short request to the exact asset URL may be used to avoid selecting
an obviously unavailable source, but a successful probe never replaces real
download error handling. Testing only `github.com` is insufficient because the
redirected release asset host may be blocked.

Downloads use a source-specific partial file. A failed source's partial bytes
are not resumed from another source. A checksum mismatch deletes the candidate,
prints a high-visibility integrity error, and may try the next configured source.
No unverified archive is extracted or executed.

`github` and `cnb` source modes disable fallback and are intended for diagnosis,
CI, and constrained networks.

The initial CNB fallback applies only to the ECC PyInstaller bundle. OSS CAD
Suite and PDK assets remain GitHub-only until their CNB mirrors are published.
Consequently, `--download-source cnb --with-toolchain` downloads ECC from CNB
but reports and downloads the toolchain assets from their only available GitHub
source. Adding toolchain mirrors later extends metadata and source lists without
changing the command interface.

## Transactional ECC Installation

ECC installation follows these phases:

1. Validate options, commands, platform, and writable roots.
2. Reuse a cache entry only after SHA-256 verification.
3. Download to a `.part` file and atomically promote it into the cache.
4. Inspect tar members and reject absolute paths, parent traversal, and other
   entries that would escape the staging directory.
5. Extract into a temporary directory under the ECC data root.
6. Verify the expected `ecc` and `_internal` layout.
7. Run `ecc --version`, `ecc version --json`, and verify that
   `_internal/torch/bin/torch_shm_manager` is executable.
8. Write the version receipt.
9. Atomically rename the staging directory to the version directory.
10. Atomically replace the launcher. This replacement is the transaction's
    commit point.

An existing same-version directory is reused only when its receipt matches the
expected artifact digest and the runtime smoke tests still pass. Otherwise it
is replaced transactionally.

Before switching the launcher, the installer reads the prior version only from
an existing launcher whose owned marker and structure validate. After a
successful switch it retains the new current version and that prior version. It
removes older directories only when they contain a valid installer-owned
receipt. If no valid owned launcher exists, cleanup is skipped. Unknown
directories and files are never deleted.

Installing a fixed older version is supported by running that version's
installer. Users may also execute an installed older version directly at
`<data-root>/<version>/ecc`.

Any failure before launcher replacement leaves the existing current ECC
unchanged. A trap removes temporary files without deleting verified cache
entries or prior installed versions.

## Optional Toolchain Installation

`--with-toolchain` installs OSS CAD Suite and the ICS55 PDK after the ECC bundle
has passed its own installation transaction. A toolchain failure does not roll
back a successfully installed ECC CLI.

An ECC-only install leaves an existing valid `<data-root>/env` and toolchain
untouched, so an ECC upgrade continues to use the previously installed shared
toolchain.

Each component uses its own staging directory, digest verification, extraction,
and final validation. Existing complete versions are shared across ECC versions
and reused.

OSS CAD Suite validation requires at least:

```text
bin/yosys is executable
share/yosys/plugins exists
```

The ICS55 PDK release consists of a base archive and seven supplemental assets.
Every archive is verified before extraction. The three Liberty archives are:

```text
ics55_LLSC_H7CH_liberty.tar.bz2
ics55_LLSC_H7CL_liberty.tar.bz2
ics55_LLSC_H7CR_liberty.tar.bz2
```

For each verified Liberty archive, the installer obtains the complete `.lib`
member list with `tar -tjf` before extraction. It rejects unsafe member paths and
an archive with no `.lib` members. After the PDK's official unpack step, every
listed Liberty file must exist and be non-empty. This validates the PDK release
contents and does not depend on ECC's `sta_ecc.json` flow configuration.

The installer also validates the tech LEF and standard-cell LEFs required by
ECC's PDK contract. Only after both OSS CAD Suite and PDK validation pass does
the installer atomically update `<data-root>/env`. If either component fails,
an existing env file and existing complete toolchain remain unchanged.

The final command exits nonzero and clearly reports that ECC succeeded but the
optional toolchain failed.

## Testing in ecos-release

Installer tests belong only to `ecos-release`. They exercise behavior through
subprocesses and temporary XDG roots rather than scanning generated shell text.

The generator test suite covers:

- Deterministic output from identical validated metadata.
- Rejection of missing assets, invalid digests, unsupported platforms, and
  inconsistent tags.
- POSIX syntax under `dash -n` and `bash -n`.
- ShellCheck when available in CI.

End-to-end tests build small fake ECC and toolchain archives and serve them from
a local HTTP server. They cover:

- GitHub success.
- GitHub failure followed by CNB success.
- Forced source modes.
- Both sources unavailable.
- Checksum mismatch.
- Unsupported OS, CPU, bitness, libc, and glibc version.
- Default no-profile behavior and explicit, idempotent one-profile mutation.
- Successful install and launcher execution.
- Failed upgrade preserving the existing launcher and current version.
- Three successful versions retaining only the newest and its predecessor.
- Idempotent reinstall of a valid same-version directory.
- Refusal to delete directories without installer receipts.
- Toolchain failure preserving a working ECC and prior env file.
- Validation of every Liberty member in all three PDK Liberty archives.

The publication workflow additionally installs the real ECC release bundle into
temporary XDG directories and executes the public CLI smoke commands before OSS
publication.

## Publication Workflow

The first workflow is manually triggered with an exact ECC tag. Automation from
ECC release events may be added later without changing generation semantics.

The workflow performs these steps in order:

1. Fetch and validate GitHub Release Asset metadata for the exact tag.
2. Verify the expected CNB Release asset exists and matches the GitHub digest.
3. Generate the versioned installer.
4. Run generator, syntax, behavior, and real-artifact installation tests.
5. Upload the versioned installer object to OSS.
6. Read the object back anonymously and verify its bytes and response headers.
7. Overwrite `latest` with the exact same installer bytes.
8. Read `latest` back anonymously and verify it matches the versioned object.

OSS metadata is:

```text
Versioned installer:
  Content-Type: text/x-sh
  Content-Disposition: inline
  Cache-Control: public, max-age=31536000, immutable

latest installer:
  Content-Type: text/x-sh
  Content-Disposition: inline
  Cache-Control: no-cache
```

OSS and any cross-repository CNB credentials are injected only through CI
secrets. They are never written to generated scripts, repository configuration,
test fixtures, or logs.

If any validation or versioned upload fails, `latest` is not changed. A failure
after the versioned upload but before `latest` update leaves a usable immutable
versioned installer and the prior known-good `latest`.

## Acceptance Criteria

- A versioned installer can be previewed in a browser and executed through
  `curl | sh`.
- Default installation on Linux x86_64 glibc 2.34 or newer installs a working
  ECC launcher without changing shell profiles.
- GitHub unavailability causes an automatic CNB fallback for the ECC bundle.
- Every installed archive is verified against release-derived SHA-256 metadata.
- Failed downloads, validation, extraction, or smoke tests do not replace the
  existing working ECC launcher.
- The current and immediately previous ECC versions remain directly executable;
  older installer-owned versions are removed.
- `--with-toolchain` installs shared tools and PDK data below the ECC data root
  and does not globally shadow Yosys.
- PDK validation checks every Liberty member supplied by all three Liberty
  archives and does not depend on STA flow configuration.
- Installer implementation and tests live only in `ecos-release`.
- `latest` changes only after the exact versioned installer and all referenced
  release assets have passed publication checks.
