import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import supervisely as sly
import trimesh
from supervisely.mesh_annotation.mesh_indices import MESH_INDEX_FIELDS


VERTEX_INDEX_FIELDS = {
    "indices",
    "vertexIndices",
    "verticesIndices",
    "vertex_indices",
    "vertices_indices",
}

NON_VERTEX_INDEX_FIELDS = set(MESH_INDEX_FIELDS) - VERTEX_INDEX_FIELDS
UNLABELED_ID = -1

_PLY_SCALAR_TYPES = {
    "char": ("b", np.int8),
    "int8": ("b", np.int8),
    "uchar": ("B", np.uint8),
    "uint8": ("B", np.uint8),
    "short": ("h", np.int16),
    "int16": ("h", np.int16),
    "ushort": ("H", np.uint16),
    "uint16": ("H", np.uint16),
    "int": ("i", np.int32),
    "int32": ("i", np.int32),
    "uint": ("I", np.uint32),
    "uint32": ("I", np.uint32),
    "float": ("f", np.float32),
    "float32": ("f", np.float32),
    "double": ("d", np.float64),
    "float64": ("d", np.float64),
}


class PerVertexLabelsExportError(RuntimeError):
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message)
        self.details = details or {}


@dataclass
class MeshExportContext:
    dataset_name: str
    item_name: str
    mesh_path: str
    output_path: str


@dataclass
class MeshData:
    vertices: np.ndarray
    faces: List[List[int]]
    vertex_colors: np.ndarray
    vertex_normals: Optional[np.ndarray] = None
    face_normals: Optional[np.ndarray] = None


