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
- Follow XDG directory conventions without modifying shell profiles.
- Make upgrades between different versions transactional without deleting
  previously installed versions.
- Generate one immutable installer per ECC version, with `latest` as a copy of
  the newest successfully published installer.

## Non-Goals

- The first release does not support macOS, Windows, ARM64, musl, or glibc older
  than 2.34.
- The first release does not provide `ecc self update` or an uninstaller.
- The first release does not automatically repair a corrupted installation of
  the same ECC version.
- The first release does not automatically remove installed ECC versions.
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
- Structured archive validation for every referenced release asset.
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
  records, including the extraction destination of each supplemental archive.

The generated script is self-contained. It does not fetch a manifest at install
time. Repeated generation from identical input must produce identical bytes.
ECC versions must be valid Semantic Versioning 2.0.0 values, and the exact tag
must be `v<version>`. The same SemVer ordering is used when deciding whether a
publication may advance `latest`. Generation is allowed only after every input
archive's exact bytes pass structured member validation and digest verification.

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
--download-source auto|github|cnb
```

Supported environment variables:

```text
ECC_WITH_TOOLCHAIN=1
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
mutation. Boolean environment variables accept only `0` or `1`. Quiet mode
suppresses progress output, never warnings or errors.

## Shell Compatibility

The generated installer is POSIX `sh` and must run under at least `dash` and
`bash` in POSIX mode. It must not depend on `[[`, `BASH_SOURCE`, arrays,
associative arrays, or the non-POSIX `source` command.

The installer requires `curl`, `uname`, `mktemp`, `mkdir`, `mv`, `rm`, `tar`,
`sha256sum`, `chmod`, `grep`, `sed`, `awk`, `head`, `tail`, `find`, `cat`, and
`ldd`. Toolchain installation also requires `bzip2`. Missing requirements and
unsupported command capabilities are reported before starting the relevant
phase. The installer does not require `git`, `make`, Python, or a compiler.

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

Configuration root:
  ${XDG_CONFIG_HOME:-$HOME/.config}/ecc
```

`XDG_BIN_HOME` is treated as a commonly used extension; the default remains
`$HOME/.local/bin`. An unset or empty `HOME` is an error unless all required
roots are explicitly configured. `ECC_INSTALL_DIR`, `XDG_DATA_HOME`,
`XDG_BIN_HOME`, `XDG_CACHE_HOME`, and `XDG_CONFIG_HOME`, when used by the
installer, must be absolute paths without control characters. A relative or
malformed configured path fails before filesystem mutation. After validated
roots are created, the installer resolves their physical paths with POSIX
`cd -P` and `pwd -P`; the lock, wrapper, and generated receipt use those
physical paths.

The managed data layout is:

```text
<data-root>/
├── v0.1.0-alpha.10/
│   ├── ecc
│   └── _internal/
├── v0.1.0-alpha.11/
│   ├── ecc
│   └── _internal/
├── tools/
│   └── oss-cad-suite/
│       └── 20260808/
├── pdks/
│   └── icsprout55/
│       └── v1.10.102/
```

The installer writes global metadata separately:

```text
<config-root>/ecc-receipt.json
```

The cache stores downloads by expected SHA-256 rather than mutable filename:

```text
<cache-root>/downloads/<sha256>.tar.gz
<cache-root>/downloads/<sha256>.tar.bz2
```

## Run Wrapper and Environment Isolation

`<config-root>/ecc-receipt.json` is global installation metadata modeled after
uv's receipt. The generated file is compact JSON equivalent to:

```json
{
  "binaries": ["ecc"],
  "data_root": "/home/user/.local/share/ecc",
  "install_prefix": "/home/user/.local/bin",
  "provider": {"format": 1, "name": "ecos-release"},
  "version": "0.1.0-alpha.11"
}
```

The installer writes the receipt through a temporary file and same-directory
`mv` after the current wrapper has been replaced. It safely JSON-escapes path
values. Receipt failure is a warning and does not turn an otherwise successful
installation into a failure. The installer never reads the receipt and does not
use it for ownership, reuse, cleanup, or current-version selection. A future
updater or uninstaller may consume it; `<bin-dir>/ecc` remains the authoritative
current-version pointer. A missing, stale, or malformed existing receipt never
blocks installation and is replaced after the wrapper commit.

`<bin-dir>/ecc` is a generated POSIX run-wrapper rather than a copy of the
PyInstaller executable. Its first two lines are the exact shebang `#!/bin/sh` and
ownership marker `# ecos-release-wrapper-v1`. It contains safely shell-quoted
data-root and version values, then executes `<data-root>/<version>/ecc` with all
arguments. It is the only authoritative current-version pointer; the global
receipt is only a metadata snapshot.

