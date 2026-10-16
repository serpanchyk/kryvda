#!/bin/sh
# Run from repository root after filling k8s/secret.yaml locally.
set -eu
[ -f k8s/secret.yaml ] || { echo 'Fill k8s/secret.yaml from secret.example.yaml first.' >&2; exit 1; }
if grep -q REPLACE_LOCALLY k8s/secret.yaml; then
  echo 'Replace every placeholder before sealing.' >&2
  exit 1
fi
kubeseal --format yaml --controller-name=sealed-secrets-controller \
  --controller-namespace=kube-system < k8s/secret.yaml > k8s/sealed-secret.yaml.tmp
kubectl annotate --local -f k8s/sealed-secret.yaml.tmp \
  argocd.argoproj.io/sync-wave=-2 --overwrite -o yaml > k8s/sealed-secret.yaml
rm k8s/sealed-secret.yaml.tmp
if ! grep -q '^  *- sealed-secret.yaml\|^- sealed-secret.yaml' k8s/kustomization.yaml; then
  printf '\n- sealed-secret.yaml\n' >> k8s/kustomization.yaml
fi