def export_per_vertex_labels_project(
    local_project_dir: str,
    output_dir: str,
    logger=None,
) -> Dict:
    project_fs = sly.MeshProject(local_project_dir, sly.OpenMode.READ)
    class_map = get_class_map(project_fs.meta)

    output_dir = os.path.abspath(output_dir)
    sly.fs.remove_dir(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    _dump_json(os.path.join(output_dir, "meta.json"), project_fs.meta.to_json())

    exported = []

    for dataset_fs in project_fs.datasets:
        for item_name in dataset_fs:
            ann_json = dataset_fs.get_ann_json(item_name)
            mesh_path = dataset_fs.get_mesh_path(item_name)
            output_path = _get_free_output_path(output_dir, dataset_fs.name, item_name)
            context = MeshExportContext(
                dataset_name=dataset_fs.name,
                item_name=item_name,
                mesh_path=mesh_path,
                output_path=output_path,
            )
            result = export_mesh_to_per_vertex_labels(context, ann_json, class_map)
            result["output_path"] = os.path.relpath(context.output_path, output_dir)
            exported.append(result)
            if logger is not None:
                logger.info(f"Exported per-vertex labels PLY: {output_path}")

    return {
        "format": "per_vertex_labels",
        "exported": len(exported),
        "exported_meshes": exported,
    }


def export_mesh_to_per_vertex_labels(
    context: MeshExportContext,
    ann_json: Dict,
    class_map: Dict[str, Dict],
) -> Dict:
    mesh = _load_mesh_data(context.mesh_path)
    vertex_count = len(mesh.vertices)
    assignments = _build_vertex_assignments(ann_json, vertex_count, class_map)

    vertex_colors = mesh.vertex_colors.copy()
    class_ids = np.full(vertex_count, UNLABELED_ID, dtype=np.int32)
    object_ids = np.full(vertex_count, UNLABELED_ID, dtype=np.int32)
    labeled_count = 0

    for vertex_index, assignment in enumerate(assignments):
        if assignment is None:
            continue
        labeled_count += 1
        vertex_colors[vertex_index] = assignment["color"]
        class_ids[vertex_index] = assignment["class_id"]
        object_ids[vertex_index] = assignment["object_id"]

    _write_per_vertex_labels_ply(
        context.output_path,
        mesh,
        vertex_colors=vertex_colors,
        class_ids=class_ids,
        object_ids=object_ids,
    )
    return {
        "status": "exported",
        "dataset": context.dataset_name,
        "mesh": context.item_name,
        "output_path": context.output_path,
        "vertex_count": vertex_count,
        "face_count": len(mesh.faces),
        "labeled_vertices": labeled_count,
        "unlabeled_vertices": vertex_count - labeled_count,
    }


def get_class_map(project_meta: sly.ProjectMeta) -> Dict[str, Dict]:
    class_map = {}
    color_to_class = {}

    for fallback_id, obj_class in enumerate(project_meta.obj_classes):
        color = _normalize_color(obj_class.color)
        color_key = tuple(color)
        if color_key in color_to_class:
            raise PerVertexLabelsExportError(
                "Duplicate class color {} for classes {!r} and {!r}".format(
                    color, color_to_class[color_key], obj_class.name
                )
            )
        class_id = getattr(obj_class, "sly_id", None)
        if class_id is None:
            class_id = fallback_id
        class_map[obj_class.name] = {"id": int(class_id), "color": color}
        color_to_class[color_key] = obj_class.name

    if len(class_map) == 0:
        raise PerVertexLabelsExportError("Project has no object classes")

    return class_map


def _build_vertex_assignments(
    ann_json: Dict,
    vertex_count: int,
    class_map: Dict[str, Dict],
) -> List[Optional[Dict]]:
    object_key_to_info = {}
    for obj in ann_json.get("objects", []):
        object_key = obj.get("key")
        if object_key is None:
            continue
        object_key_to_info[object_key] = {
            "class_name": obj.get("classTitle"),
            "object_id": _normalize_optional_id(obj.get("id")),
        }

    assignments = [None] * vertex_count

    for figure in ann_json.get("figures", []):
        geometry = figure.get("geometry") or {}
        if not isinstance(geometry, dict):
            raise PerVertexLabelsExportError("Figure geometry must be an object")

        non_vertex_fields = [
            field for field in NON_VERTEX_INDEX_FIELDS if _has_index_payload(geometry.get(field))
        ]
        if len(non_vertex_fields) != 0:
            raise PerVertexLabelsExportError(
                "Non-vertex mesh index fields are not supported: {}".format(
                    ", ".join(sorted(non_vertex_fields))
                )
            )

        vertex_fields = [
            field for field in VERTEX_INDEX_FIELDS if _has_index_payload(geometry.get(field))
        ]
        if len(vertex_fields) > 1:
            raise PerVertexLabelsExportError(
                "Figure contains multiple vertex index fields: {}".format(
                    ", ".join(sorted(vertex_fields))
                )
            )
        if len(vertex_fields) == 0:
            continue

        indices = geometry[vertex_fields[0]]
        if not isinstance(indices, list):
            raise PerVertexLabelsExportError(
                f"Vertex indices must be a list, got {type(indices).__name__}"
            )

        object_info = object_key_to_info.get(figure.get("objectKey"), {})
        class_name = object_info.get("class_name") or figure.get("classTitle")
        if class_name not in class_map:
            raise PerVertexLabelsExportError(f"Class {class_name!r} is missing from project meta")

        object_id = object_info.get("object_id")
        if object_id is None:
            object_id = _normalize_optional_id(figure.get("objectId"))
        if object_id is None:
            object_id = UNLABELED_ID

        assignment = {
            "class_name": class_name,
            "class_id": class_map[class_name]["id"],
            "object_id": object_id,
            "color": class_map[class_name]["color"],
        }

        for index in indices:
            if not isinstance(index, int):
                raise PerVertexLabelsExportError(f"Vertex index {index!r} is not an integer")
            if index < 0 or index >= vertex_count:
                raise PerVertexLabelsExportError(
                    f"Vertex index {index} is out of range for {vertex_count} vertices"
                )
            previous = assignments[index]
            if previous is not None and (
                previous["class_id"] != assignment["class_id"]
                or previous["object_id"] != assignment["object_id"]
            ):
                raise PerVertexLabelsExportError(
                    "Vertex {} has conflicting labels: class/object {}:{} and {}:{}".format(
                        index,
                        previous["class_id"],
                        previous["object_id"],
                        assignment["class_id"],
                        assignment["object_id"],
                    )
                )
            assignments[index] = assignment

    return assignments


def _load_mesh_data(mesh_path: str) -> MeshData:
    if Path(mesh_path).suffix.lower() == ".ply":
        return _load_ply_mesh_data(mesh_path)
    return _load_trimesh_mesh_data(mesh_path)


def _load_ply_mesh_data(mesh_path: str) -> MeshData:
    with open(mesh_path, "rb") as file:
        header_lines = []
        while True:
            raw_line = file.readline()
            if raw_line == b"":
                raise PerVertexLabelsExportError("PLY header is missing end_header")
            line = raw_line.decode("ascii").strip()
            header_lines.append(line)
            if line == "end_header":
                break
        body = file.read()

    header = _parse_ply_header(header_lines)
    if header["format"] == "ascii":
        parsed = _parse_ascii_ply_body(body.decode("ascii"), header)
    elif header["format"] in {"binary_little_endian", "binary_big_endian"}:
        parsed = _parse_binary_ply_body(body, header)
    else:
        raise PerVertexLabelsExportError(f"Unsupported PLY format: {header['format']}")

    vertices = parsed["vertices"]
    faces = parsed["faces"]
    if len(vertices) == 0:
        raise PerVertexLabelsExportError("Mesh has no vertices")
    if len(faces) == 0:
        raise PerVertexLabelsExportError("Mesh has no faces")

    vertex_colors = parsed["vertex_colors"]
    if vertex_colors is None:
        vertex_colors = np.zeros((len(vertices), 3), dtype=np.uint8)

    return MeshData(
        vertices=vertices,
        faces=faces,
        vertex_colors=vertex_colors,
        vertex_normals=parsed["vertex_normals"],
        face_normals=parsed["face_normals"],
    )


def _load_trimesh_mesh_data(mesh_path: str) -> MeshData:
    mesh = trimesh.load(mesh_path, process=False, maintain_order=True)
    if isinstance(mesh, trimesh.Scene):
        geometries = list(mesh.geometry.values())
        if len(geometries) != 1:
            raise PerVertexLabelsExportError(
                f"Mesh scene contains {len(geometries)} geometries; expected exactly one"
            )
        mesh = geometries[0]

    if not isinstance(mesh, trimesh.Trimesh):
        raise PerVertexLabelsExportError(f"Unsupported mesh object type: {type(mesh).__name__}")

    vertices = np.asarray(mesh.vertices)
    faces = [list(map(int, face)) for face in np.asarray(mesh.faces)]
    if len(vertices) == 0:
        raise PerVertexLabelsExportError("Mesh has no vertices")
    if len(faces) == 0:
        raise PerVertexLabelsExportError("Mesh has no faces")

    return MeshData(
        vertices=vertices,
        faces=faces,
        vertex_colors=_get_trimesh_vertex_colors(mesh),
        vertex_normals=_cached_normals(mesh, "vertex"),
        face_normals=_cached_normals(mesh, "face"),
    )


def _parse_ply_header(header_lines: List[str]) -> Dict:
    if len(header_lines) < 3 or header_lines[0] != "ply":
        raise PerVertexLabelsExportError("File is not a PLY mesh")

    elements = []
    current_element = None
    ply_format = None

    for line in header_lines[1:]:
        if line == "" or line.startswith("comment "):
            continue
        parts = line.split()
        if len(parts) == 0:
            continue
        if parts[0] == "format":
            if len(parts) < 3:
                raise PerVertexLabelsExportError("Invalid PLY format line")
            ply_format = parts[1]
        elif parts[0] == "element":
            if len(parts) != 3:
                raise PerVertexLabelsExportError(f"Invalid PLY element line: {line!r}")
            current_element = {
                "name": parts[1],
                "count": int(parts[2]),
                "properties": [],
            }
            elements.append(current_element)
        elif parts[0] == "property":
            if current_element is None:
                raise PerVertexLabelsExportError("PLY property appeared before an element")
            if len(parts) >= 5 and parts[1] == "list":
                property_info = {
                    "kind": "list",
                    "count_type": parts[2],
                    "item_type": parts[3],
                    "name": parts[4],
                }
            elif len(parts) == 3:
                property_info = {
                    "kind": "scalar",
                    "type": parts[1],
                    "name": parts[2],
                }
            else:
                raise PerVertexLabelsExportError(f"Invalid PLY property line: {line!r}")
            _validate_ply_property_type(property_info)
            current_element["properties"].append(property_info)
        elif parts[0] == "end_header":
            break

    if ply_format is None:
        raise PerVertexLabelsExportError("PLY format is missing")
    return {"format": ply_format, "elements": elements}


def _parse_ascii_ply_body(body: str, header: Dict) -> Dict:
    rows = iter(body.splitlines())
    parsed = _empty_parsed_mesh()

    for element in header["elements"]:
        for _ in range(element["count"]):
            try:
                tokens = next(rows).split()
            except StopIteration as exc:
                raise PerVertexLabelsExportError(
                    f"PLY body ended while reading element {element['name']!r}"
                ) from exc
            values = _parse_ascii_element(tokens, element)
            _store_ply_element(parsed, element["name"], values)

    return _finalize_parsed_mesh(parsed)


def _parse_ascii_element(tokens: List[str], element: Dict) -> Dict:
    values = {}
    position = 0
    for property_info in element["properties"]:
        if property_info["kind"] == "scalar":
            if position >= len(tokens):
                raise PerVertexLabelsExportError(
                    f"Not enough values for PLY element {element['name']!r}"
                )
            values[property_info["name"]] = _parse_ascii_scalar(
                tokens[position], property_info["type"]
            )
            position += 1
            continue

        if position >= len(tokens):
            raise PerVertexLabelsExportError(
                f"Missing list size for PLY property {property_info['name']!r}"
            )
        item_count = int(_parse_ascii_scalar(tokens[position], property_info["count_type"]))
        position += 1
        end_position = position + item_count
        if end_position > len(tokens):
            raise PerVertexLabelsExportError(
                f"Not enough list values for PLY property {property_info['name']!r}"
            )
        values[property_info["name"]] = [
            _parse_ascii_scalar(token, property_info["item_type"])
            for token in tokens[position:end_position]
        ]
        position = end_position
    return values


def _parse_binary_ply_body(body: bytes, header: Dict) -> Dict:
    parsed = _empty_parsed_mesh()
    endian = "<" if header["format"] == "binary_little_endian" else ">"
    offset = 0

    for element in header["elements"]:
        for _ in range(element["count"]):
            values, offset = _parse_binary_element(body, offset, endian, element)
            _store_ply_element(parsed, element["name"], values)

    return _finalize_parsed_mesh(parsed)


def _parse_binary_element(body: bytes, offset: int, endian: str, element: Dict):
    values = {}
    for property_info in element["properties"]:
        if property_info["kind"] == "scalar":
            value, offset = _unpack_binary_scalar(body, offset, endian, property_info["type"])
            values[property_info["name"]] = value
            continue

        item_count, offset = _unpack_binary_scalar(
            body, offset, endian, property_info["count_type"]
        )
        item_count = int(item_count)
        items = []
        for _ in range(item_count):
            value, offset = _unpack_binary_scalar(
                body, offset, endian, property_info["item_type"]
            )
            items.append(value)
        values[property_info["name"]] = items
    return values, offset


def _unpack_binary_scalar(body: bytes, offset: int, endian: str, type_name: str):
    format_char = _PLY_SCALAR_TYPES[type_name][0]
    format_string = endian + format_char
    size = struct.calcsize(format_string)
    if offset + size > len(body):
        raise PerVertexLabelsExportError("PLY binary body ended unexpectedly")
    return struct.unpack_from(format_string, body, offset)[0], offset + size


def _empty_parsed_mesh() -> Dict:
    return {
        "vertices": [],
        "faces": [],
        "vertex_normals": [],
        "face_normals": [],
        "vertex_colors": [],
        "has_vertex_normals": False,
        "has_face_normals": False,
        "has_vertex_colors": False,
    }


def _store_ply_element(parsed: Dict, element_name: str, values: Dict) -> None:
    if element_name == "vertex":
        _store_ply_vertex(parsed, values)
    elif element_name == "face":
        _store_ply_face(parsed, values)


def _store_ply_vertex(parsed: Dict, values: Dict) -> None:
    if not all(key in values for key in ("x", "y", "z")):
        raise PerVertexLabelsExportError("PLY vertex element must contain x, y and z")
    parsed["vertices"].append([values["x"], values["y"], values["z"]])

    if all(key in values for key in ("nx", "ny", "nz")):
        parsed["has_vertex_normals"] = True
        parsed["vertex_normals"].append([values["nx"], values["ny"], values["nz"]])
    elif parsed["has_vertex_normals"]:
        raise PerVertexLabelsExportError("PLY vertex normals are incomplete")

    color_names = _get_ply_color_names(values)
    if color_names is not None:
        parsed["has_vertex_colors"] = True
        parsed["vertex_colors"].append([_clamp_color(values[name]) for name in color_names])
    elif parsed["has_vertex_colors"]:
        raise PerVertexLabelsExportError("PLY vertex colors are incomplete")


def _store_ply_face(parsed: Dict, values: Dict) -> None:
    face_property = _get_face_index_property(values)
    if face_property is None:
        raise PerVertexLabelsExportError("PLY face element must contain vertex indices")

    face = values[face_property]
    if len(face) < 3:
        raise PerVertexLabelsExportError("PLY face has fewer than 3 vertices")
    parsed["faces"].append([int(index) for index in face])

    if all(key in values for key in ("nx", "ny", "nz")):
        parsed["has_face_normals"] = True
        parsed["face_normals"].append([values["nx"], values["ny"], values["nz"]])
    elif parsed["has_face_normals"]:
        raise PerVertexLabelsExportError("PLY face normals are incomplete")


def _finalize_parsed_mesh(parsed: Dict) -> Dict:
    vertices = np.asarray(parsed["vertices"], dtype=np.float64)
    faces = parsed["faces"]

    for face in faces:
        for index in face:
            if index < 0 or index >= len(vertices):
                raise PerVertexLabelsExportError("Face indices are out of vertex range")

    if parsed["has_vertex_normals"]:
        vertex_normals = np.asarray(parsed["vertex_normals"], dtype=np.float64)
        if vertex_normals.shape != vertices.shape:
            raise PerVertexLabelsExportError("PLY vertex normals shape does not match vertices")
    else:
        vertex_normals = None

    if parsed["has_face_normals"]:
        face_normals = np.asarray(parsed["face_normals"], dtype=np.float64)
        if face_normals.shape != (len(faces), 3):
            raise PerVertexLabelsExportError("PLY face normals shape does not match faces")
    else:
        face_normals = None

    if parsed["has_vertex_colors"]:
        vertex_colors = np.asarray(parsed["vertex_colors"], dtype=np.uint8)
        if vertex_colors.shape != (len(vertices), 3):
            raise PerVertexLabelsExportError("PLY vertex color shape does not match vertices")
    else:
        vertex_colors = None

    return {
        "vertices": vertices,
        "faces": faces,
        "vertex_normals": vertex_normals,
        "face_normals": face_normals,
        "vertex_colors": vertex_colors,
    }


def _write_per_vertex_labels_ply(
    output_path: str,
    mesh: MeshData,
    vertex_colors: np.ndarray,
    class_ids: np.ndarray,
    object_ids: np.ndarray,
) -> None:
    vertices = np.asarray(mesh.vertices)
    faces = mesh.faces
    if vertices.ndim != 2 or vertices.shape[1] != 3:
        raise PerVertexLabelsExportError("PLY export requires Nx3 vertices")
    if vertex_colors.shape != (len(vertices), 3):
        raise PerVertexLabelsExportError(
            f"Expected {len(vertices)} RGB vertex colors, got shape {vertex_colors.shape}"
        )
    if class_ids.shape != (len(vertices),):
        raise PerVertexLabelsExportError(
            f"Expected {len(vertices)} class IDs, got shape {class_ids.shape}"
        )
    if object_ids.shape != (len(vertices),):
        raise PerVertexLabelsExportError(
            f"Expected {len(vertices)} object IDs, got shape {object_ids.shape}"
        )

    vertex_normals = mesh.vertex_normals
    face_normals = mesh.face_normals
    if vertex_normals is not None and vertex_normals.shape != vertices.shape:
        raise PerVertexLabelsExportError("Vertex normals shape does not match vertices")
    if face_normals is not None and face_normals.shape != (len(faces), 3):
        raise PerVertexLabelsExportError("Face normals shape does not match faces")

    for face in faces:
        if len(face) < 3:
            raise PerVertexLabelsExportError("PLY face has fewer than 3 vertices")
        for index in face:
            if index < 0 or index >= len(vertices):
                raise PerVertexLabelsExportError("Face indices are out of vertex range")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="ascii", newline="\n") as file:
        file.write("ply\n")
        file.write("format ascii 1.0\n")
        file.write("comment exported by Supervisely export-mesh-project\n")
        file.write(f"element vertex {len(vertices)}\n")
        file.write("property float x\nproperty float y\nproperty float z\n")
        if vertex_normals is not None:
            file.write("property float nx\nproperty float ny\nproperty float nz\n")
        file.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        file.write("property int class_id\nproperty int object_id\n")
        file.write(f"element face {len(faces)}\n")
        file.write("property list uchar int vertex_indices\n")
        if face_normals is not None:
            file.write("property float nx\nproperty float ny\nproperty float nz\n")
        file.write("end_header\n")

        for vertex_index, vertex in enumerate(vertices):
            values = [_format_float(value) for value in vertex]
            if vertex_normals is not None:
                values.extend(_format_float(value) for value in vertex_normals[vertex_index])
            values.extend(str(int(value)) for value in vertex_colors[vertex_index])
            values.append(str(int(class_ids[vertex_index])))
            values.append(str(int(object_ids[vertex_index])))
            file.write(" ".join(values) + "\n")

        for face_index, face in enumerate(faces):
            values = [str(len(face))]
            values.extend(str(int(value)) for value in face)
            if face_normals is not None:
                values.extend(_format_float(value) for value in face_normals[face_index])
            file.write(" ".join(values) + "\n")