An ECC-only wrapper exports no toolchain variables. When a complete managed
toolchain is selected, the wrapper exports only:

```text
CHIPCOMPILER_OSS_CAD_DIR=<managed OSS CAD Suite root>
CHIPCOMPILER_ICS55_PDK_ROOT=<managed ICS55 PDK root>
```

Those exports affect only the wrapper process, the real ECC process that
replaces it through `exec`, and ECC child processes. They do not modify the
calling shell or any system-wide environment. The wrapper does not modify
`PATH` and does not export `YOSYS_PLUGINPATH` or `YOSYS_DATDIR`; ECC resolves the
managed Yosys executable from `CHIPCOMPILER_OSS_CAD_DIR` and builds the
Yosys-specific subprocess environment itself.

There is no separate runtime env file. The installer never sources or executes
an existing wrapper while discovering prior state. It accepts an existing
`<bin-dir>/ecc` as owned only when it is a regular file with the exact shebang
and ownership marker; otherwise the path is an ownership collision. The
candidate wrapper receives its user execute bit with `chmod u+x`, passes
`sh -n`, and is installed through a temporary file and same-directory `mv`. The
installer does not otherwise normalize its permissions and has no implicit
force-overwrite mode.

## PATH Policy

The installer never modifies shell profiles. If `<bin-dir>` is not already in
`PATH`, it prints the appropriate command for POSIX shells, or fish syntax when
the basename of `SHELL` is `fish`.

After installation, the installer evaluates `command -v ecc`. If it does not
resolve to `<bin-dir>/ecc`, it reports the command that shadows the installed
wrapper even when `<bin-dir>` appears elsewhere in `PATH`.

## Source Selection and Downloading

The installer does not infer geography. `auto` means ordered availability
fallback:

1. Try the exact GitHub Release asset URL, following its redirect to the real
   asset host.
2. On connection failure, HTTP failure, retry exhaustion, or sustained low
   transfer speed, try the exact CNB Release asset URL.
3. Verify the completed file against the one embedded SHA-256 digest.

Each transfer uses `curl -fL` with a 10-second connection timeout, two retries
after the initial attempt, a two-second retry delay, a 60-second retry budget,
and low-speed failure when the transfer remains below 1024 bytes per second for
30 seconds. Installation fails before downloading if the available `curl` cannot
support the required options. These values are part of the first installer
behavior, not mutable environment configuration.

Downloads use a unique source-specific partial file created with `mktemp` below
the cache download directory. A failed source's partial bytes are not resumed
from another source. Concurrent transfers never share a partial file. Before a
verified candidate is promoted to the digest-keyed cache path, an existing cache
entry is reverified; a valid entry wins, while an invalid entry is replaced by
the verified candidate. A checksum mismatch deletes the candidate, prints a
high-visibility integrity error, and may try the next configured source. No
unverified archive is extracted or executed.

`github` and `cnb` source modes disable fallback and are intended for diagnosis,
CI, and constrained networks.

The initial CNB fallback applies only to the ECC PyInstaller bundle. OSS CAD
Suite and PDK assets remain GitHub-only until their CNB mirrors are published.
Consequently, `--download-source cnb --with-toolchain` downloads ECC from CNB
but reports and downloads the toolchain assets from their only available GitHub
source. Adding toolchain mirrors later extends metadata and source lists without
changing the command interface.

## Archive Safety Policy

Before generating a public installer, the publication workflow downloads the
exact ECC, OSS CAD Suite, PDK base, and PDK supplemental archive bytes. A
publication validator uses Python's structured `tarfile` member metadata, not
formatted `tar -t` output, to obtain the complete inventory and reject:

