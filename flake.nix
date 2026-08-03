{
  description = "postmaker — draft Discourse notes into site/Threads/Bluesky posts for review";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
    in
    {
      packages = forAll (pkgs: {
        default = pkgs.python3.pkgs.buildPythonApplication {
          pname = "postmaker";
          version = "0.1.0";
          pyproject = true;
          src = ./.;
          nativeBuildInputs = [ pkgs.python3.pkgs.setuptools ];
          doCheck = false;
          # Runtime deps: stdlib only. Generation shells out to `claude`, which
          # the user provides on PATH (already authenticated).
        };
      });

      apps = forAll (pkgs: {
        default = {
          type = "app";
          program = "${self.packages.${pkgs.system}.default}/bin/postmaker";
        };
      });

      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [ pkgs.python3 pkgs.jq pkgs.tmux ];
          shellHook = ''
            echo "postmaker dev shell — run: python -m postmaker <run|once|gen>"
          '';
        };
      });
    };
}
