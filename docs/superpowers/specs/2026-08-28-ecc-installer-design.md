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
- Make upgrades between different versions transactional and retain the current
  and immediately previous ECC versions.
- Generate one immutable installer per ECC version, with `latest` as a copy of
  the newest successfully published installer.

## Non-Goals

- The first release does not support macOS, Windows, ARM64, musl, or glibc older
  than 2.34.
- The first release does not provide `ecc self update` or an uninstaller.
- The first release does not automatically repair a corrupted installation of
  the same ECC version.
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
  records, including the extraction destination of each supplemental archive.

The generated script is self-contained. It does not fetch a manifest at install
time. Repeated generation from identical input must produce identical bytes.
ECC versions must be valid Semantic Versioning 2.0.0 values, and the exact tag
must be `v<version>`. The same SemVer ordering is used when deciding whether a
publication may advance `latest`.

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
```

`XDG_BIN_HOME` is treated as a commonly used extension; the default remains
`$HOME/.local/bin`. An unset or empty `HOME` is an error unless all required
roots are explicitly configured. `ECC_INSTALL_DIR`, `XDG_DATA_HOME`,
`XDG_BIN_HOME`, `XDG_CACHE_HOME`, `XDG_CONFIG_HOME`, and `ZDOTDIR`, when used by
the installer, must be absolute paths without newline or carriage-return
characters. A relative or malformed configured path fails before filesystem
mutation. After validated roots are created, the installer resolves their
physical paths with POSIX `cd -P` and `pwd -P`; locks, the global receipt,
launchers, and ownership comparisons use those physical paths so lexical aliases
through parent-directory symlinks cannot bypass locking.

The managed data layout is:

```text
<data-root>/
├── ecc-receipt.json
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
└── env
```

The cache stores downloads by expected SHA-256 rather than mutable filename:

```text
<cache-root>/downloads/<sha256>.tar.gz
<cache-root>/downloads/<sha256>.tar.bz2
```

## Launcher and Environment Isolation

`<data-root>/ecc-receipt.json` is one global, static ownership receipt. Its
complete contents are one JSON object followed by a newline:

```json
{"format":1,"owner":"ecos-release"}
```

The receipt does not list installed versions, artifact digests, the current
version, or the previous version, and it is not updated on each install. It
reserves exact `v<semver>` directory names and the `tools`, `pdks`, and `env`
namespaces below the data root for this installer.

If the data root does not exist, the installer creates it and the ownership
receipt. An existing empty data root may be claimed by creating the receipt. An
existing non-empty data root without the exact valid receipt is not adopted or
modified. Receipt initialization uses a temporary file in the data root's
parent and an atomic no-clobber link into the data root. If another invocation
publishes the target first, the loser validates it rather than overwriting it.
The installer compares the complete bytes and does not need a JSON parser. After
initialization, every install validates the exact receipt before creating the
data-root lock or changing managed state.

`<bin-dir>/ecc` is a small generated POSIX launcher rather than a copy of the
PyInstaller executable. It contains installer-owned, machine-readable version
and data-root assignments, optionally reads the installer-owned
`<data-root>/env` file, and executes `<data-root>/<version>/ecc` with all
arguments. It is the only current-version pointer; the global receipt does not
duplicate current state.

The installer parses owned launcher assignments as data and never sources or
executes an existing launcher while discovering prior state.

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

The launcher and env file use safely quoted absolute paths and are installed
through temporary files followed by same-directory `mv`. Before any install, an
existing `<bin-dir>/ecc` that does not have the expected installer marker and
valid structure is treated as an ownership collision and is not overwritten.
The installer has no implicit force-overwrite mode.

## Shell Profile Policy

The default installation never modifies a shell profile. If `<bin-dir>` is not
already in `PATH`, the installer prints a command for the current shell.

Profile mutation occurs only with `--modify-path` or `ECC_MODIFY_PATH=1`. The
installer uses the basename of `SHELL` to select one file:

```text
sh:    $HOME/.profile
bash:  $HOME/.bashrc
zsh:   ${ZDOTDIR:-$HOME}/.zshrc
fish:  ${XDG_CONFIG_HOME:-$HOME/.config}/fish/conf.d/ecc.env.fish
```

Known Bourne-style profiles receive one marked, idempotent block. Fish receives
equivalent fish syntax. An unknown shell is not modified; the installer prints
manual instructions. Failure to update a requested profile is reported after a
successful install and returns a nonzero status without rolling back ECC.

After installation, the installer evaluates `command -v ecc`. If it does not
resolve to `<bin-dir>/ecc`, it reports the command that shadows the installed
launcher even when `<bin-dir>` appears elsewhere in `PATH`.

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
30 seconds. Generation or preflight fails if the available `curl` cannot support
the required options. These values are part of the first installer behavior,
not mutable environment configuration.

An optional short request to the exact asset URL may be used to avoid selecting
an obviously unavailable source, but a successful probe never replaces real
download error handling. Testing only `github.com` is insufficient because the
redirected release asset host may be blocked.

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

Every ECC, OSS CAD Suite, PDK base, and PDK supplemental archive is subject to
the same extraction policy. Before extraction, the installer obtains the full
member inventory and rejects:

- Absolute member paths, empty member paths, or a `..` path component.
- Member paths or link targets containing newline, carriage-return, or other
  control characters that the inventory parser cannot represent unambiguously.
- Symbolic-link or hard-link targets that are absolute or resolve outside the
  staging root.
- Device nodes, FIFOs, sockets, and any entry type other than a regular file,
  directory, symbolic link, or hard link.

Extraction runs only into a newly created staging directory, never through the
PDK repository's `make unzip` target. It disables owner and permission
restoration and must not follow a pre-existing directory symlink. After
extraction, the installer walks the staging tree, rejects special files, and
verifies that every link resolves within the staging root. The implementation
may rely on explicitly preflighted GNU tar capabilities for these guarantees;
it must fail closed when the installed tar cannot provide them.

## Installation Locking

Downloads into unique cache partial files may run without an installation lock.
Before reading or mutating installed state, every invocation acquires two
installer-owned directory locks in a fixed order:

1. `<data-root>/.ecos-release-install-lock`
2. `<bin-dir>/.ecc-install-lock`

The locks use atomic `mkdir`, record PID and host information, and are released
by the normal exit and signal trap. A contender never mutates installed state
while either lock is held. If the recorded host is local and the PID is no
longer alive, a contender may atomically quarantine the stale lock and retry;
an unverifiable or live owner causes a clear nonzero failure. Acquiring the data
lock before the binary lock for every invocation prevents deadlock when custom
data and binary roots overlap across invocations.

## Transactional ECC Installation

ECC installation follows these phases:

1. Validate options, commands, platform, configured paths, ownership collisions,
   and writable roots, then initialize or validate the fixed global receipt.
2. Reuse a cache entry only after SHA-256 verification.
3. Download to a `.part` file and atomically promote it into the cache.
4. Acquire the data-root lock and then the binary-directory lock.
5. Re-read the launcher and global receipt while holding both locks;
   decisions made before locking are not trusted for mutation.
6. Apply the archive safety policy and extract into a unique temporary directory
   under the ECC data root.
7. Verify the expected `ecc` and `_internal` layout.
8. Run `ecc --version`, `ecc version --json`, and verify that
   `_internal/torch/bin/torch_shm_manager` is executable.
9. If `<data-root>/<version>` does not exist, atomically rename staging to that
   previously nonexistent version directory.
10. Atomically replace `<bin-dir>/ecc`. This replacement is the transaction's
    commit point.
11. When switching versions, remove older managed ECC version directories while
    retaining the new and prior versions.

An existing same-version directory is reused only when its expected layout and
runtime smoke tests pass. If it is incomplete or fails a smoke test, the
installer stops without moving, deleting, or overwriting it and tells the user
to move the directory aside before reinstalling. Same-version automatic repair
is intentionally excluded because a non-empty active directory cannot be
atomically replaced.

Before switching the launcher to a different version, the installer reads the
prior version only from an existing launcher whose owned marker and structure
validate. After a successful switch it retains the new current version and that
prior version. It removes other top-level directories whose names are exact ECC
version tags only because the valid global receipt reserves that namespace for
the installer. Cleanup does not run for a same-version reinstall or when no valid
owned prior launcher exists. `tools`, `pdks`, unknown names, and unknown files
are never removed by ECC version cleanup.

Cleanup runs after the commit point. A cleanup failure leaves the new launcher
active, preserves any version it could not safely remove, and is reported as a
warning; a later different-version install retries cleanup.

Installing a fixed older version is supported by running that version's
installer. Users may also execute an installed older version directly at
`<data-root>/<version>/ecc`.

Any failure before launcher replacement leaves the existing current ECC
unchanged. A trap removes temporary files and releases owned locks without
deleting verified cache entries or prior installed versions.

## Optional Toolchain Installation

`--with-toolchain` installs OSS CAD Suite and the ICS55 PDK after the ECC bundle
has passed its own installation transaction. A toolchain failure does not roll
back a successfully installed ECC CLI.

An ECC-only install leaves an existing valid `<data-root>/env` and toolchain
untouched, so an ECC upgrade continues to use the previously installed shared
toolchain.

Each component uses its own staging directory, digest verification, archive
safety checks, and final validation. Existing complete versions are shared
across ECC versions and reused. Toolchain state mutation occurs while holding
the same data-root lock used for ECC installation. Because the global receipt
reserves the toolchain namespaces, an existing component version is reused only
when all component validations pass. An invalid same-version component fails
closed and is not replaced in place.

OSS CAD Suite validation requires at least:

```text
bin/yosys is executable
share/yosys/plugins exists
yosys --version succeeds in the candidate launcher environment
the ECC-compatible builtin `read_slang` or `plugin -i slang` probe succeeds
```

The ICS55 PDK release consists of a base archive and seven supplemental assets.
Every archive is verified before extraction. The three Liberty archives are:

```text
ics55_LLSC_H7CH_liberty.tar.bz2
ics55_LLSC_H7CL_liberty.tar.bz2
ics55_LLSC_H7CR_liberty.tar.bz2
```

For each verified Liberty archive, the installer obtains the complete `.lib`
member list before extraction. It rejects an archive with no `.lib` members.
The installer extracts all seven supplemental archives directly into their
metadata-defined destinations instead of invoking the PDK Makefile. After this
deterministic unpack step, every listed Liberty file must exist and be non-empty.
This validates the PDK release contents and does not depend on ECC's
`sta_ecc.json` flow configuration.

The installer also validates the tech LEF and standard-cell LEFs required by
ECC's PDK contract. Tool runtime probes run with `LD_LIBRARY_PATH` and
`LD_PRELOAD` removed, matching ECC's managed Yosys subprocess behavior. Only
after both OSS CAD Suite and PDK validation pass does the installer atomically
update `<data-root>/env`. If either component fails, an existing env file and
existing complete toolchain remain unchanged.

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
- GitHub redirect target stalling or remaining below the low-speed threshold,
  followed by CNB success within the specified retry budget.
- Forced source modes.
- Both sources unavailable.
- Checksum mismatch.
- Unsupported OS, CPU, bitness, libc, and glibc version.
- Default no-profile behavior and explicit, idempotent one-profile mutation.
- Successful install and launcher execution.
- Failed upgrade preserving the existing launcher and current version.
- A corrupted same-version directory failing without changing the launcher or
  installed files.
- Three successful versions retaining only the newest and its predecessor.
- Idempotent reinstall of a valid same-version directory without deleting the
  retained previous version.
- A concurrent installer encountering a live lock failing without mutating or
  deleting the selected version, and stale-lock recovery succeeding safely.
- Creation and validation of the one global ownership receipt.
- Refusal to adopt a non-empty unowned data root or overwrite an unowned binary.
- Shadowed `ecc` detection and `ZDOTDIR` / `XDG_CONFIG_HOME` profile selection.
- Rejection of traversal paths, escaping links, and special archive members for
  every supported archive type.
- Toolchain failure preserving a working ECC and prior env file.
- Real Yosys version and Slang frontend probes in the candidate environment.
- Validation of every Liberty member in all three PDK Liberty archives.

The publication workflow additionally performs two real-artifact installations
into temporary XDG directories before OSS publication: an ECC-only install that
executes the public CLI smoke commands, and a `--with-toolchain` install that
downloads every referenced OSS CAD Suite and PDK asset and executes the Yosys,
Slang, Liberty, and LEF validations defined above.

## Publication Workflow

The first workflow is manually triggered with an exact ECC tag. Automation from
ECC release events may be added later without changing publication semantics.

The publication workflow uses one repository-wide installer-publication
concurrency group with `cancel-in-progress: false`. A second run waits instead
of racing an active publication.

The workflow performs these steps in order:

1. Fetch and validate GitHub Release Asset metadata for the exact tag.
2. Verify the expected CNB Release asset exists and matches the GitHub digest.
3. Generate the versioned installer.
4. Run generator, syntax, behavior, and real-artifact installation tests.
5. Read the versioned OSS path. Create it with OSS forbid-overwrite semantics
   when absent; when present, accept it only if its bytes and required headers
   already match, otherwise fail without overwriting it.
6. Read the object back anonymously and verify its bytes and response headers.
7. Read the current `latest` installer when present. Refuse to replace a strictly
   newer ECC version according to SemVer ordering.
8. Replace `latest` with the exact same installer bytes. Publication credentials
   are scoped to this serialized workflow; other writers are outside the
   supported publication model.
9. Read `latest` back anonymously and verify it matches the versioned object.

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
  ECC launcher without changing shell profiles.
- GitHub unavailability causes an automatic CNB fallback for the ECC bundle.
- Every installed archive is verified against release-derived SHA-256 metadata.
- Failed downloads, validation, extraction, or smoke tests do not replace the
  existing working ECC launcher.
- A corrupted same-version install fails without changing the active launcher or
  installed directory.
- Concurrent installer invocations cannot overlap installed-state mutation.
- The current and immediately previous ECC versions remain directly executable;
  older installer-owned versions are removed.
- `--with-toolchain` installs shared tools and PDK data below the ECC data root
  and does not globally shadow Yosys.
- PDK validation checks every Liberty member supplied by all three Liberty
  archives and does not depend on STA flow configuration.
- Archive validation prevents path, link, and special-file escape for every
  installed archive.
- Toolchain validation executes Yosys and verifies the Slang frontend in the
  same managed environment ECC will use.
- Installer implementation and tests live only in `ecos-release`.
- Versioned installer objects cannot be overwritten with different bytes.
- `latest` changes only after the exact versioned installer and all referenced
  release assets have passed publication checks, and it cannot be downgraded by
  publishing an older SemVer release.
