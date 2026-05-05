<div align="center" markdown>

# Export Mesh Project

</div>

## Overview

Export a Supervisely mesh project or dataset as a downloadable archive.

Supported formats:

- Supervisely mesh project format.
- Per-Vertex Labels PLY.

The Per-Vertex Labels export writes ASCII PLY files with project class colors projected into vertex RGB values. Labeled vertices also receive `class_id` and `object_id` attributes. Unlabeled vertices keep their original RGB values and receive `-1` for both IDs.

The archive includes painted mesh files and root `meta.json` in Supervisely format. The exporter preserves mesh vertices, faces, and source normals when they are present in the source PLY representation. It does not decimate, remesh, smooth, fill holes, triangulate, or recompute normals.

## Development

The mesh SDK APIs are currently expected from the `meshes` branch:

```bash
./create_venv.sh
```

For local smoke testing, set the modal state in `debug.env`.
