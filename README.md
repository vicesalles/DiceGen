# Blender Dice Gen

A Blender add-on that generates polyhedral dice

![](https://github.com/user-attachments/assets/52db5bd6-0d78-4d2a-b9cd-36b29cd95511)

## Installation and usage

Download the [main python script](https://github.com/shawn-makes-stuff/DiceGen5.0/blob/main/DiceGen5.py), then go to `Edit > Preferences... > Add-ons > Install...` and select the file.

Afterwards you will be able to generate dice in `Add > Mesh > Dice` or `Sidebar > DiceGen5 > Add Dice to Scene`.

Each newly added die is placed in its own collection named after the dice type, with the body, numbers, and fin supports grouped together.

The add-on will create a blank dice mesh and, if enabled, a separate numbers object. The blank dice object will have a boolean modifier that has the "Realtime" flag turned off for performance reasons. Turn that on to see the result in the viewport.

## Supported dice

- D4 Tetrahedron
- D4 Crystal
- D4 Shard
- D6 Cube
- D8 Octahedron
- D10 Pentagonal Trepazohedron
- D100 Pentagonal Trepazohedron
- D12 Dodecahedron
- D20 Icosahedron
- Custom Crystal, any number of faces
- Custom Shard, any number of faces
- Custom Bipyramid, any even number of faces (not impossible geometry)
- Custom Trapezohedron, any number of even faces (not impossible geometry)

### New features

- Add a custom image to a face using an SVG
- Set dice type to sharp, chamfer, or bevel (these are done with a bevel modifier)
- Set dice type bumper (creates a "cage" around the dice corners, modifies dice mesh)
- Added new Dice Gen section to Object properties to allow quick configuration changes of individual dice
- Added new Dice Gen sidebar menu option to allow quickly creating multiple dice with the same configuration
- Built-in fin supports for resin printing
- Automatic per-die collections to keep multi-die scenes organized
- Dedicated critical face material: assign a distinct material to the highest-value face label
- Dot orientation indicator: place a small dot below `6` and `9` for visual clarity
- Unity-ready FBX export: exports body, numbers, and critical face as separate objects with independent materials for easy customization
- Automatic system font selection on first use (falls back to Blender built-in if none found)

## Unity-ready export

Select any generated dice body and click **Export Selected as FBX**. The button is available in two places:

1. **Object Properties panel** (orange cube tab): select a die body, scroll to *Dice Gen*, and click *Export Selected as FBX* right next to *Regenerate Dice*.
2. **N-panel sidebar**: press **N** in the 3D viewport, open the *DiceGen5* tab, and find *Unity Export* at the bottom.

The exporter produces **multiple objects per die** so you can customize materials individually in Unity:

| Object | Example name | Material | Purpose |
|--------|-------------|----------|---------|
| Body | `GG_D6_Body` | `MAT_Die_Body` | Solid die body (boolean modifiers removed) |
| Numbers | `GG_D6_Numbers` | `MAT_Die_Label` | Regular engraved numbers |
| Critical | `GG_D6_Numbers_Critical` | `MAT_Die_Label_Critical` | Highest-value face label (if enabled) |

All objects in the set are exported into a single FBX file. In Unity you can swap each material independently — change body color, number color, and critical face color without re-exporting.

Other export details:

- Applies transforms so scale is `1,1,1` and rotation is identity
- Writes to `//exports/unity/d6/grangol_d6_default.fbx` next to your `.blend` file
- You can select multiple dice and export them all at once; each die gets its own subfolder

## Settings reference

Detailed setting documentation is in [SETTINGS.md](SETTINGS.md).

- Global settings
- Number and indicator settings
- Custom image settings
- Resin fin support settings
- Geometry-specific settings
- Unity-ready export conventions
- Workflow notes


## Tips

- The unit scale in Blender is weird and with default settings the scale of the generated STL will be off by a factor of 1000 compared to the displayed scale in Blender. To have Blender display scales that matches the resulting STL set `Scene Properties > Units > Unit Scale` to 0.001. It also helps to set the length unit to millimeters.
- If the dice disappears when enabling the boolean modifier, try ticking the `Self` option under the solver options for the Exact solver. Or try switching to the Fast solver.
