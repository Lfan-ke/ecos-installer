{
  pkgs,
  lib,
  model,
}:

let
  hexToSri =
    hex:
    builtins.convertHash {
      hash = hex;
      hashAlgo = "sha256";
      toHashFormat = "sri";
    };

  fetchPinned =
    {
      url,
      sha256,
      name,
    }:
    pkgs.fetchurl {
      inherit url name;
      hash = hexToSri sha256;
    };

  validator = ./archive-validate.py;

  checkArchive =
    {
      name,
      url,
      sha256,
      requireLiberty ? false,
      dest ? null,
      expectLiberty ? [ ],
    }:
    let
      src = fetchPinned { inherit url sha256 name; };
    in
    pkgs.runCommand "check-${name}"
      {
        nativeBuildInputs = [ pkgs.python3 ];
      }
      ''
        python3 ${validator} ${src} \
          ${lib.optionalString requireLiberty "--require-liberty"} \
          ${lib.optionalString (dest != null) "--dest ${lib.escapeShellArg dest}"} \
          ${lib.concatMapStrings (p: "--expect-liberty ${lib.escapeShellArg p} ") expectLiberty}
        mkdir -p "$out"
        ln -s ${src} "$out/${name}"
      '';

  libertyFor = dest: builtins.filter (p: lib.hasPrefix (dest + "/") p) model.pdk.libertyFiles;

  eccGithub = checkArchive {
    name = model.ecc.name;
    url = model.ecc.url;
    sha256 = model.ecc.sha256;
  };

  eccCnb = checkArchive {
    name = "cnb-${model.ecc.name}";
    url = model.ecc.cnbUrl;
    sha256 = model.ecc.sha256;
  };

  ossGithub = checkArchive {
    name = model.ossCadSuite.name;
    url = model.ossCadSuite.url;
    sha256 = model.ossCadSuite.sha256;
  };

  ossCnb = checkArchive {
    name = "cnb-${model.ossCadSuite.name}";
    url = model.ossCadSuite.cnbUrl;
    sha256 = model.ossCadSuite.sha256;
  };

  pdkBase = checkArchive {
    name = model.pdk.base.name;
    url = model.pdk.base.url;
    sha256 = model.pdk.base.sha256;
  };

  pdkAssets = map (
    a:
    checkArchive {
      name = a.name;
      url = a.url;
      sha256 = a.sha256;
      requireLiberty = a.kind == "liberty";
      dest = if a.kind == "liberty" then a.dest else null;
      expectLiberty = if a.kind == "liberty" then libertyFor a.dest else [ ];
    }
  ) model.pdk.assets;

  pdkCnb = map (
    a:
    checkArchive {
      name = "cnb-${a.name}";
      url = a.cnbUrl;
      sha256 = a.sha256;
      requireLiberty = a.kind == "liberty";
    }
  ) model.pdk.assets;
in
{
  inherit hexToSri fetchPinned;
  all = [
    eccGithub
    eccCnb
    ossGithub
    ossCnb
    pdkBase
  ]
  ++ pdkAssets
  ++ pdkCnb;
}
