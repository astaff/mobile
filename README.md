# mbl

Generate parametric hanging mobiles with a small Python DSL and export printable `.3mf` / `.stl`.

## CLI

```bash
git clone <repo-url>
cd <repo-dir>
uv sync
uv run mbl "HELLO" --output hello.3mf
uv run mbl "XYZ" --leaf-shape burst --output xyz.3mf
uv run mbl "XYZ" --leaf-shape burst --shape-scale 1.3 --text-scale 0.9 --output xyz-scaled.3mf
```

Key flags:
- `--output`: output file (`.3mf` default, `.stl` supported)
- `--font`: stencil font file (`.ttf` / `.otf`)
- `--font-size`: letter size in mm
- `--leaf-shape`: `circle`, `burst`, `star`
- `--shape-scale`: extra multiplier for leaf body size
- `--text-scale`: multiplier for glyph cutout size (independent from leaf body scale)
- `--hook-style`: `line` or `hook`
- `--width`, `--height`: top arc dimensions

## Python SDK DSL

```bash
uv run python - <<'PY'
from mbl import Mobile

Mobile.from_word("HELLO", leaf_shape="circle").to_file("hello.3mf")
Mobile.from_word("XYZ", leaf_shape="burst").to_file("xyz.3mf")
Mobile.from_word("XYZ", leaf_shape="burst", shape_scale=1.3, text_scale=0.9).to_file("xyz-scaled.3mf")
PY
```

## DSL shape

- Single bind: `Arc(w, h) @ (left, right)`
- Right-hole shorthand: `Arc(w, h) @ (left,)`
- Row map bind: `Arc(w, h) @ [(a, b), (c,)]`