- Absolute member paths, empty member paths, or a `..` path component.
- Member paths or link targets containing control characters.
- Symbolic-link or hard-link targets that are absolute or resolve outside the
  staging root.
- Device nodes, FIFOs, sockets, and any entry type other than a regular file,
  directory, symbolic link, or hard link.

Only after this structural validation succeeds may the workflow bind the
archive's SHA-256 digest into a generated installer. CNB ECC bytes must match the
same validated digest. Structural validation therefore applies to the exact
bytes accepted later by the runtime installer rather than to a mutable filename
or URL.

At runtime, the installer does not reimplement a structured archive parser in
POSIX shell. It verifies the downloaded bytes against the embedded digest, then
extracts only into a newly created staging directory using preflighted GNU tar
with owner and permission restoration disabled. It never invokes the PDK
repository's `make unzip` target. A nonzero extraction status fails the install.
After extraction, it verifies the expected component layout and rejects
unexpected filesystem object types before any runtime smoke test or final
promotion. The publication validator remains responsible for complete member
path and link-target analysis.

## Installation Locking

Downloads into unique cache partial files may run without an installation lock.
Before mutating installed state, an invocation acquires one
`<data-root>/.ecc-install-lock` directory using atomic `mkdir`. The normal exit
and signal trap removes only a lock acquired by the current process. If the lock
already exists, the installer fails with its path and tells the user to confirm
that no installer is running before removing it manually. The installer does not
interpret PID files or recover stale locks automatically.

## Transactional ECC Installation

ECC installation follows these phases:

1. Validate options, commands, platform, configured paths, ownership collisions,
   and writable roots.
2. Reuse a cache entry only after SHA-256 verification.
3. Download to a `.part` file and atomically promote it into the cache.
4. Acquire the data-root lock.
5. Re-read the wrapper and target paths while holding the lock; decisions made
   before locking are not trusted for mutation.
6. Apply the archive safety policy and extract into a unique temporary directory
   under the ECC data root.
7. Verify the expected `ecc` and `_internal` layout.
8. Run `ecc --version`, `ecc version --json`, and verify that
   `_internal/torch/bin/torch_shm_manager` is executable.
9. If `<data-root>/<version>` does not exist, atomically rename staging to that
   previously nonexistent version directory.
10. Install and validate the requested optional toolchain while the existing
    wrapper remains unchanged.
11. Only after every component requested by this invocation validates, generate
    an ECC-only wrapper or a toolchain wrapper as appropriate. A default install
    may continue selecting already installed expected toolchain versions only
    when they independently validate.
12. Atomically replace `<bin-dir>/ecc`. This replacement is the transaction's
    commit point.
13. Atomically write the global receipt. Failure here produces a warning only.

An existing same-version directory is reused only when its expected layout and
runtime smoke tests pass. If it is incomplete or fails a smoke test, the
installer stops without moving, deleting, or overwriting it and tells the user
to move the directory aside before reinstalling. Same-version automatic repair
is intentionally excluded because a non-empty active directory cannot be
atomically replaced.

Installing a version never removes another version directory. Old versions
remain directly executable until the user removes them or a future uninstaller
manages them.

Installing a fixed older version is supported by running that version's
installer. Users may also execute an installed older version directly at
`<data-root>/<version>/ecc`.

Any failure before wrapper replacement leaves the existing wrapper and receipt
unchanged. A failed first installation creates neither. A trap removes temporary
files, incomplete staging directories, and the owned lock without deleting
verified cache entries, prior installed versions, or complete version directories
that this invocation already validated and promoted for reuse.

## Optional Toolchain Installation

`--with-toolchain` installs OSS CAD Suite and the ICS55 PDK after the ECC bundle
has passed its validation but before the wrapper commit. The installer creates or
replaces the wrapper only after ECC, OSS CAD Suite, and the PDK all validate. A
toolchain failure returns nonzero and leaves the existing wrapper and receipt
unchanged; on a first installation it creates neither. Fully validated version
directories may remain for a later retry; incomplete staging directories are
removed.

An ECC-only install leaves existing toolchain directories untouched. If the
expected OSS CAD Suite and PDK versions already pass the validations below, the
new wrapper continues to export their roots; otherwise it exports no toolchain
variables and reports that ECC was installed without the managed toolchain.

