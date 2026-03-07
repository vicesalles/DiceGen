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
- `Font`: font file used for text numbers.

## Orientation indicator settings

These appear only on supported dice and only when numbers are enabled.

- `Orientation Indicator`: marker used to distinguish `6` and `9`.
  `None`: no marker.
  `Period`: adds a dot.
  `Bar`: adds a short underline bar.
- `Period Scale`: scales the period marker.
- `Period Space`: distance between the number and period.
- `Bar Height`: height scale for the underline bar.
- `Bar Width`: width scale for the underline bar.
- `Bar Space`: distance between the number and the bar.
- `Center Align Bar`: includes the bar in the vertical alignment of the number layout.

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

## Workflow notes

- Each new die is created in its own collection named after the dice type.
- The collection contains the body, numbers, and fin supports for that die.
- Regenerating a die keeps rebuilt parts inside the same collection.
