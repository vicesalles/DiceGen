# DiceGen5 Settings Reference

This file documents the user-facing settings exposed by `DiceGen5.py`.

The addon shows different geometry controls depending on the selected dice type, but the settings are grouped into a few consistent categories.

## Global settings

- `Dice Size`: overall die size in millimeters.
- `Dice Finish`: edge treatment for the die body.
  `Sharp`: leaves edges untouched.
  `Chamfer`: adds a light bevel.
  `Fillet`: adds a rounder bevel with more segments.
  `Bumpers`: creates raised edge borders around inset faces.
- `Bumper Size`: scales the bumper effect when `Dice Finish` is set to `Bumpers`.

## Number settings

- `Generate Numbers`: turns number generation on or off.
- `Number Scale`: scales the engraved numbers.
- `Number Depth`: engraving depth in millimeters.
- `Font`: font file used for text numbers. Defaults to a system font (Arial on Windows, DejaVu on Linux, Helvetica on macOS). Falls back to Blender's built-in font if no system font is found.

## Orientation indicator settings

These appear only on supported dice and only when numbers are enabled.

- `Orientation Indicator`: marker used to distinguish `6` and `9`.
  `None`: no marker.
  `Period`: adds a period after the number (e.g., `6.`).
  `Bar`: adds a short underline bar.
  `Dot`: adds a small dot below the number.
- `Period Scale`: scales the period marker.
- `Period Space`: distance between the number and period.
- `Bar Height`: height scale for the underline bar.
- `Bar Width`: width scale for the underline bar.
- `Bar Space`: distance between the number and the bar.
- `Center Align Bar`: includes the bar in the vertical alignment of the number layout.
- `Dot Scale`: scales the dot marker below `6` and `9`.
- `Dot Space`: distance between the number and the dot.

## Critical face material settings

- `Use Critical Face Material`: when enabled, the highest-value face label gets its own material instead of sharing the default number material.
- `Critical Face Material`: the color used for the highest-value face label. This is independent from the die body material and the regular number material.

This works together with custom SVG images: if the highest face is replaced by a custom image, that image still receives the critical face material.

## Custom image settings

- `Custom Image (SVG)`: SVG file to engrave instead of a face number.
- `Custom Image Face`: 1-based face index that uses the image. `0` disables image replacement.
- `Custom Image Scale`: scales the imported SVG relative to the number size.

## Resin fin support settings

`DiceGen5.py` includes a built-in fin support workflow intended for resin printing.

- Dice are print-oriented with a point facing down.
- Fin supports are generated as real meshes as part of the dice builder.
- Fins are built along the point-down support edges.
- Fins intersect the die body slightly so chamfer and bevel finishes still connect cleanly.
- The fin edge height stops at the real edge length of the current die.

- `Generate Fin Supports`: turns fin generation on or off.
- `Fin Edge Height`: how far up the supporting edges the fins climb.
- `Top Edge Thickness`: fin thickness where it meets the die.
- `Bottom Edge Thickness`: fin thickness where it meets the raft.
- `Fin Drop`: vertical distance from the die to the raft.
- `Raft Margin`: expands the raft footprint outward.
- `Raft Thickness`: thickness of the raft body.
- `Raft Taper`: narrows the raft toward the build plate for easier removal.

## Geometry-specific settings

These appear only on dice types that use them.

- `Number Center Offset`: D4 only. Moves numbers away from face center toward a vertex.
- `Number Horizontal Offset`: shifts numbers sideways in the local face direction.
- `Number Vertical Offset`: shifts numbers up or down in the local face direction.
- `Number of Faces`: used by custom dice types to define total face count.
- `Base Height`: used by crystal-style dice to control the center body height.
- `Top Point Height`: controls the top apex height.
- `Bottom Point Height`: controls the bottom apex height.
- `Dice Height`: used by D10, D100, and custom trapezohedrons to control body height or aspect ratio.

## Unity-ready export

The addon includes a built-in exporter that produces clean static meshes for game engines.

