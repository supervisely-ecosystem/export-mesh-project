<div align="center" markdown>
<img src="https://user-images.githubusercontent.com/12828725/199022135-4161917c-05f8-4681-9dc1-b5e10ee8bb0f.png">

# Export Mesh Project

<p align="center">
  <a href="#overview">Overview</a> |
  <a href="#how-to-run">How To Run</a> |
  <a href="#how-to-use">How To Use</a>
</p>

[![](https://img.shields.io/badge/supervisely-ecosystem-brightgreen)](https://ecosystem.supervisely.com)
[![](https://img.shields.io/badge/slack-chat-green.svg?logo=slack)](https://supervisely.com/slack)
[![views](https://app.supervisely.com/img/badges/views/supervisely-ecosystem/export-mesh-project.png)](https://supervisely.com)
[![runs](https://app.supervisely.com/img/badges/runs/supervisely-ecosystem/export-mesh-project.png)](https://supervisely.com)

</div>

# Overview

Export a Supervisely mesh project or dataset as a downloadable archive.

Supported formats:

- **Supervisely**: exports the project in Supervisely mesh format.
- **Per-Vertex Labels**: exports ASCII PLY files with labels projected onto vertices.

In Per-Vertex Labels format, labeled vertices receive RGB values from their class color and two extra vertex attributes: `class_id` and `object_id`. Unlabeled vertices keep their original RGB values and receive `-1` for both IDs. The archive also includes `meta.json` with class-color relationships in Supervisely format.

# How To Run

1. Run the app from the context menu of a **Mesh Project** or **Mesh Dataset**: `Download as` -> `Export Mesh Project`.

2. Select the export format in the modal window and press **Run**.

# How To Use

1. Wait for the app to process the data. When it finishes, a download link will become available in the task output.

2. The resulting archive is also uploaded to Team Files:

- `Team Files` -> `tmp` -> `supervisely` -> `export` -> `export-supervisely-mesh-projects` -> `<task_id>_<projectId>_<projectName>.tar`

**Per-Vertex Labels output structure:**

```text
project_per_vertex_labels.tar
|-- meta.json
`-- dataset_name
    |-- mesh_1.ply
    |-- mesh_2.ply
    `-- ...
```
