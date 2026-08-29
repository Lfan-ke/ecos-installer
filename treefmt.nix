{
  projectRootFile = "flake.nix";

  programs.nixfmt.enable = true;
  programs.ruff-format = {
    enable = true;
    lineLength = 100;
  };
  programs.taplo.enable = true;
  programs.yamlfmt.enable = true;
  programs.shfmt.enable = true;

  # POSIX installer template uses @PLACEHOLDER@ tokens; leave it alone.
  settings.formatter.shfmt.excludes = [ "templates/*" ];
}
