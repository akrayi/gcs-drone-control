"""CI-only update of the GitOps deployment descriptor; never writes credentials."""
import os
import re
from pathlib import Path
import yaml

registry = os.environ["ACR_NAME"]
version = os.environ["VERSION"]
if not re.fullmatch(r"[a-zA-Z0-9]{5,50}", registry) or not re.fullmatch(r"v[1-9][0-9]*", version):
    raise ValueError("Invalid registry name or release version")
path = Path("gitops/aks/kustomization.yaml")
data = yaml.safe_load(path.read_text())
images = []
for component in ("backend", "frontend"):
    digest = os.environ[f"{component.upper()}_DIGEST"]
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError("Expected immutable SHA256 image digest")
    images.append({"name": f"YOUR_ACR.azurecr.io/gcs-{component}",
                   "newName": f"{registry}.azurecr.io/gcs-{component}",
                   "newTag": version, "digest": digest})
data["images"] = images
path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
print(f"Updated GitOps images to {version}, pinned by digest")