def _cached_normals(mesh: trimesh.Trimesh, level: str) -> Optional[np.ndarray]:
    cache_key = f"{level}_normals"
    cache = getattr(mesh, "_cache", None)
    if cache is not None and cache_key in cache:
        value = cache[cache_key]
        if value is not None:
            return np.asarray(value)

    attributes = getattr(mesh, f"{level}_attributes", {}) or {}
    if all(key in attributes for key in ("nx", "ny", "nz")):
        return np.column_stack([attributes["nx"], attributes["ny"], attributes["nz"]])

    return None


def _get_trimesh_vertex_colors(mesh: trimesh.Trimesh) -> np.ndarray:
    visual = getattr(mesh, "visual", None)
    if visual is not None and getattr(visual, "kind", None) == "vertex":
        colors = getattr(visual, "vertex_colors", None)
        if colors is not None:
            colors = np.asarray(colors)
            if colors.shape[0] == len(mesh.vertices) and colors.shape[1] >= 3:
                return colors[:, :3].astype(np.uint8, copy=True)
    return np.zeros((len(mesh.vertices), 3), dtype=np.uint8)


def _normalize_color(color) -> List[int]:
    if isinstance(color, str):
        value = color.strip()
        if value.startswith("#"):
            value = value[1:]
        if len(value) != 6:
            raise PerVertexLabelsExportError(f"Invalid hex color {color!r}")
        rgb = [int(value[i : i + 2], 16) for i in (0, 2, 4)]
    elif isinstance(color, (list, tuple)) and len(color) >= 3:
        rgb = [int(color[0]), int(color[1]), int(color[2])]
    else:
        raise PerVertexLabelsExportError(f"Unsupported color value {color!r}")

    for channel in rgb:
        if channel < 0 or channel > 255:
            raise PerVertexLabelsExportError(f"Color channel {channel!r} is outside 0..255")
    return rgb


