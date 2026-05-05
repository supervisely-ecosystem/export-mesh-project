import os
from distutils.util import strtobool

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

if format == "per_vertex_labels":
    download_meshes = True
