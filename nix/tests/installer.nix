{
  pkgs,
  installer,
  template,
}:

{
  syntax =
    pkgs.runCommand "ecos-release-installer-syntax"
      {
        nativeBuildInputs = [
          pkgs.dash
          pkgs.bash
          pkgs.shellcheck
        ];
      }
      ''
        set -euo pipefail
        dash -n ${installer}
        bash -n ${installer}
        shellcheck -s dash -S error ${installer}
        echo ok > "$out"
      '';

  e2e =
    pkgs.runCommand "ecos-release-installer-e2e"
      {
        nativeBuildInputs = [
          pkgs.python3
          pkgs.curl
          pkgs.dash
          pkgs.bash
          pkgs.coreutils
          pkgs.gnutar
          pkgs.gzip
          pkgs.bzip2
          pkgs.gnused
          pkgs.glibc.bin
        ];
      }
      ''
        set -euo pipefail
        export HOME="$PWD/home"
        mkdir -p "$HOME"
        python3 ${./installer-e2e.py} --template ${template}
        echo ok > "$out"
      '';
}
