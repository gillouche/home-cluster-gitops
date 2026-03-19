{
  description = "Home Cluster GitOps Monorepo";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
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
            echo "Python:   $(python3 --version)"
          '';
        };
      }
    );
}
