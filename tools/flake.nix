{
    description = "Dev environment with Python 3.14";

    inputs = {
        nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
        flake-utils.url = "github:numtide/flake-utils";
    };

    outputs = { self, nixpkgs, flake-utils }:
        let
            system = "aarch64-darwin";
            pkgs = nixpkgs.legacyPackages.${system};
        in {
            shell = pkgs.zsh;

            devShells.${system}.default = pkgs.mkShell {
                packages = [
                    pkgs.python314
                    pkgs.uv
                ];

                shellHook = ''
                    if [ ! -d .venv ]; then
                            uv init
                            uv venv
                        fi
                        source .venv/bin/activate

                        echo "Python3 version: "
                        python3 --version

                        echo "uv version: "
                        uv --version
                '';
            };
    };
}
