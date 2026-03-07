# Blender Dice Gen

A Blender add-on that generates polyhedral dice, with built-in resin fin supports and a separate resin auto-support addon for merged print meshes.

![](https://github.com/user-attachments/assets/52db5bd6-0d78-4d2a-b9cd-36b29cd95511)

## Installation and usage

Download the [main python script](https://github.com/shawn-makes-stuff/DiceGen5.0/blob/main/DiceGen5.py), then go to `Edit > Preferences... > Add-ons > Install...` and select the file.

If you also want automatic resin supports after you merge the finished die, install [DiceGenResinAutoSupports.py](https://github.com/shawn-makes-stuff/DiceGen5.0/blob/main/DiceGenResinAutoSupports.py) as a second addon.

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
- Built-in resin fin supports for point-down printing
- Separate resin auto-support addon for merged meshes and island cleanup
- Automatic per-die collections to keep multi-die scenes organized

## Resin fin supports

`DiceGen5.py` includes a built-in fin support workflow intended for resin printing.

- Dice are print-oriented with a point facing down.
- Fin supports are generated as real meshes as part of the dice builder.
- Fins are built along the point-down support edges and intersect the die body slightly so chamfer and bevel finishes still connect cleanly.
- The fin edge height stops at the real edge length of the current die.

### Fin support settings

- `Generate Fin Supports`: turn fin generation on or off
- `Fin Edge Height`: how far up the supporting edges the fin climbs
- `Top Edge Thickness`: thickness where the fin meets the die
- `Bottom Edge Thickness`: thickness where the fin meets the raft
- `Fin Drop`: distance from die to raft
- `Raft Margin`: expands the raft footprint
- `Raft Thickness`: sets raft thickness
- `Raft Taper`: narrows the raft toward the build plate for easier removal

## Resin auto supports

`DiceGenResinAutoSupports.py` is a separate addon for the final merged mesh.

- Works on a selected merged mesh
- Samples downward-facing surfaces
- Detects unsupported islands and long unsupported spans
- Generates mesh-based supports with configurable contacts, shafts, bases, and braces

## Tips

- The unit scale in Blender is weird and with default settings the scale of the generated STL will be off by a factor of 1000 compared to the displayed scale in Blender. To have Blender display scales that matches the resulting STL set `Scene Properties > Units > Unit Scale` to 0.001. It also helps to set the length unit to millimeters.
- If the dice disappears when enabling the boolean modifier, try ticking the `Self` option under the solver options for the Exact solver. Or try switching to the Fast solver.
