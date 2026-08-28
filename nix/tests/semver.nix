{ pkgs, semver }:

let
  v10 = semver.parse "0.1.0-alpha.10";
  v11 = semver.parse "0.1.0-alpha.11";
  vRel = semver.parse "0.1.0";
  v0 = semver.parse "1.0.0-0";
  v1 = semver.parse "1.0.0-1";
  vBuild = semver.parse "1.0.0+build.1";
  vPlain = semver.parse "1.0.0";
in
assert semver.compare v10 v11 == -1;
assert semver.compare v11 vRel == -1;
assert semver.compare vRel v11 == 1;
assert semver.compare v0 v1 == -1;
assert semver.compare vBuild vPlain == 0;
assert semver.equal (semver.parse "1.0.0-alpha+001") (semver.parse "1.0.0-alpha");
assert semver.lessThan (semver.parse "0.1.0-alpha.1") (semver.parse "0.1.0-alpha.beta");
pkgs.runCommand "ecos-release-semver-check" { } ''
  echo ok > "$out"
''
