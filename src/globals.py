import os
from distutils.util import strtobool
from urllib.parse import urlparse

from dotenv import load_dotenv
import supervisely as sly


if sly.is_development():
    load_dotenv("debug.env")
    load_dotenv(os.path.expanduser("~/supervisely.env"))


api: sly.Api = sly.Api.from_env()
DATA_DIR = sly.app.get_data_dir()

TEAM_ID = sly.env.team_id()
WORKSPACE_ID = sly.env.workspace_id()
TASK_ID = sly.env.task_id()
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))

PROJECT_ID = sly.env.project_id(raise_not_found=False)
DATASET_ID = sly.env.dataset_id(raise_not_found=False)
assert DATASET_ID or PROJECT_ID, "Either dataset or project ID must be provided"

format = os.getenv("modal.state.format", "sly")
download_meshes = bool(strtobool(os.getenv("modal.state.downloadMeshes", "true")))
download_annotations = True
export_destination = os.getenv("modal.state.exportDestination", "regular")
cloud_export_path = os.getenv("modal.state.cloudExportPath", "").strip()
_cloud_storage_schemes = {"s3", "google", "gcs", "azure", "minio", "fs"}

if export_destination not in {"regular", "cloud"}:
    raise ValueError(f"Unsupported export destination: {export_destination!r}")
if export_destination == "cloud":
    if cloud_export_path == "":
        raise ValueError("Cloud export destination folder is not selected")

    parsed_cloud_path = urlparse(cloud_export_path)
    if (
        parsed_cloud_path.scheme not in _cloud_storage_schemes
        or parsed_cloud_path.netloc == ""
    ):
        raise ValueError(
            "Invalid cloud export destination. Select a folder from Cloud Storages."
        )

if format == "per_vertex_labels":
    download_meshes = True
