{ pkgs }:

pkgs.mkShell {
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
    echo "Kubectl: $(kubectl version --client -o json | jq -r .clientVersion.gitVersion)"
    echo "Python: $(python3 --version)"
  '';
}