def _normalize_optional_id(value) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _validate_ply_property_type(property_info: Dict) -> None:
    if property_info["kind"] == "scalar":
        if property_info["type"] not in _PLY_SCALAR_TYPES:
            raise PerVertexLabelsExportError(f"Unsupported PLY type: {property_info['type']}")
        return

    if property_info["count_type"] not in _PLY_SCALAR_TYPES:
        raise PerVertexLabelsExportError(
            f"Unsupported PLY list count type: {property_info['count_type']}"
        )
    if property_info["item_type"] not in _PLY_SCALAR_TYPES:
        raise PerVertexLabelsExportError(
            f"Unsupported PLY list item type: {property_info['item_type']}"
        )


def _parse_ascii_scalar(value: str, type_name: str):
    dtype = _PLY_SCALAR_TYPES[type_name][1]
    if np.issubdtype(dtype, np.integer):
        return int(value)
    return float(value)


def _get_ply_color_names(values: Dict) -> Optional[List[str]]:
    for color_names in (("red", "green", "blue"), ("diffuse_red", "diffuse_green", "diffuse_blue")):
        if all(name in values for name in color_names):
            return list(color_names)
    return None


def _get_face_index_property(values: Dict) -> Optional[str]:
    for name in ("vertex_indices", "vertex_index"):
        if name in values:
            return name
    for name, value in values.items():
        if isinstance(value, list) and "vertex" in name:
            return name
    return None


def _clamp_color(value) -> int:
    return max(0, min(255, int(round(float(value)))))


def _has_index_payload(value) -> bool:
    if value is None:
        return False
    if isinstance(value, list) and len(value) == 0:
        return False
    return True


def _format_float(value) -> str:
    return "{:.17g}".format(float(value))


def _get_free_output_path(output_dir: str, dataset_name: str, item_name: str) -> str:
    dataset_dir = os.path.join(output_dir, *Path(dataset_name).parts)
    stem = Path(item_name).stem
    candidate = os.path.join(dataset_dir, f"{stem}.ply")
    if not os.path.exists(candidate):
        return candidate

    index = 1
    while True:
        candidate = os.path.join(dataset_dir, f"{stem}_{index:03d}.ply")
        if not os.path.exists(candidate):
            return candidate
        index += 1


def _dump_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