Each component uses its own staging directory, digest verification, archive
safety checks, and final validation. Existing complete versions are shared
across ECC versions and reused. Toolchain state mutation occurs while holding
the same data-root lock used for ECC installation. An existing component version
is reused only when all component validations pass. An invalid same-version
component fails closed and is not replaced in place. Unknown paths below the
data root are not adopted, overwritten, or deleted.

OSS CAD Suite validation requires at least:

```text
bin/yosys is executable
share/yosys/plugins exists
yosys --version succeeds in the candidate wrapper environment
the ECC-compatible builtin `read_slang` or `plugin -i slang` probe succeeds
```

The ICS55 PDK release consists of a base archive and seven supplemental assets.
Every archive is verified before extraction. The three Liberty archives are:

```text
ics55_LLSC_H7CH_liberty.tar.bz2
ics55_LLSC_H7CL_liberty.tar.bz2
ics55_LLSC_H7CR_liberty.tar.bz2
```

For each verified Liberty archive, the publication validator obtains the
complete `.lib` member list and rejects an archive with no `.lib` members. The
generated installer embeds the normalized destination of every listed Liberty
file. At runtime it extracts all seven supplemental archives directly into their
metadata-defined destinations instead of invoking the PDK Makefile, then
requires every embedded Liberty path to exist and be non-empty. This validates
the PDK release contents and does not depend on ECC's `sta_ecc.json` flow
configuration.

The installer also validates the tech LEF and standard-cell LEFs required by
ECC's PDK contract. Tool runtime probes run with `LD_LIBRARY_PATH` and
`LD_PRELOAD` removed, matching ECC's managed Yosys subprocess behavior. Only
after both OSS CAD Suite and PDK validation pass may their roots be embedded in
the candidate wrapper. If either component fails, existing complete toolchain
directories remain unchanged and are not selected unless they independently
pass validation.

## Testing in ecos-release

Installer tests belong only to `ecos-release`. They exercise behavior through
subprocesses and temporary XDG roots rather than scanning generated shell text.

The generator and publication-validation test suites cover:

- Deterministic output from identical validated metadata.
- Rejection of missing assets, invalid digests, unsupported platforms, and
  inconsistent tags.
- Structured rejection of traversal paths, escaping links, control characters,
  special members, and empty Liberty inventories for every archive format.
- POSIX syntax under `dash -n` and `bash -n`.
- ShellCheck when available in CI.

End-to-end tests build small fake ECC and toolchain archives and serve them from
a local HTTP server. They cover:

- GitHub success.
- GitHub failure followed by CNB success.
- GitHub redirect target stalling or remaining below the low-speed threshold,
  followed by CNB success within the specified retry budget.
- Forced source modes.
- Both sources unavailable.
- Checksum mismatch.
- Unsupported OS, CPU, bitness, libc, and glibc version.
- PATH guidance without shell-profile mutation.
- Successful direct execution of a generated ECC-only wrapper without
  toolchain exports.
- A toolchain wrapper exporting only `CHIPCOMPILER_OSS_CAD_DIR` and
  `CHIPCOMPILER_ICS55_PDK_ROOT`, without modifying `PATH` or exporting
  Yosys-specific variables.
- An ECC-only upgrade preserving an already installed, validated expected
  toolchain in the new wrapper.
- Any failure before commit during a first installation leaving no wrapper or
  receipt.
- Failed upgrade preserving the existing wrapper, receipt, and current version.
- A corrupted same-version directory failing without changing the wrapper or
  installed files.
- Three successful versions remaining installed while the wrapper selects the
  newest one.
- Idempotent reinstall of a valid same-version directory without deleting other
  versions.
- A concurrent installer encountering a live lock failing without mutating or
  deleting installed state, and manual lock removal allowing a later retry.
- Global receipt creation after wrapper commit and receipt-write failure being
  non-fatal.
- A missing, stale, or malformed prior receipt not affecting installation.
- Refusal to overwrite an unowned binary or invalid same-version target.
- Shadowed `ecc` detection and `XDG_CONFIG_HOME` receipt placement.
- Runtime checksum binding to publication-validated archive bytes and rejection
  of unexpected post-extraction filesystem object types.
