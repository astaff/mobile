"""3MF exporter with one object per STL part."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
import zipfile

import math

from mbl.stl import Triangle, read_binary_stl

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CTYPE_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


def _fmt(v: float) -> str:
    txt = f"{v:.6f}".rstrip("0").rstrip(".")
    if txt in {"", "-0"}:
        return "0"
    return txt


def _mesh_bounds_xy(triangles: list[Triangle]) -> tuple[float, float, float, float]:
    min_x = float("inf")
    max_x = float("-inf")
    min_y = float("inf")
    max_y = float("-inf")

    for v0, v1, v2 in triangles:
        for vx, vy, _vz in (v0, v1, v2):
            min_x = min(min_x, vx)
            max_x = max(max_x, vx)
            min_y = min(min_y, vy)
            max_y = max(max_y, vy)

    if min_x == float("inf"):
        return 0.0, 0.0, 0.0, 0.0

    return min_x, max_x, min_y, max_y


def _build_model_xml(part_meshes: list[tuple[str, list[Triangle], float, float]]) -> bytes:
    # Manual XML assembly is much faster than ElementTree for large meshes.
    chunks: list[str] = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<model unit="millimeter" xml:lang="en-US" xmlns="{CORE_NS}">',
        "<resources>",
    ]
    build_items: list[str] = []

    for object_id, (name, triangles, offset_x, offset_y) in enumerate(part_meshes, start=1):
        safe_name = escape(name, {'"': "&quot;"})
        chunks.append(f'<object id="{object_id}" type="model" name="{safe_name}"><mesh><vertices>')

        vertex_indices: dict[tuple[float, float, float], int] = {}
        tri_indices: list[tuple[int, int, int]] = []

        for v0, v1, v2 in triangles:
            tri: list[int] = []
            for vx, vy, vz in (v0, v1, v2):
                key = (vx + offset_x, vy + offset_y, vz)
                idx = vertex_indices.get(key)
                if idx is None:
                    idx = len(vertex_indices)
                    vertex_indices[key] = idx
                    chunks.append(
                        f'<vertex x="{_fmt(key[0])}" y="{_fmt(key[1])}" z="{_fmt(key[2])}"/>'
                    )
                tri.append(idx)
            tri_indices.append((tri[0], tri[1], tri[2]))

        chunks.append("</vertices><triangles>")
        for a, b, c in tri_indices:
            chunks.append(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>')
        chunks.append("</triangles></mesh></object>")

        build_items.append(f'<item objectid="{object_id}"/>')

    chunks.append("</resources><build>")
    chunks.extend(build_items)
    chunks.append("</build></model>")
    return "".join(chunks).encode("utf-8")


def _content_types_xml() -> bytes:
    ET.register_namespace("", CTYPE_NS)
    root = ET.Element(
        f"{{{CTYPE_NS}}}Types",
    )
    ET.SubElement(
        root,
        f"{{{CTYPE_NS}}}Default",
        {
            "Extension": "rels",
            "ContentType": "application/vnd.openxmlformats-package.relationships+xml",
        },
    )
    ET.SubElement(
        root,
        f"{{{CTYPE_NS}}}Default",
        {
            "Extension": "model",
            "ContentType": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
        },
    )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _rels_xml() -> bytes:
    ET.register_namespace("", REL_NS)
    root = ET.Element(f"{{{REL_NS}}}Relationships")
    ET.SubElement(
        root,
        f"{{{REL_NS}}}Relationship",
        {
            "Target": "/3D/3dmodel.model",
            "Id": "rel0",
            "Type": "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel",
        },
    )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _rotate_triangles_z(triangles: list[Triangle], degrees: float) -> list[Triangle]:
    """Rotate all triangles around the Z axis by *degrees*."""
    rad = math.radians(degrees)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    rotated: list[Triangle] = []
    for v0, v1, v2 in triangles:
        new_verts = []
        for x, y, z in (v0, v1, v2):
            new_verts.append((x * cos_a - y * sin_a, x * sin_a + y * cos_a, z))
        rotated.append((tuple(new_verts[0]), tuple(new_verts[1]), tuple(new_verts[2])))  # type: ignore[arg-type]
    return rotated


def _layout_parts_to_plates(
    inputs: list[Path],
    spacing: float,
    build_plate_width: float,
    build_plate_depth: float,
    edge_margin: float,
) -> list[list[tuple[str, list[Triangle], float, float]]]:
    """Lay out parts across one or more build plates, top-to-bottom, left-to-right.

    Returns a list of plates, each plate a list of (name, triangles, offset_x, offset_y).
    """
    usable_width = build_plate_width - 2.0 * edge_margin
    usable_depth = build_plate_depth - 2.0 * edge_margin
    if usable_width <= 0 or usable_depth <= 0:
        raise ValueError(
            f"Build plate {build_plate_width:.1f}x{build_plate_depth:.1f} mm is too "
            f"small for edge margin {edge_margin:.1f} mm"
        )

    plates: list[list[tuple[str, list[Triangle], float, float]]] = [[]]
    cursor_x = edge_margin
    cursor_y = edge_margin
    row_depth = 0.0

    for path in inputs:
        triangles, _bounds = read_binary_stl(path)
        min_x, max_x, min_y, max_y = _mesh_bounds_xy(triangles)
        width = max_x - min_x
        depth = max_y - min_y

        if width > usable_width or depth > usable_depth:
            # Rotate 45° to fit diagonally on the plate.
            triangles = _rotate_triangles_z(triangles, 45.0)
            min_x, max_x, min_y, max_y = _mesh_bounds_xy(triangles)
            width = max_x - min_x
            depth = max_y - min_y
            if width > usable_width or depth > usable_depth:
                raise ValueError(
                    f"Part '{path.stem}' ({width:.2f}x{depth:.2f} mm) exceeds "
                    f"usable plate area even after 45° rotation "
                    f"(plate {build_plate_width:.1f}x{build_plate_depth:.1f}, "
                    f"edge margin {edge_margin:.1f})"
                )

        # Wrap to next row when this part no longer fits current row.
        if cursor_x > edge_margin and (cursor_x + width) > (build_plate_width - edge_margin):
            cursor_x = edge_margin
            cursor_y += row_depth + spacing
            row_depth = 0.0

        # Spill to a new plate when this part no longer fits vertically.
        if (cursor_y + depth) > (build_plate_depth - edge_margin):
            plates.append([])
            cursor_x = edge_margin
            cursor_y = edge_margin
            row_depth = 0.0

        offset_x = cursor_x - min_x
        offset_y = cursor_y - min_y
        plates[-1].append((path.stem, triangles, offset_x, offset_y))

        cursor_x += width + spacing
        row_depth = max(row_depth, depth)

    return plates


def export_3mf_files(
    inputs: list[Path],
    output: Path,
    spacing: float = 2.0,
    build_plate_width: float = 200.0,
    build_plate_depth: float = 200.0,
    edge_margin: float = 0.0,
) -> list[Path]:
    """Write one or more 3MF packages, one per build plate.

    Parts are laid out top-to-bottom, left-to-right.  When a plate fills up,
    a new file is created (``output``, ``output.with_stem(stem-2)``, …).
    The first plate contains the topmost arcs of the mobile.

    Returns the list of written 3MF paths.
    """
    plates = _layout_parts_to_plates(
        inputs, spacing, build_plate_width, build_plate_depth, edge_margin,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for plate_idx, part_meshes in enumerate(plates):
        if not part_meshes:
            continue
        if plate_idx == 0:
            plate_path = output
        else:
            stem = output.stem
            plate_path = output.with_stem(f"{stem}-{plate_idx + 1}")

        with zipfile.ZipFile(plate_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", _content_types_xml())
            zf.writestr("_rels/.rels", _rels_xml())
            zf.writestr("3D/3dmodel.model", _build_model_xml(part_meshes))
        written.append(plate_path)

    return written
