"""Validate already-rendered manifests against Kubernetes 1.34 JSON schemas.

Usage: python scripts/validate-manifests.py rendered-base.yaml rendered-aks.yaml
Requires: pip install kubernetes-validate==1.37.0
"""
import sys
from pathlib import Path
import yaml
from kubernetes_validate import validate

count = 0
for filename in sys.argv[1:]:
    for document in yaml.safe_load_all(Path(filename).read_text(encoding="utf-8-sig")):
        if document:
            validate(document, "1.34.0", strict=True)
            count += 1
if not count:
    raise SystemExit("Pass one or more rendered Kubernetes YAML files")
print(f"Validated {count} resources against strict Kubernetes 1.34 schemas")