- Toolchain failure preserving the existing wrapper and receipt while retaining
  only complete, validated version directories for reuse.
- Real Yosys version and Slang frontend probes in the candidate environment.
- Validation of every Liberty member in all three PDK Liberty archives.

The publication workflow additionally performs one real-artifact
`--with-toolchain` installation into temporary XDG directories before OSS
publication. It executes the public ECC CLI smoke commands, downloads every
referenced OSS CAD Suite and PDK asset, and executes the Yosys, Slang, Liberty,
and LEF validations defined above.

## Publication Workflow

The first workflow is manually triggered with an exact ECC tag. Automation from
ECC release events may be added later without changing publication semantics.

The publication workflow uses one repository-wide installer-publication
concurrency group with `cancel-in-progress: false`. A second run waits instead
of racing an active publication.

The workflow performs these steps in order:

1. Fetch GitHub Release Asset metadata for the exact tag and download every ECC,
   OSS CAD Suite, PDK base, and PDK supplemental archive referenced by the
   release model.
2. Verify every digest and run structured member validation against those exact
   bytes, including complete Liberty inventory collection.
3. Verify the expected CNB ECC asset exists and matches the validated GitHub
   digest.
4. Generate the versioned installer from the validated release model.
5. Run generator, syntax, behavior, and real-artifact installation tests.
6. Read the versioned OSS path. Create it with OSS forbid-overwrite semantics
   when absent; when present, accept it only if its bytes and required headers
   already match, otherwise fail without overwriting it.
7. Read the object back anonymously and verify its bytes and response headers.
8. Read the current `latest` installer when present. Refuse to replace a strictly
   newer ECC version according to SemVer ordering.
9. Replace `latest` with the exact same installer bytes. Publication credentials
   are scoped to this serialized workflow; other writers are outside the
   supported publication model.
10. Read `latest` back anonymously and verify it matches the versioned object.

Publication tests cover an idempotent rerun, rejection of different bytes at an
existing versioned path, an older SemVer release leaving `latest` unchanged, and
queued workflow runs being unable to downgrade `latest` regardless of execution
order. A missing or malformed current `latest` version assignment fails closed
rather than being overwritten.

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
versioned installer and the prior known-good `latest`. Publishing an older fixed
version remains supported at its versioned URL but never downgrades `latest`.

## Acceptance Criteria

- A versioned installer can be previewed in a browser and executed through
  `curl | sh`.
- Default installation on Linux x86_64 glibc 2.34 or newer installs a working
  ECC run-wrapper without changing shell profiles.
- GitHub unavailability causes an automatic CNB fallback for the ECC bundle.
- Every installed archive is verified against release-derived SHA-256 metadata.
- Failed downloads, validation, extraction, or smoke tests do not replace the
  existing working ECC wrapper.
- A failed first installation does not create a wrapper or receipt.
- A corrupted same-version install fails without changing the active wrapper or
  installed directory.
- Concurrent installer invocations using the same data root cannot overlap
  installed-state mutation.
- Installing a new ECC version does not delete any previously installed version.
- A successful install writes a non-authoritative global receipt after switching
  the wrapper; receipt failure does not break the installed ECC.
- `--with-toolchain` installs shared tools and PDK data below the ECC data root
  and does not globally shadow Yosys. It creates or replaces the wrapper only
  after ECC and both toolchain components validate.
- The wrapper exports only the managed OSS CAD Suite and PDK roots. It does not
  modify `PATH`, export Yosys-specific variables, or affect the calling shell.
- PDK validation checks every Liberty member supplied by all three Liberty
  archives and does not depend on STA flow configuration.
- Publication validates the complete structure of every referenced archive, and
  runtime SHA-256 checks bind installation to those exact validated bytes.
- Toolchain validation executes Yosys and verifies the Slang frontend in the
  same managed environment ECC will use.
- Installer implementation and tests live only in `ecos-release`.
- Versioned installer objects cannot be overwritten with different bytes.
- `latest` changes only after the exact versioned installer and all referenced
  release assets have passed publication checks, and it cannot be downgraded by
  publishing an older SemVer release.
