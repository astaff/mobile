"""3MF exporter with one object per STL part."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

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
    ET.register_namespace("", CORE_NS)
    model = ET.Element(f"{{{CORE_NS}}}model", {"unit": "millimeter", "xml:lang": "en-US"})
    resources = ET.SubElement(model, f"{{{CORE_NS}}}resources")
    build = ET.SubElement(model, f"{{{CORE_NS}}}build")

    for object_id, (name, triangles, offset_x, offset_y) in enumerate(part_meshes, start=1):
        obj = ET.SubElement(
            resources,
            f"{{{CORE_NS}}}object",
            {"id": str(object_id), "type": "model", "name": name},
        )
        mesh = ET.SubElement(obj, f"{{{CORE_NS}}}mesh")
        vertices_el = ET.SubElement(mesh, f"{{{CORE_NS}}}vertices")
        triangles_el = ET.SubElement(mesh, f"{{{CORE_NS}}}triangles")

        vertex_indices: dict[tuple[float, float, float], int] = {}
        tri_indices: list[tuple[int, int, int]] = []

        for v0, v1, v2 in triangles:
            tri = []
            for vx, vy, vz in (v0, v1, v2):
                key = (vx + offset_x, vy + offset_y, vz)
                idx = vertex_indices.get(key)
                if idx is None:
                    idx = len(vertex_indices)
                    vertex_indices[key] = idx
                    ET.SubElement(
                        vertices_el,
                        f"{{{CORE_NS}}}vertex",
                        {"x": _fmt(key[0]), "y": _fmt(key[1]), "z": _fmt(key[2])},
                    )
                tri.append(idx)
            tri_indices.append((tri[0], tri[1], tri[2]))

        for a, b, c in tri_indices:
            ET.SubElement(
                triangles_el,
                f"{{{CORE_NS}}}triangle",
                {"v1": str(a), "v2": str(b), "v3": str(c)},
            )

        ET.SubElement(build, f"{{{CORE_NS}}}item", {"objectid": str(object_id)})

    return ET.tostring(model, encoding="utf-8", xml_declaration=True)


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


def export_3mf_files(
    inputs: list[Path],
    output: Path,
    spacing: float = 2.0,
    build_plate_width: float = 200.0,
    build_plate_depth: float = 200.0,
    edge_margin: float = 1.0,
) -> Path:
    """Write a 3MF package containing one named object per STL input file.

    Parts are arranged in a 2D grid that wraps rows to fit the configured
    build plate footprint.
    """
    part_meshes: list[tuple[str, list[Triangle], float, float]] = []
    usable_width = build_plate_width - 2.0 * edge_margin
    usable_depth = build_plate_depth - 2.0 * edge_margin
    if usable_width <= 0 or usable_depth <= 0:
        raise ValueError(
            f"Build plate {build_plate_width:.1f}x{build_plate_depth:.1f} mm is too "
            f"small for edge margin {edge_margin:.1f} mm"
        )

    cursor_x = edge_margin
    cursor_y = edge_margin
    row_depth = 0.0

    for path in inputs:
        triangles, _bounds = read_binary_stl(path)
        min_x, max_x, min_y, max_y = _mesh_bounds_xy(triangles)
        width = max_x - min_x
        depth = max_y - min_y

        if width > usable_width or depth > usable_depth:
            raise ValueError(
                f"Part '{path.stem}' ({width:.2f}x{depth:.2f} mm) exceeds "
                f"usable plate area {usable_width:.1f}x{usable_depth:.1f} mm "
                f"(plate {build_plate_width:.1f}x{build_plate_depth:.1f}, "
                f"edge margin {edge_margin:.1f})"
            )

        # Wrap to next row when this part no longer fits current row.
        if cursor_x > edge_margin and (cursor_x + width) > (build_plate_width - edge_margin):
            cursor_x = edge_margin
            cursor_y += row_depth + spacing
            row_depth = 0.0

        if (cursor_y + depth) > (build_plate_depth - edge_margin):
            raise ValueError(
                f"Cannot fit all parts on build plate "
                f"{build_plate_width:.1f}x{build_plate_depth:.1f} mm "
                f"with spacing {spacing:.1f} and edge margin {edge_margin:.1f} mm"
            )

        offset_x = cursor_x - min_x
        offset_y = cursor_y - min_y
        part_meshes.append((path.stem, triangles, offset_x, offset_y))

        cursor_x += width + spacing
        row_depth = max(row_depth, depth)

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types_xml())
        zf.writestr("_rels/.rels", _rels_xml())
        zf.writestr("3D/3dmodel.model", _build_model_xml(part_meshes))

    return output
