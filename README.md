<div align="center" markdown>
<img src="https://github.com/user-attachments/assets/df161a1c-163e-4c1e-8d76-5b42ba210ae3">

# Export Mesh Project

<p align="center">
  <a href="#overview">Overview</a> |
  <a href="#how-to-run">How To Run</a> |
  <a href="#how-to-use">How To Use</a>
</p>

[![](https://img.shields.io/badge/supervisely-ecosystem-brightgreen)](https://ecosystem.supervisely.com)
[![](https://img.shields.io/badge/slack-chat-green.svg?logo=slack)](https://supervisely.com/slack)
![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/supervisely-ecosystem/export-mesh-project)
[![views](https://app.supervisely.com/img/badges/views/supervisely-ecosystem/export-mesh-project.png)](https://supervisely.com)
[![runs](https://app.supervisely.com/img/badges/runs/supervisely-ecosystem/export-mesh-project.png)](https://supervisely.com)

</div>

# Overview

Export a Supervisely mesh project or dataset as a downloadable archive.

Export formats:

- **Supervisely**: exports the project in Supervisely mesh format.
- **Per-Vertex Labels**: exports ASCII PLY files with labels projected onto vertices.

In Per-Vertex Labels format, source meshes (`.ply`, `.obj`, `.stl`) are written as ASCII PLY files. Labeled vertices receive RGB values from their class color and two extra vertex attributes: `class_id` and `object_id`. Unlabeled vertices keep their original RGB values (meshes without vertex colors are filled with neutral white `255 255 255`), vertex alpha is preserved when present, and `-1` is written for both IDs. Mesh topology (vertices, faces, normals) is preserved unchanged. The archive also includes `meta.json` with class-color relationships in Supervisely format.

# How To Run

1. Run the app from the context menu of a **Mesh Project** or **Mesh Dataset**: `Download as` → `Export Mesh Project`.

2. Select the export format and destination in the modal window, then press **Run**.

# How To Use

1. Wait for the app to process the data. When it finishes, a download link will become available in the task output.

2. With **Regular export**, the resulting archive is also uploaded to Team Files:

- `Team Files` → `tmp` → `supervisely` → `export` → `export-supervisely-mesh-projects` → `<task_id>_<projectId>_<projectName>.tar`

For the Per-Vertex Labels format, the archive name gets a `_per_vertex_labels` suffix: `<task_id>_<projectId>_<projectName>_per_vertex_labels.tar`.

3. With **Cloud export**, the resulting archive is uploaded to the selected folder.

## Formats file structures

**Supervisely output structure**

```text
📦 project_name
├── 📂 dataset_name
│   ├── 📂 meshes
│   │   ├── 📄 mesh_01.ply
│   │   └── 📄 mesh_02.ply
│   ├── 📂 annotations
│   │   ├── 📂 mesh_01.ply
│   │   │   ├── 📄 annotation.json
│   │   │   └── 📂 geometries
│   │   │       ├── 📄 4178a5fbc3284da9876d76ef9688de09.indices.bin
│   │   │       └── 📄 9c3e12ab7f1045bc901d34ef5a72c108.indices.bin
│   │   └── 📂 mesh_02.ply
│   │       ├── 📄 annotation.json
│   │       └── 📂 geometries
│   │           └── 📄 b2d09f3e1c6840a7882e15cf4d39710a.indices.bin
│   └── 📂 datasets
│       └── 📂 nested_dataset_name
│           ├── 📂 meshes
│           └── 📂 annotations
└── 📄 meta.json
```

**Per-Vertex Labels output structure:**

```text
📦 project name
├── 📂 dataset_name
│   ├── 📄 mesh_01.ply
│   ├── 📄 mesh_02.ply
│   └── 📂 nested_dataset_name
│       └── 📄 mesh_03.ply
└── 📄 meta.json
```