- Select one or more dice **body** objects in the viewport.
- Click **Export Selected as FBX**. This button is available in two places:
  1. The **Object Properties** panel (orange cube tab), inside the *Dice Gen* section.
  2. The **N-panel sidebar** (*DiceGen5* tab) under *Unity Export*.
- Output is written to `//exports/unity/` relative to the current `.blend` file.

### Export structure

Each die is exported as a **set of separate objects** inside one FBX file. This lets you customize materials independently in Unity:

| Piece | Object name | Material name | Description |
|-------|------------|---------------|-------------|
| Body | `GG_D6_Body` | `MAT_Die_Body` | Solid die body. Boolean modifiers are removed so the mesh stays intact. |
| Numbers | `GG_D6_Numbers` | `MAT_Die_Label` | Regular number meshes. |
| Critical | `GG_D6_Numbers_Critical` | `MAT_Die_Label_Critical` | Highest-value face label (only when *Use Critical Face Material* is enabled). |

### Conventions

- **Folder structure:** `exports/unity/d6/`, `exports/unity/d20/`, etc.
- **File names:** `grangol_d6_default.fbx`
- Transforms are applied so every object has identity scale/rotation and origin at world zero.
- Bevel and bumper modifiers are baked into the body geometry.
- A glTF Binary (`.glb`) fallback path is also available.

### Export options

After triggering the export, the operator redo panel (press **F9**) or the sidebar operator settings let you tweak:

- **Format:** `FBX` (default) or `glTF Binary`.
- **Pivot:** `Geometric Center` (default) or `Face Center`.
  - *Geometric Center:* the object's origin is at the die's center. Best for general use.
  - *Face Center:* the object's origin is moved to the center of the specified face. All exported pieces (body, numbers, critical) are shifted together so they stay aligned. This is ideal for deterministic rolling scripts in Unity because the pivot sits on the touching-the-floor face instead of the center.
- **Face Index:** (only when Pivot is *Face Center*) the 0-based mesh face index to use as the origin. Enable Blender's *Viewport Overlays > Developer > Indices* to see face numbers in the 3D view.

### Unity workflow

1. Import the FBX into Unity.
2. In the Material Import Settings, choose *Use Embedded Materials*.
3. Create material variants for `MAT_Die_Body`, `MAT_Die_Label`, and `MAT_Die_Label_Critical`.
4. Assign different colors, textures, or shaders to each slot independently.

### Companion face-data text file

Every export also produces a sidecar text file (e.g., `grangol_d6_default_faces.txt`) in the same folder. It lists every mesh face with:

- `index` — the 0-based face index (matches Blender's Face Index overlay)
- `value` — the number engraved on that face (e.g., `1`, `2`, `6`)
- `center_x/y/z` — the face center in local space (after pivot shift if applicable)
- `normal_x/y/z` — the face normal vector

Example:

```
# DiceGen Face Data for dice_body
# Type: Cube
# Total faces: 6
# Pivot face index: None (geometric center)

# Face data format: index | value | center_x | center_y | center_z | normal_x | normal_y | normal_z

0 | 1 | 0.000000 | -0.500000 | 0.000000 | 0.000000 | -1.000000 | 0.000000
1 | 2 | 0.500000 | 0.000000 | 0.000000 | 1.000000 | 0.000000 | 0.000000
...
```

You can parse this file at runtime or in the Unity Editor to build a lookup table from face index → die value, or to compute the resting transform from face center + normal.

### Deterministic rolling tip

If you are writing a script that snaps the die to a specific face:

1. Export with **Pivot** set to *Face Center* and pick the face that will be the "resting" face (e.g., face 5 for the "6" side on a standard D6).
2. In Unity, position the die so its origin sits on the floor collider.
3. Rotate around the origin to animate rolls; when the animation finishes, the origin is already on the correct contact point.

## Workflow notes

- Each new die is created in its own collection named after the dice type.
- The collection contains the body, numbers, and fin supports for that die.
- Regenerating a die keeps rebuilt parts inside the same collection.
