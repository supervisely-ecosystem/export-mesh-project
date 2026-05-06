import os

import supervisely as sly

import globals as g
import per_vertex_labels
import workflow as w


def _remote_archive_path(remote_dir: str, archive_name: str) -> str:
    return f"{remote_dir.rstrip('/')}/{archive_name}"


def _get_free_storage_path(api: sly.Api, team_id: int, remote_path: str) -> str:
    if not api.storage.exists(team_id, remote_path):
        return remote_path

    base, ext = os.path.splitext(remote_path)
    index = 1
    while True:
        candidate = f"{base}_{index}{ext}"
        if not api.storage.exists(team_id, candidate):
            return candidate
        index += 1


@sly.timeit
def download(api: sly.Api, task_id):
    if g.DATASET_ID:
        dataset = api.dataset.get_info_by_id(g.DATASET_ID)
        project = api.project.get_info_by_id(dataset.project_id)
        w.workflow_input(api, dataset.id, "dataset")
    elif g.PROJECT_ID:
        project = api.project.get_info_by_id(g.PROJECT_ID)
        w.workflow_input(api, project.id, "project")
    else:
        raise ValueError("PROJECT_ID or DATASET_ID should be provided")

    source_dir = os.path.join(g.DATA_DIR, f"{project.id}_{project.name}")
    sly.fs.remove_dir(source_dir)

    sly.download_mesh_project(
        api=api,
        project_id=project.id,
        dest_dir=source_dir,
        dataset_ids=[g.DATASET_ID] if g.DATASET_ID else None,
        download_meshes=g.download_meshes,
        download_meshes_info=False,
        batch_size=g.BATCH_SIZE,
        log_progress=True,
    )

    archive_dir = source_dir
    if g.format == "per_vertex_labels":
        archive_dir = os.path.join(g.DATA_DIR, f"{project.id}_{project.name}_per_vertex_labels")
        per_vertex_labels.export_per_vertex_labels_project(
            local_project_dir=source_dir,
            output_dir=archive_dir,
            logger=sly.logger,
        )
    elif g.format != "sly":
        raise ValueError(f"Unsupported format: {g.format}")

    full_archive_name = f"{project.id}_{project.name}.tar"
    if g.format == "per_vertex_labels":
        full_archive_name = f"{project.id}_{project.name}_per_vertex_labels.tar"
    result_archive = os.path.join(g.DATA_DIR, full_archive_name)
    sly.fs.archive_directory(archive_dir, result_archive)
    sly.logger.info("Result directory is archived")

    upload_progress = []

    def _print_progress(monitor, progress_holder):
        if len(progress_holder) == 0:
            progress_holder.append(
                sly.Progress(
                    message="Upload {!r}".format(full_archive_name),
                    total_cnt=monitor.len,
                    ext_logger=sly.logger,
                    is_size=True,
                )
            )
        progress_holder[0].set_current_value(monitor.bytes_read)

    if g.export_destination == "cloud":
        remote_archive_path = _remote_archive_path(g.cloud_export_path, full_archive_name)
        remote_archive_path = _get_free_storage_path(api, g.TEAM_ID, remote_archive_path)
        api.storage.upload_bulk(
            g.TEAM_ID,
            [result_archive],
            [remote_archive_path],
            lambda monitor: _print_progress(monitor, upload_progress),
        )
        sly.logger.info("Uploaded to Cloud Storage: {!r}".format(remote_archive_path))
        api.task.set_output_text(
            task_id,
            "Archive uploaded to Cloud Storage",
            remote_archive_path,
            zmdi_icon="zmdi-cloud-upload",
        )
    else:
        remote_archive_path = os.path.join(
            sly.team_files.RECOMMENDED_EXPORT_PATH,
            f"export-supervisely-mesh-projects/{task_id}_{full_archive_name}",
        )
        remote_archive_path = api.file.get_free_name(g.TEAM_ID, remote_archive_path)
        file_info = api.file.upload(
            g.TEAM_ID,
            result_archive,
            remote_archive_path,
            lambda monitor: _print_progress(monitor, upload_progress),
        )
        sly.logger.info("Uploaded to Team-Files: {!r}".format(file_info.storage_path))
        api.task.set_output_archive(
            task_id, file_info.id, full_archive_name, file_url=file_info.storage_path
        )
        w.workflow_output(api, file_info)


@sly.handle_exceptions(has_ui=False)
def main():
    sly.logger.info(
        "Script arguments",
        extra={
            "TEAM_ID": g.TEAM_ID,
            "WORKSPACE_ID": g.WORKSPACE_ID,
            "PROJECT_ID": g.PROJECT_ID,
            "DATASET_ID": g.DATASET_ID,
            "format": g.format,
            "download_meshes": g.download_meshes,
            "export_destination": g.export_destination,
            "cloud_export_path": g.cloud_export_path,
        },
    )

    download(g.api, g.TASK_ID)


if __name__ == "__main__":
    sly.main_wrapper("main", main)
