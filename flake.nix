{
  description = "Home Cluster GitOps Monorepo";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
    flake-utils.url = "github:numtide/flake-utils";
    attic.url = "github:zhaofengli/attic";
  };

  outputs = { self, nixpkgs, flake-utils, attic }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            # Kubernetes Tools
            argocd
            kubectl
            kubernetes-helm
            kubectx
            kubeseal
            popeye
            k9s
            
            # Attic (from flake input)
            attic.packages.${system}.attic-client
            attic.packages.${system}.attic-server
            
            # Python Tools
            python314
            uv
          ];

          shellHook = ''
            # Setup Python environment in tools/ if it exists
            if [ -d "tools" ]; then
              if [ ! -d "tools/.venv" ]; then
                echo "Initializing Python virtual environment in tools/..."
                (cd tools && uv venv)
              fi
              source tools/.venv/bin/activate
            fi

            echo "Environment loaded!"
            echo "Kubectl:  $(kubectl version --client -o json | jq -r .clientVersion.gitVersion)"
            echo "ArgoCD:   $(argocd version --client --short)"
            echo "Kubeseal: $(kubeseal --version | awk '{print $NF}')"
            echo "Attic:    $(attic --version)"
            echo "AtticD:   $(atticd --version)"
            echo "Python:   $(python3 --version)"
          '';
        };
      }
    );
}
