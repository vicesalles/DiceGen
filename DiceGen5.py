import math
import re
import bpy
import os
import bmesh
from contextlib import contextmanager
from typing import List, Tuple, Optional, Dict, Any
from math import sqrt, acos, pow
from mathutils import Vector, Matrix, Euler
from bpy.types import Menu
from bpy.props import FloatProperty, BoolProperty, StringProperty, EnumProperty, PointerProperty, IntProperty, FloatVectorProperty
from bpy_extras.object_utils import object_data_add

bl_info = {
    'name': 'DiceGen 5.x GG edition',
    'author': 'Long Tran, shawn-makes-stuff, vicesalles',
    'version': (1, 3, 0),
    'blender': (5, 0, 0),
    'location': 'View3D > Add > Mesh',
    'description': 'Generate polyhedral dice models.',
    'category': 'Add Mesh',
    'doc_url': 'https://github.com/Longi94/blender-dice-gen/wiki',
    'tracker_url': 'https://github.com/Longi94/blender-dice-gen/issues'
}

def _discover_system_font() -> str:
    """
    Return the path to a usable system TTF/OTF font, or empty string if none found.
    Falls back gracefully so Blender's built-in font is used when no system font exists.
    """
    candidates = []
    if os.name == 'nt':
        font_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
        candidates = [
            os.path.join(font_dir, 'arial.ttf'),
            os.path.join(font_dir, 'segoeui.ttf'),
            os.path.join(font_dir, 'calibri.ttf'),
            os.path.join(font_dir, 'verdana.ttf'),
            os.path.join(font_dir, 'tahoma.ttf'),
        ]
    elif os.uname().sysname == 'Darwin':
        candidates = [
            '/System/Library/Fonts/Helvetica.ttc',
            '/Library/Fonts/Arial.ttf',
            '/System/Library/Fonts/Supplemental/Arial.ttf',
        ]
    else:
        candidates = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
        ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ''


DEFAULT_SYSTEM_FONT = _discover_system_font()

NUMBER_IND_NONE = 'none'
NUMBER_IND_BAR = 'bar'
NUMBER_IND_PERIOD = 'period'
NUMBER_IND_DOT = 'dot'
PANEL_POCKET_BOOLEAN_NAME = "panel_pocket_boolean"
PANEL_NUMBER_BOOLEAN_NAME = "panel_number_boolean"
PANEL_TOP_FACE_BOOLEAN_NAME = "panel_top_face_boolean"
PANEL_OBJECT_KEY = "dice_panels_name"
PANEL_CUTTER_KEY = "dice_panel_cutter_name"
PANEL_NUMBER_CUTTER_KEY = "dice_panel_numbers_name"
PANEL_TOP_FACE_CUTTER_KEY = "dice_top_face_cutter_name"
FIN_SUPPORT_OBJECT_KEY = "dice_fin_support_name"
FIN_SUPPORT_BODY_INTERSECTION = 1.0

HALF_PI = math.pi / 2
THIRD_PI = math.pi / 3
QUARTER_PI = math.pi / 4
SIXTH_PI = math.pi / 6

# Empirically determined rotation angles for icosahedron number placement
# These values were derived using Blender's alignment trick for D20 dice
#
# TODO: Calculate these values analytically instead of using empirical measurements
# The analytical calculation should involve:
# 1. Computing the dihedral angle between icosahedron faces
# 2. Calculating the rotation needed to align numbers perpendicular to each face
# 3. Accounting for the golden ratio relationships inherent in icosahedron geometry
#
# For reference, the icosahedron has a dihedral angle of ~138.19° (acos(-sqrt(5)/3))
# and its geometry involves the golden ratio φ = (1 + sqrt(5)) / 2
ICOSAHEDRON_ROTATION_ANGLES = {
    'angle_1': 0.918438,  # ≈ 52.6°  - pitch angle for certain face orientations
    'angle_2': 2.82743,   # ≈ 162°   - yaw angle for face alignment
    'angle_3': 4.15881,   # ≈ 238.3° - roll angle for number orientation
    'angle_4': 0.314159,  # ≈ 18°    - small pitch adjustment (~π/10)
    'angle_5': 2.12437,   # ≈ 121.7° - complementary angle for opposite faces
    'angle_6': 4.06003,   # ≈ 232.7° - large pitch for inverted faces
    'angle_7': 2.22315,   # ≈ 127.4° - mid-range rotation angle
    'angle_8': 1.01722,   # ≈ 58.3°  - standard face orientation offset
}


def leg_b(leg_a: float, h: float) -> float:
    """
    Calculate the second leg of a right triangle given one leg and its height.

    Args:
        leg_a: Length of one leg of the right triangle
        h: Height of the triangle

    Returns:
        Length of the other leg
    """
    return sqrt(pow(h, 2) + (pow(h, 4) / (pow(leg_a, 2) - pow(h, 2))))


# https://dmccooey.com/polyhedra
CONSTANTS = {
    'tetrahedron': {
        'dihedral_angle': acos(1 / 3),
        'height': sqrt(2 / 3),
        'c0': sqrt(2) / 4
    },
    'octahedron': {
        'dihedral_angle': acos(sqrt(5) / -5),
        'circumscribed_r': (sqrt(3) + sqrt(15)) / 4,
        'inscribed_r': sqrt(10 * (25 + 11 * sqrt(5))) / 20,
        'c0': (1 + sqrt(5)) / 4,
        'c1': (3 + sqrt(5)) / 4,
        'c2': 0.5
    },
    'icosahedron': {
        'dihedral_angle': acos(sqrt(5) / -3),
        'circumscribed_r': sqrt(2 * (5 + sqrt(5))) / 4,
        'inscribed_r': (3 * sqrt(3) + sqrt(15)) / 12,
        'c0': (1 + sqrt(5)) / 4,
        'c1': 0.5
    },
    'pentagonal_trap': {
        'inscribed_r': sqrt(5 * (5 + 2 * sqrt(5))) / 10,
        'base_height': 1.1180340051651,
        'base_width': leg_b(1.1180340051651, 0.5),
        'c0': (sqrt(5) - 1) / 4,
        'c1': (1 + sqrt(5)) / 4,
        'c2': (3 + sqrt(5)) / 4,
        'c3': 0.5
    }
}

# calculate rotation of trapezohedron to have it stand upright
# from dice-gen Math.acos((C0 - C2) / Math.sqrt(Math.pow(C0 - C2, 2) + 4 * Math.pow(C1, 2)))
CONSTANTS['pentagonal_trap']['angle'] = Euler((0, 0, acos(
    (CONSTANTS['pentagonal_trap']['c0'] - CONSTANTS['pentagonal_trap']['c2']) / sqrt(
        pow(CONSTANTS['pentagonal_trap']['c0'] - CONSTANTS['pentagonal_trap']['c2'], 2) + 4 * pow(
            CONSTANTS['pentagonal_trap']['c1'], 2)))), 'XYZ')

CONSTANTS['pentagonal_trap']['angle'].rotate(Euler((HALF_PI, 0, 0), 'XYZ'))


class Mesh:
    """
    Base class for polyhedral dice mesh generation.

    This class provides the foundation for creating different types of dice geometry
    and handles number placement on dice faces.

    Attributes:
        vertices: List of vertex coordinates for the mesh
        faces: List of face definitions (vertex indices)
        name: Name of the mesh
        dice_mesh: The created Blender mesh object
        base_font_scale: Base scaling factor for numbers on this die type
    """

    def __init__(self, name: str):
        """
        Initialize the mesh generator.

        Args:
            name: Name for the mesh object
        """
        self.vertices = None
        self.faces = None
        self.name = name
        self.dice_mesh = None
        self.base_font_scale = 1
        self.print_rotation = Matrix.Identity(3)
        self.print_lift = 0.0
        self.output_vertices = None
        self._print_layout_applied = False

    def create(self, context) -> bpy.types.Object:
        """
        Create the dice mesh in Blender.

        Args:
            context: Blender context

        Returns:
            The created mesh object
        """
        self.dice_mesh = create_mesh(context, self.get_output_vertices(), self.faces, self.name)
        # reset transforms
        self.dice_mesh.matrix_world = Matrix()
        return self.dice_mesh

    def get_numbers(self) -> List[str]:
        """
        Get the list of numbers to place on the dice faces.

        Returns:
            List of number strings
        """
        return []

    def get_number_locations(self) -> List[Tuple[float, float, float]]:
        """
        Get the 3D positions for each number on the dice.

        Returns:
            List of (x, y, z) coordinate tuples
        """
        return []

    def get_number_rotations(self) -> List[Tuple[float, float, float]]:
        """
        Get the rotation angles for each number on the dice.

        Returns:
            List of (x, y, z) Euler angle tuples in radians
        """
        return []

    def apply_print_layout(self, lift_height: float = 0.0) -> None:
        if self._print_layout_applied or not self.vertices:
            return

        vertex_vectors = [Vector(vertex) for vertex in self.vertices]
        bottom_index = min(
            range(len(vertex_vectors)),
            key=lambda index: (
                vertex_vectors[index].z,
                vertex_vectors[index].x * vertex_vectors[index].x + vertex_vectors[index].y * vertex_vectors[index].y,
                vertex_vectors[index].x,
                vertex_vectors[index].y,
            ),
        )
        bottom_vector = vertex_vectors[bottom_index]
        target_vector = Vector((0.0, 0.0, -1.0))

        if bottom_vector.length > 1e-6:
            rotation = bottom_vector.normalized().rotation_difference(target_vector).to_matrix()
        else:
            rotation = Matrix.Identity(3)

        rotated_vertices = [rotation @ vertex for vertex in vertex_vectors]
        min_z = min(vertex.z for vertex in rotated_vertices)
        z_offset = lift_height - min_z
        translated_vertices = [vertex + Vector((0.0, 0.0, z_offset)) for vertex in rotated_vertices]

        self.output_vertices = [(vertex.x, vertex.y, vertex.z) for vertex in translated_vertices]
        self.print_rotation = rotation
        self.print_lift = z_offset
        self._print_layout_applied = True

    def get_output_vertices(self) -> List[Tuple[float, float, float]]:
        return self.output_vertices if self.output_vertices is not None else self.vertices

    def transform_number_locations(self, locations: List[Tuple[float, float, float]]) -> List[Tuple[float, float, float]]:
        transformed: List[Tuple[float, float, float]] = []
        for location in locations:
            point = self.print_rotation @ Vector(location)
            point.z += self.print_lift
            transformed.append((point.x, point.y, point.z))
        return transformed

    def transform_number_rotations(self, rotations: List[Tuple[float, float, float]]) -> List[Tuple[float, float, float]]:
        transformed: List[Tuple[float, float, float]] = []
        for rotation in rotations:
            rotation_matrix = self.print_rotation @ Euler(rotation, 'XYZ').to_matrix()
            transformed_euler = rotation_matrix.to_euler('XYZ')
            transformed.append((transformed_euler.x, transformed_euler.y, transformed_euler.z))
        return transformed

    def create_numbers(self, context, size, number_scale, number_depth, font_path,
                       number_indicator_type=NUMBER_IND_NONE, period_indicator_scale=1, period_indicator_space=1,
                       bar_indicator_height=1, bar_indicator_width=1, bar_indicator_space=1,
                       center_bar=True, custom_image_face=0, custom_image_path='', custom_image_scale=1,
                       use_critical_face_material=False, critical_face_material=(1.0, 0.0, 0.0, 1.0),
                       dot_indicator_scale=1, dot_indicator_space=1):
        numbers_objects = create_numbers_object_for_mesh(
            context, self, size, number_scale, number_depth, font_path,
            number_indicator_type, period_indicator_scale, period_indicator_space,
            bar_indicator_height, bar_indicator_width, bar_indicator_space, center_bar,
            custom_image_face, custom_image_path, custom_image_scale,
            use_critical_face_material=use_critical_face_material,
            critical_face_material=critical_face_material,
            dot_indicator_scale=dot_indicator_scale,
            dot_indicator_space=dot_indicator_space,
        )
        for idx, num_obj in enumerate(numbers_objects):
            mod_name = 'boolean' if idx == 0 else 'boolean_critical'
            apply_boolean_modifier(self.dice_mesh, num_obj, modifier_name=mod_name)
        return numbers_objects[0] if numbers_objects else None


class Tetrahedron(Mesh):
    """
    Tetrahedral dice (D4) mesh generator.

    Creates a regular tetrahedron with numbers placed on each face.
    The tetrahedron is oriented to stand on one face.
    """

    def __init__(self, name: str, size: float, number_center_offset: float, number_h_offset: float = 0.0, number_v_offset: float = 0.0):
        """
        Initialize a tetrahedron dice mesh.

        Args:
            name: Name for the mesh object
            size: Face-to-point size of the tetrahedron
            number_center_offset: How far numbers are offset from face centers (0=center, 1=vertex)
            number_h_offset: Horizontal offset for numbers on faces
            number_v_offset: Vertical offset for numbers on faces
        """
        super().__init__(name)
        self.size = size
        self.number_center_offset = number_center_offset
        self.number_h_offset = number_h_offset
        self.number_v_offset = number_v_offset

        c0 = CONSTANTS['tetrahedron']['c0'] / CONSTANTS['tetrahedron']['height'] * size

        self.vertices = [(c0, -c0, c0), (c0, c0, -c0), (-c0, c0, c0), (-c0, -c0, -c0)]
        self.faces = [[0, 1, 2], [1, 0, 3], [2, 3, 0], [3, 2, 1]]

        self.base_font_scale = 0.3

    def get_numbers(self):
        return [str(math.floor(i / 3) + 1) for i in range(12)]

    def get_number_locations(self):
        # face centers
        centers = [Vector((
            ((self.vertices[f[0]][0] + self.vertices[f[1]][0] + self.vertices[f[2]][0]) / 3),
            ((self.vertices[f[0]][1] + self.vertices[f[1]][1] + self.vertices[f[2]][1]) / 3),
            ((self.vertices[f[0]][2] + self.vertices[f[1]][2] + self.vertices[f[2]][2]) / 3)
        )) for f in self.faces]
        vertices = [Vector(v) for v in self.vertices]

        # Calculate base positions using center offset
        location_vectors = [
            centers[0].lerp(vertices[2], self.number_center_offset),
            centers[2].lerp(vertices[2], self.number_center_offset),
            centers[3].lerp(vertices[2], self.number_center_offset),
            centers[0].lerp(vertices[1], self.number_center_offset),
            centers[1].lerp(vertices[1], self.number_center_offset),
            centers[3].lerp(vertices[1], self.number_center_offset),
            centers[0].lerp(vertices[0], self.number_center_offset),
            centers[1].lerp(vertices[0], self.number_center_offset),
            centers[2].lerp(vertices[0], self.number_center_offset),
            centers[1].lerp(vertices[3], self.number_center_offset),
            centers[2].lerp(vertices[3], self.number_center_offset),
            centers[3].lerp(vertices[3], self.number_center_offset)
        ]

        # Apply horizontal and vertical offsets
        # For each face, we need to determine the local coordinate system
        if self.number_h_offset != 0.0 or self.number_v_offset != 0.0:
            c0 = CONSTANTS['tetrahedron']['c0'] / CONSTANTS['tetrahedron']['height'] * self.size
            scale_factor = c0 * 0.5  # Scale for offset application

            # Define face normal and up vectors for each of the 4 faces
            # Face 0: [0,1,2], Face 1: [1,0,3], Face 2: [2,3,0], Face 3: [3,2,1]
            face_info = [
                (0, vertices[2]),  # Numbers 0,1,2 - face 0
                (2, vertices[2]),  # Numbers 1,2 - face 2
                (3, vertices[2]),  # Numbers 2 - face 3
                (0, vertices[1]),  # Numbers 3,4,5 - face 0
                (1, vertices[1]),  # Numbers 4,5 - face 1
                (3, vertices[1]),  # Numbers 5 - face 3
                (0, vertices[0]),  # Numbers 6,7,8 - face 0
                (1, vertices[0]),  # Numbers 7,8 - face 1
                (2, vertices[0]),  # Numbers 8 - face 2
                (1, vertices[3]),  # Numbers 9,10,11 - face 1
                (2, vertices[3]),  # Numbers 10,11 - face 2
                (3, vertices[3]),  # Numbers 11 - face 3
            ]

            for i, (face_idx, target_vert) in enumerate(face_info):
                # Calculate face normal
                face = self.faces[face_idx]
                v0 = vertices[face[0]]
                v1 = vertices[face[1]]
                v2 = vertices[face[2]]
                edge1 = v1 - v0
                edge2 = v2 - v0
                normal = edge1.cross(edge2).normalized()

                # Direction from center to target vertex (this is our "up" direction)
                up_dir = (target_vert - centers[face_idx]).normalized()

                # Right direction is perpendicular to both normal and up
                right_dir = up_dir.cross(normal).normalized()

                # Apply offsets
                location_vectors[i] += right_dir * self.number_h_offset * scale_factor
                location_vectors[i] += up_dir * self.number_v_offset * scale_factor

        return [(v.x, v.y, v.z) for v in location_vectors]

    def get_number_rotations(self):
        return [
            (CONSTANTS['tetrahedron']['dihedral_angle'] / 2, math.pi / 4, HALF_PI),
            (CONSTANTS['tetrahedron']['dihedral_angle'] / 2, -math.pi / 4, 0),
            (-(math.pi - CONSTANTS['tetrahedron']['dihedral_angle']) / 2, math.pi, math.pi / 4),
            (-(math.pi - CONSTANTS['tetrahedron']['dihedral_angle']) / 2, 0, -math.pi / 4),
            (CONSTANTS['tetrahedron']['dihedral_angle'] / 2, math.pi * 3 / 4, 0),
            (CONSTANTS['tetrahedron']['dihedral_angle'] / 2, math.pi * 5 / 4, math.pi * 3 / 2),
            (CONSTANTS['tetrahedron']['dihedral_angle'] / 2, -math.pi / 4, -math.pi),
            (-(math.pi - CONSTANTS['tetrahedron']['dihedral_angle']) / 2, math.pi, -math.pi * 3 / 4),
            (CONSTANTS['tetrahedron']['dihedral_angle'] / 2, math.pi / 4, -HALF_PI),
            (CONSTANTS['tetrahedron']['dihedral_angle'] / 2, math.pi * 5 / 4, HALF_PI),
            (-(math.pi - CONSTANTS['tetrahedron']['dihedral_angle']) / 2, 0, math.pi * 3 / 4),
            (CONSTANTS['tetrahedron']['dihedral_angle'] / 2, math.pi * 3 / 4, math.pi)
        ]


class D4Crystal(Mesh):

    def __init__(self, name, size, base_height, top_point_height, bottom_point_height, number_h_offset: float = 0.0, number_v_offset: float = 0.0):
        super().__init__(name)
        self.size = size
        self.number_h_offset = number_h_offset
        self.number_v_offset = number_v_offset

        c0 = 0.5 * size
        c1 = 0.5 * base_height
        c2 = 0.5 * base_height + top_point_height
        c3 = -0.5 * base_height - bottom_point_height

        self.vertices = [(-c0, -c0, c1), (c0, -c0, c1), (c0, c0, c1), (-c0, c0, c1), (-c0, -c0, -c1), (c0, -c0, -c1),
                         (c0, c0, -c1), (-c0, c0, -c1), (0, 0, c2), (0, 0, c3)]
        self.faces = [[0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7], [0, 1, 8], [1, 2, 8], [2, 3, 8],
                      [3, 0, 8], [4, 5, 9], [5, 6, 9], [6, 7, 9], [7, 4, 9]]

        self.base_font_scale = 0.8

    def create(self, context):
        """Create the mesh and recalculate normals"""
        mesh_obj = super().create(context)
        # Recalculate normals to ensure they point outward
        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        bpy.context.view_layer.objects.active = mesh_obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')
        return mesh_obj

    def get_numbers(self):
        return numbers(4)

    def get_number_locations(self):
        c0 = 0.5 * self.size
        h = self.number_h_offset * c0
        v = self.number_v_offset * c0
        # Apply offsets in each face's local coordinate system (all faces are on XY plane, rotated)
        return [(c0, h, v), (h, c0, v), (h, -c0, v), (-c0, h, v)]

    def get_number_rotations(self):
        return [(HALF_PI, 0, HALF_PI), (HALF_PI, 0, HALF_PI * 2), (HALF_PI, 0, 0), (HALF_PI, 0, HALF_PI * 3)]


class CustomCrystal(Mesh):
    """
    Custom crystal dice mesh generator.

    Creates a crystal-shaped die with a square base and pyramidal points on top and bottom.
    Supports any even number of faces (4, 6, 8, 10, 12, etc.) by placing numbers on the
    square sides of the die.
    """

    def __init__(self, name, size, num_faces, base_height, top_point_height, bottom_point_height, number_h_offset: float = 0.0, number_v_offset: float = 0.0):
        super().__init__(name)
        self.num_faces = num_faces
        self.size = size
        self.base_height = base_height
        self.top_point_height = top_point_height
        self.bottom_point_height = bottom_point_height
        self.number_h_offset = number_h_offset
        self.number_v_offset = number_v_offset

        # Calculate the number of sides on the base polygon
        # For a crystal, we have top pyramid + bottom pyramid + sides
        # If we want N total faces and the sides are where numbers go,
        # we need N sides (each side is where a number goes)
        self.num_sides = num_faces

        c0 = 0.5 * size
        c1 = 0.5 * base_height
        c2 = 0.5 * base_height + top_point_height
        c3 = -0.5 * base_height - bottom_point_height

        # Create vertices for a regular polygon base
        angle_step = 2 * math.pi / self.num_sides
        base_top_vertices = []
        base_bottom_vertices = []

        for i in range(self.num_sides):
            angle = i * angle_step
            x = c0 * math.cos(angle)
            y = c0 * math.sin(angle)
            base_top_vertices.append((x, y, c1))
            base_bottom_vertices.append((x, y, -c1))

        # Apex vertices
        top_apex = (0, 0, c2)
        bottom_apex = (0, 0, c3)

        # Combine all vertices
        self.vertices = base_top_vertices + base_bottom_vertices + [top_apex, bottom_apex]

        # Create faces
        faces = []

        # Side faces (quads connecting top and bottom base)
        for i in range(self.num_sides):
            next_i = (i + 1) % self.num_sides
            faces.append([i, next_i, next_i + self.num_sides, i + self.num_sides])

        # Top pyramid faces
        top_apex_idx = len(self.vertices) - 2
        for i in range(self.num_sides):
            next_i = (i + 1) % self.num_sides
            faces.append([i, next_i, top_apex_idx])

        # Bottom pyramid faces
        bottom_apex_idx = len(self.vertices) - 1
        for i in range(self.num_sides):
            next_i = (i + 1) % self.num_sides
            faces.append([i + self.num_sides, bottom_apex_idx, next_i + self.num_sides])

        self.faces = faces
        self.base_font_scale = 0.8

    def create(self, context):
        """Create the mesh and recalculate normals"""
        mesh_obj = super().create(context)
        # Recalculate normals to ensure they point outward
        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        bpy.context.view_layer.objects.active = mesh_obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')
        return mesh_obj

    def get_numbers(self):
        return numbers(self.num_faces)

    def get_number_locations(self):
        # Place numbers on the center of each side face
        # For a regular polygon with vertices at radius c0, the distance to the middle
        # of an edge (apothem) is c0 * cos(π / num_sides)
        c0 = 0.5 * self.size
        angle_step = 2 * math.pi / self.num_sides
        # Calculate apothem - distance from center to middle of edge
        apothem = c0 * math.cos(math.pi / self.num_sides)
        h = self.number_h_offset * apothem
        v = self.number_v_offset * apothem
        locations = []

        for i in range(self.num_sides):
            angle = (i + 0.5) * angle_step  # Center of the side
            # Position numbers at the face surface
            # h moves tangent to the circle (perpendicular to radial direction)
            # v moves vertically in Z
            x = apothem * math.cos(angle) + h * (-math.sin(angle))
            y = apothem * math.sin(angle) + h * math.cos(angle)
            locations.append((x, y, v))

        return locations

    def get_number_rotations(self):
        # Rotate numbers to face outward from each side
        angle_step = 2 * math.pi / self.num_sides
        rotations = []

        for i in range(self.num_sides):
            angle = (i + 0.5) * angle_step
            rotations.append((HALF_PI, 0, angle + HALF_PI))

        return rotations


class CustomShard(Mesh):
    """
    Custom shard dice mesh generator.

    Creates a shard-shaped die with a regular polygon base and pyramidal points
    on top and bottom. Numbers are placed on the bottom pyramid faces.
    Supports various face counts (4, 6, 8, 10, 12, etc.).
    """

    def __init__(self, name, size, num_faces, top_point_height, bottom_point_height, number_v_offset, number_h_offset: float = 0.0):
        super().__init__(name)
        self.num_faces = num_faces
        self.size = size
        self.number_v_offset = number_v_offset
        self.number_h_offset = number_h_offset
        self.bottom_point_height = bottom_point_height
        self.top_point_height = top_point_height

        # For a shard, numbers go on the bottom pyramid faces
        self.num_sides = num_faces

        # Calculate radius for regular polygon
        c0 = size / (2 * math.sin(math.pi / self.num_sides))
        c1 = top_point_height * c0
        c2 = bottom_point_height * c0

        # Create vertices for a regular polygon base at z=0
        angle_step = 2 * math.pi / self.num_sides
        base_vertices = []

        for i in range(self.num_sides):
            angle = i * angle_step
            x = c0 * math.cos(angle)
            y = c0 * math.sin(angle)
            base_vertices.append((x, y, 0))

        # Apex vertices
        top_apex = (0, 0, c1)
        bottom_apex = (0, 0, -c2)

        # Combine all vertices
        self.vertices = base_vertices + [top_apex, bottom_apex]

        # Create faces
        faces = []
        top_apex_idx = len(base_vertices)
        bottom_apex_idx = len(base_vertices) + 1

        # Top pyramid faces (wind counter-clockwise when viewed from outside)
        for i in range(self.num_sides):
            next_i = (i + 1) % self.num_sides
            faces.append([i, next_i, top_apex_idx])

        # Bottom pyramid faces (wind clockwise to keep normals pointing outward)
        for i in range(self.num_sides):
            next_i = (i + 1) % self.num_sides
            faces.append([i, bottom_apex_idx, next_i])

        self.faces = faces
        self.base_font_scale = 0.8

    def create(self, context):
        """Create the mesh and recalculate normals"""
        mesh_obj = super().create(context)
        # Recalculate normals to ensure they point outward
        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        bpy.context.view_layer.objects.active = mesh_obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')
        return mesh_obj

    def get_numbers(self):
        return numbers(self.num_faces)

    def get_number_locations(self):
        # Calculate number positions on bottom pyramid faces
        # Each face is a triangle: vertex i, vertex i+1, bottom apex
        # We interpolate along the face from the edge midpoint toward the apex

        angle_step = 2 * math.pi / self.num_sides
        c0 = self.size / (2 * math.sin(math.pi / self.num_sides))  # vertex radius
        c_bottom = self.bottom_point_height * c0  # bottom apex depth
        h = self.number_h_offset * c0

        locations = []
        for i in range(self.num_sides):
            # Get the two base vertices that form this face
            angle1 = i * angle_step
            angle2 = (i + 1) * angle_step

            # Midpoint of the two base vertices (on the base edge at z=0)
            edge_mid_x = (c0 * math.cos(angle1) + c0 * math.cos(angle2)) / 2
            edge_mid_y = (c0 * math.sin(angle1) + c0 * math.sin(angle2)) / 2

            # Interpolate from edge midpoint (at z=0) to bottom apex (at 0,0,-c_bottom)
            # At offset=1: at edge midpoint, at offset=0: at apex
            # h moves tangent to the face (perpendicular to radial direction)
            face_angle = (angle1 + angle2) / 2
            x = edge_mid_x * self.number_v_offset + h * (-math.sin(face_angle))
            y = edge_mid_y * self.number_v_offset + h * math.cos(face_angle)
            z = -c_bottom * (1 - self.number_v_offset)

            locations.append((x, y, z))

        return locations

    def get_number_rotations(self):
        # Calculate rotation by using the actual face normal vectors
        # Each bottom face is: vertex i, bottom_apex, vertex i+1

        angle_step = 2 * math.pi / self.num_sides
        c0 = self.size / (2 * math.sin(math.pi / self.num_sides))  # vertex radius
        c_bottom = self.bottom_point_height * c0

        rotations = []
        for i in range(self.num_sides):
            # Get the three vertices of this bottom pyramid face
            angle1 = i * angle_step
            angle2 = (i + 1) * angle_step
            center_angle = (i + 0.5) * angle_step

            # Vertex positions
            v1 = Vector((c0 * math.cos(angle1), c0 * math.sin(angle1), 0))
            v2 = Vector((0, 0, -c_bottom))  # bottom apex
            v3 = Vector((c0 * math.cos(angle2), c0 * math.sin(angle2), 0))

            # Calculate tilt angle using the same method as D4Shard
            # This measures the angle between a vertical vector and the vector to the edge midpoint
            edge_center_x = (c0 * math.cos(angle1) + c0 * math.cos(angle2)) / 2
            edge_center_y = (c0 * math.sin(angle1) + c0 * math.sin(angle2)) / 2

            # Vector from origin to vertical (above origin)
            vertical_vec = Vector((0, 0, c_bottom))
            # Vector from origin to edge center
            edge_vec = Vector((edge_center_x, edge_center_y, c_bottom))

            # Calculate angle between these vectors and add 90 degrees
            tilt_angle = math.pi / 2 + vertical_vec.angle(edge_vec)

            # Calculate the "up" vector on the face
            # The "up" direction should point from the bottom apex toward the top edge
            edge_midpoint = (v1 + v3) / 2  # midpoint of base edge
            up_on_face = edge_midpoint - v2  # vector from apex to edge midpoint
            up_on_face = up_on_face.normalized()

            # We need to find what angle to rotate the number around the face normal
            # After tilting, we want the number's local Y axis to point "up" along the face
            # The "up" direction on a tilted pyramid face points from apex toward the edge

            # Now calculate the angle we need to rotate around Y axis (roll)
            # This aligns the number's orientation with the face's orientation
            # The angle is measured from the radial direction
            radial_2d = Vector((math.cos(center_angle), math.sin(center_angle), 0))

            # Project up_on_face onto the XY plane to get its horizontal component
            up_horizontal = Vector((up_on_face.x, up_on_face.y, 0)).normalized()

            # Calculate angle between radial direction and up_horizontal
            # This is the roll we need to apply
            cos_roll = radial_2d.dot(up_horizontal)
            sin_roll = radial_2d.x * up_horizontal.y - radial_2d.y * up_horizontal.x
            y_rotation = math.atan2(sin_roll, cos_roll)

            # Add -90 degrees rotation around the Z axis to align the number with the face
            # Plus 180 degrees to flip the number so it reads correctly (not backwards)
            z_rotation = center_angle - math.pi / 2 + math.pi

            rotations.append((tilt_angle, y_rotation, z_rotation))

        return rotations


class D4Shard(CustomShard):
    """
    D4 Shard dice - a thin wrapper around CustomShard with 4 faces.

    This reuses the CustomShard logic which already handles positioning and rotation correctly.
    """

    def __init__(self, name, size, top_point_height, bottom_point_height, number_v_offset, number_h_offset: float = 0.0):
        # Simply call CustomShard with num_faces=4
        super().__init__(name, size, 4, top_point_height, bottom_point_height, number_v_offset, number_h_offset)


class CustomBipyramid(Mesh):
    """
    Custom bipyramid dice mesh generator.

    Creates a bipyramid (double pyramid) die with a regular polygon base and pyramidal points
    on both top and bottom. Numbers are placed on both the top and bottom pyramid faces.
    num_faces represents the total number of faces on the die (must be even, e.g., 6, 8, 10, 12, etc.).
    A die with 8 faces has a square base (4 sides), with 4 top faces + 4 bottom faces = 8 total.
    """

    def __init__(self, name, size, num_faces, top_point_height, bottom_point_height, number_h_offset: float = 0.0, number_v_offset: float = 0.0):
        """
        Initialize a custom bipyramid mesh.

        Args:
            name: Name for the mesh object
            size: Edge length of the base polygon
            num_faces: Total number of faces on the die (must be even, as it equals 2*base_polygon_sides)
            top_point_height: Height of the top pyramid point (relative to base radius)
            bottom_point_height: Height of the bottom pyramid point (relative to base radius)
            number_h_offset: Horizontal offset for numbers on faces
            number_v_offset: Vertical offset for numbers on faces
        """
        super().__init__(name)
        # Enforce even face count with minimum 6
        self.num_faces = max(6, num_faces if num_faces % 2 == 0 else num_faces + 1)  # Total number of faces
        self.size = size
        self.number_h_offset = number_h_offset
        self.number_v_offset = number_v_offset
        self.top_point_height = top_point_height
        self.bottom_point_height = bottom_point_height

        # Number of base polygon sides = num_faces / 2
        self.num_sides = self.num_faces // 2

        # Calculate radius for regular polygon
        c0 = size / (2 * math.sin(math.pi / self.num_sides))
        c1 = top_point_height * c0
        c2 = bottom_point_height * c0

        # Create vertices for a regular polygon base at z=0
        angle_step = 2 * math.pi / self.num_sides
        base_vertices = []

        for i in range(self.num_sides):
            angle = i * angle_step
            x = c0 * math.cos(angle)
            y = c0 * math.sin(angle)
            base_vertices.append((x, y, 0))

        # Apex vertices
        top_apex = (0, 0, c1)
        bottom_apex = (0, 0, -c2)

        # Combine all vertices
        self.vertices = base_vertices + [top_apex, bottom_apex]

        # Create faces
        faces = []
        top_apex_idx = len(base_vertices)
        bottom_apex_idx = len(base_vertices) + 1

        # Top pyramid faces (wind counter-clockwise when viewed from outside)
        for i in range(self.num_sides):
            next_i = (i + 1) % self.num_sides
            faces.append([i, next_i, top_apex_idx])

        # Bottom pyramid faces (wind clockwise to keep normals pointing outward)
        for i in range(self.num_sides):
            next_i = (i + 1) % self.num_sides
            faces.append([i, bottom_apex_idx, next_i])

        self.faces = faces
        self.base_font_scale = 0.8

    def create(self, context):
        """Create the mesh and recalculate normals"""
        mesh_obj = super().create(context)
        # Recalculate normals to ensure they point outward
        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        bpy.context.view_layer.objects.active = mesh_obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')
        return mesh_obj

    def get_numbers(self):
        return numbers(self.num_faces)  # num_faces now represents total face count

    def get_number_locations(self):
        # Calculate number positions on both top and bottom pyramid faces using rotation matrices
        angle_step = 2 * math.pi / self.num_sides
        c0 = self.size / (2 * math.sin(math.pi / self.num_sides))  # vertex radius
        c_top = self.top_point_height * c0
        c_bottom = self.bottom_point_height * c0

        # Get rotations to derive local coordinate systems
        rotations = self.get_number_rotations()

        locations = []

        # Scale factors for offsets
        h_scale = self.number_h_offset * self.size * 0.5
        v_scale = self.number_v_offset * self.size * 0.5

        # Top pyramid faces
        for i in range(self.num_sides):
            # Get the two base vertices that form this face
            angle1 = i * angle_step
            angle2 = (i + 1) * angle_step

            # Midpoint of the two base vertices (on the base edge at z=0)
            edge_mid_x = (c0 * math.cos(angle1) + c0 * math.cos(angle2)) / 2
            edge_mid_y = (c0 * math.sin(angle1) + c0 * math.sin(angle2)) / 2

            # For top pyramid: lerp from edge midpoint toward top apex
            # Default position is 1/3 up from base edge to apex (looks good visually)
            lerp_factor = 0.33
            base_pos = Vector((
                edge_mid_x * (1 - lerp_factor),
                edge_mid_y * (1 - lerp_factor),
                c_top * lerp_factor
            ))

            # Use rotation matrix to get local coordinate system
            rot = rotations[i]
            euler = Euler(rot, 'XYZ')
            rot_matrix = euler.to_matrix()
            local_right = Vector((1, 0, 0))
            local_up = Vector((0, 1, 0))
            world_right = rot_matrix @ local_right
            world_up = rot_matrix @ local_up

            # Apply offsets in face-local coordinates
            pos = base_pos + world_right * h_scale + world_up * v_scale
            locations.append(tuple(pos))

        # Bottom pyramid faces
        for i in range(self.num_sides):
            # Get the two base vertices that form this face
            angle1 = i * angle_step
            angle2 = (i + 1) * angle_step

            # Midpoint of the two base vertices (on the base edge at z=0)
            edge_mid_x = (c0 * math.cos(angle1) + c0 * math.cos(angle2)) / 2
            edge_mid_y = (c0 * math.sin(angle1) + c0 * math.sin(angle2)) / 2

            # For bottom pyramid: lerp from edge midpoint toward bottom apex
            lerp_factor = 0.33
            base_pos = Vector((
                edge_mid_x * (1 - lerp_factor),
                edge_mid_y * (1 - lerp_factor),
                -c_bottom * lerp_factor
            ))

            # Use rotation matrix to get local coordinate system
            rot = rotations[self.num_sides + i]
            euler = Euler(rot, 'XYZ')
            rot_matrix = euler.to_matrix()
            local_right = Vector((1, 0, 0))
            local_up = Vector((0, 1, 0))
            world_right = rot_matrix @ local_right
            world_up = rot_matrix @ local_up

            # Apply offsets in face-local coordinates
            pos = base_pos + world_right * h_scale + world_up * v_scale
            locations.append(tuple(pos))

        return locations

    def get_number_rotations(self):
        # Calculate rotations for both top and bottom pyramid faces based on face normals
        angle_step = 2 * math.pi / self.num_sides
        c0 = self.size / (2 * math.sin(math.pi / self.num_sides))
        c_top = self.top_point_height * c0
        c_bottom = self.bottom_point_height * c0

        rotations = []

        # Precompute base vertices
        base_vertices = [Vector((c0 * math.cos(i * angle_step), c0 * math.sin(i * angle_step), 0)) for i in range(self.num_sides)]
        top_apex = Vector((0, 0, c_top))
        bottom_apex = Vector((0, 0, -c_bottom))

        def orientation_from_face(v0: Vector, v1: Vector, v2: Vector, apex: Vector, base_a: Vector, base_b: Vector) -> Tuple[float, float, float]:
            # Outward normal from face winding
            normal = (v1 - v0).cross(v2 - v0).normalized()

            # Up direction: project apex->edge_mid onto the face plane to keep numbers upright on the face
            edge_mid = (base_a + base_b) / 2
            up_hint = edge_mid - apex
            up_proj = (up_hint - normal * up_hint.dot(normal)).normalized()

            # Right-handed basis: X=right, Y=up, Z=normal
            right = up_proj.cross(normal).normalized()
            face_up = normal.cross(right).normalized()

            rot_matrix = Matrix((right, face_up, normal)).transposed()
            euler = rot_matrix.to_euler('XYZ')
            return (euler.x, euler.y, euler.z)

        # Top pyramid faces (winding: base_i, base_next, apex)
        for i in range(self.num_sides):
            v0 = base_vertices[i]
            v1 = base_vertices[(i + 1) % self.num_sides]
            rotations.append(orientation_from_face(v0, v1, top_apex, top_apex, v0, v1))

        # Bottom pyramid faces (winding: base_i, apex, base_next) to keep normals outward
        for i in range(self.num_sides):
            v0 = base_vertices[i]
            v1 = bottom_apex
            v2 = base_vertices[(i + 1) % self.num_sides]
            rotations.append(orientation_from_face(v0, v1, v2, bottom_apex, v0, v2))

        return rotations


class Cube(Mesh):
    """
    Cubic dice (D6) mesh generator.

    Creates a regular cube (hexahedron) with numbers 1-6 placed on each face.
    Opposite faces sum to 7 following standard dice conventions.
    """

    def __init__(self, name: str, size: float, number_h_offset: float = 0.0, number_v_offset: float = 0.0):
        """
        Initialize a cube dice mesh.

        Args:
            name: Name for the mesh object
            size: Face-to-face size of the cube
            number_h_offset: Horizontal offset for numbers on faces
            number_v_offset: Vertical offset for numbers on faces
        """
        super().__init__(name)

        # Calculate the necessary constants
        self.v_coord_const = 0.5 * size
        self.number_h_offset = number_h_offset
        self.number_v_offset = number_v_offset
        s = self.v_coord_const

        # create the vertices and faces
        self.vertices = [(-s, -s, -s), (s, -s, -s), (s, s, -s), (-s, s, -s), (-s, -s, s), (s, -s, s), (s, s, s),
                         (-s, s, s)]
        self.faces = [[0, 3, 2, 1], [0, 1, 5, 4], [0, 4, 7, 3], [6, 5, 1, 2], [6, 2, 3, 7], [6, 7, 4, 5]]

    def get_numbers(self):
        return numbers(6)

    def get_number_locations(self):
        s = self.v_coord_const
        h = self.number_h_offset * s
        v = self.number_v_offset * s
        # Each tuple represents (x, y, z) position of number on each face
        # Offsets are applied in the face's local coordinate system:
        # Face 1 (front, -Y): h along X, v along Z
        # Face 2 (left, -X): h along Z, v along Y
        # Face 3 (top, +Z): h along X, v along Y
        # Face 4 (bottom, -Z): h along X, v along Y
        # Face 5 (right, +X): h along Z, v along Y
        # Face 6 (back, +Y): h along X, v along Z
        return [(h, -s, v), (-s, -h, v), (h, v, s), (h, v, -s), (s, h, v), (h, s, v)]

    def get_number_rotations(self):
        return [
            (HALF_PI, 0, 0),
            (math.pi, HALF_PI, 0),
            (0, 0, 0),
            (math.pi, 0, 0),
            (0, HALF_PI, 0),
            (-HALF_PI, 0, 0)
        ]


class Octahedron(Mesh):

    def __init__(self, name, size, number_h_offset: float = 0.0, number_v_offset: float = 0.0):
        super().__init__(name)

        # calculate circumscribed sphere radius from inscribed sphere radius
        # diameter of the inscribed sphere is the face 2 face length of the octahedron
        self.circumscribed_r = (size * math.sqrt(3)) / 2
        self.number_h_offset = number_h_offset
        self.number_v_offset = number_v_offset
        s = self.circumscribed_r

        # create the vertices and faces
        self.vertices = [(s, 0, 0), (-s, 0, 0), (0, s, 0), (0, -s, 0), (0, 0, s), (0, 0, -s)]
        self.faces = [[4, 0, 2], [4, 2, 1], [4, 1, 3], [4, 3, 0], [5, 2, 0], [5, 1, 2], [5, 3, 1], [5, 0, 3]]

        self.base_font_scale = 0.7

    def get_numbers(self):
        return numbers(8)

    def get_number_locations(self):
        c = self.circumscribed_r / 3

        # Base positions at face centers
        base_positions = [
            Vector((c, c, c)),      # Face 0
            Vector((-c, c, c)),     # Face 1
            Vector((-c, -c, c)),    # Face 2
            Vector((c, -c, c)),     # Face 3
            Vector((-c, c, -c)),    # Face 4
            Vector((c, c, -c)),     # Face 5
            Vector((c, -c, -c)),    # Face 6
            Vector((-c, -c, -c)),   # Face 7
        ]

        # Get the rotations to understand number orientation
        rotations = self.get_number_rotations()

        locations = []
        h_scale = self.number_h_offset * c
        v_scale = self.number_v_offset * c

        for i, rot in enumerate(rotations):
            # Create rotation matrix from Euler angles
            euler = Euler(rot, 'XYZ')
            rot_matrix = euler.to_matrix()

            # In the number's local space, X is right, Y is up (before rotation)
            # Apply rotation to get world-space directions
            local_right = Vector((1, 0, 0))
            local_up = Vector((0, 1, 0))

            world_right = rot_matrix @ local_right
            world_up = rot_matrix @ local_up

            # Start with base position and apply offsets
            pos = base_positions[i].copy()
            pos += world_right * h_scale + world_up * v_scale
            locations.append((pos.x, pos.y, pos.z))

        return locations

    def get_number_rotations(self):
        # dihedral angle / 2 - for tilting numbers to match face angle
        da = math.acos(-1 / 3)
        # Octahedron faces are organized as top pyramid (faces 0-3) and bottom pyramid (faces 4-7)
        # Each face is a triangle with a specific orientation that determines the z-rotation
        angles = [Euler((0, 0, 0), 'XYZ') for _ in range(8)]

        # Top pyramid faces - pointing upward (apex at vertex 4: (0,0,s))
        # Face 0: [4,0,2] - edge from +X to +Y
        angles[0].x = da / 2
        angles[0].z = math.pi * 3 / 4

        # Face 1: [4,2,1] - edge from +Y to -X
        angles[1].x = da / 2
        angles[1].z = math.pi * 5 / 4

        # Face 2: [4,1,3] - edge from -X to -Y
        angles[2].x = da / 2
        angles[2].z = math.pi * 7 / 4

        # Face 3: [4,3,0] - edge from -Y to +X
        angles[3].x = da / 2
        angles[3].z = math.pi * 1 / 4

        # Bottom pyramid faces - pointing downward (apex at vertex 5: (0,0,-s))
        # Face 4: [5,2,0] - number 5 (adjusting)
        angles[4].x = -math.pi + da / 2
        angles[4].z = math.pi * 1 / 4

        # Face 5: [5,1,2] - number 6 (CORRECT - don't change)
        angles[5].x = -math.pi + da / 2
        angles[5].z = math.pi * 7 / 4

        # Face 6: [5,3,1] - number 7 (CORRECT - don't change)
        angles[6].x = -math.pi + da / 2
        angles[6].z = math.pi * 5 / 4

        # Face 7: [5,0,3] - number 8 (adjusting)
        angles[7].x = -math.pi + da / 2
        angles[7].z = math.pi * 3 / 4

        return [(a.x, a.y, a.z) for a in angles]


class Dodecahedron(Mesh):

    def __init__(self, name, size, number_h_offset: float = 0.0, number_v_offset: float = 0.0):
        super().__init__(name)
        self.size = size
        self.number_h_offset = number_h_offset
        self.number_v_offset = number_v_offset

        # Calculate the necessary constants https://dmccooey.com/polyhedra/Dodecahedron.html
        edge_length = size / 2 / CONSTANTS['octahedron']['inscribed_r']

        c0 = CONSTANTS['octahedron']['c0'] * edge_length
        c1 = CONSTANTS['octahedron']['c1'] * edge_length
        s = CONSTANTS['octahedron']['c2'] * edge_length

        self.vertices = [(0.0, s, c1), (0.0, s, -c1), (0.0, -s, c1), (0.0, -s, -c1), (c1, 0.0, s), (c1, 0.0, -s),
                         (-c1, 0.0, s), (-c1, 0.0, -s), (s, c1, 0.0), (s, -c1, 0.0), (-s, c1, 0.0), (-s, -c1, 0.0),
                         (c0, c0, c0), (c0, c0, -c0), (c0, -c0, c0), (c0, -c0, -c0), (-c0, c0, c0), (-c0, c0, -c0),
                         (-c0, -c0, c0), (-c0, -c0, -c0)]

        self.faces = [[0, 2, 14, 4, 12], [0, 12, 8, 10, 16], [0, 16, 6, 18, 2], [7, 6, 16, 10, 17],
                      [7, 17, 1, 3, 19], [7, 19, 11, 18, 6], [9, 11, 19, 3, 15], [9, 15, 5, 4, 14],
                      [9, 14, 2, 18, 11], [13, 1, 17, 10, 8], [13, 8, 12, 4, 5], [13, 5, 15, 3, 1]]

        self.base_font_scale = 0.5

    def get_numbers(self):
        return numbers(12)

    def get_number_locations(self):
        # Numbers placed at dual polyhedron (icosahedron) vertices
        dual_e = self.size / 2 / CONSTANTS['icosahedron']['circumscribed_r']
        c0 = dual_e * CONSTANTS['icosahedron']['c0']
        c1 = dual_e * CONSTANTS['icosahedron']['c1']

        # Base positions at icosahedron vertices (dual of dodecahedron)
        base_positions = [
            Vector((c1, 0, c0)),
            Vector((0, c0, c1)),
            Vector((-c1, 0, c0)),
            Vector((0, -c0, c1)),
            Vector((c0, -c1, 0)),
            Vector((c0, c1, 0)),
            Vector((-c0, -c1, 0)),
            Vector((-c0, c1, 0)),
            Vector((0, c0, -c1)),
            Vector((c1, 0, -c0)),
            Vector((0, -c0, -c1)),
            Vector((-c1, 0, -c0)),
        ]

        # Get the rotations to understand number orientation
        rotations = self.get_number_rotations()

        locations = []
        h_scale = self.number_h_offset * c0
        v_scale = self.number_v_offset * c0

        for base_pos, rot in zip(base_positions, rotations):
            # Create rotation matrix from Euler angles
            euler = Euler(rot, 'XYZ')
            rot_matrix = euler.to_matrix()

            # In the number's local space, X is right, Y is up (before rotation)
            local_right = Vector((1, 0, 0))
            local_up = Vector((0, 1, 0))

            world_right = rot_matrix @ local_right
            world_up = rot_matrix @ local_up

            # Apply offsets in the number's coordinate system
            pos = base_pos.copy() + world_right * h_scale + world_up * v_scale
            locations.append((pos.x, pos.y, pos.z))

        return locations

    def get_number_rotations(self):
        angles = [Euler((0, 0, 0), 'XYZ') for _ in range(12)]

        angles[0].z = math.radians(-162)
        angles[0].rotate(Euler((0, (math.pi - CONSTANTS['octahedron']['dihedral_angle']) / 2, 0), 'XYZ'))

        angles[1].z = math.radians(36)
        angles[1].rotate(Euler((CONSTANTS['octahedron']['dihedral_angle'] / -2, 0, 0), 'XYZ'))

        angles[2].z = HALF_PI
        angles[2].x = -(math.pi - CONSTANTS['octahedron']['dihedral_angle']) / 2

        angles[3].z = math.radians(144)
        angles[3].rotate(Euler((CONSTANTS['octahedron']['dihedral_angle'] / 2, 0, 0), 'XYZ'))

        angles[4].y = HALF_PI
        angles[4].rotate(Euler((-math.radians(108), 0, 0), 'XYZ'))
        angles[4].rotate(Euler((0, 0, (math.pi - CONSTANTS['octahedron']['dihedral_angle']) / -2), 'XYZ'))

        angles[5].y = HALF_PI
        angles[5].rotate(Euler((-math.radians(72), 0, 0), 'XYZ'))
        angles[5].rotate(Euler((0, 0, (math.pi - CONSTANTS['octahedron']['dihedral_angle']) / 2), 'XYZ'))

        angles[6].y = -HALF_PI
        angles[6].rotate(Euler((math.radians(108), 0, 0), 'XYZ'))
        angles[6].rotate(Euler((0, 0, (math.pi - CONSTANTS['octahedron']['dihedral_angle']) / 2), 'XYZ'))

        angles[7].y = HALF_PI
        angles[7].rotate(Euler((math.radians(72), 0, 0), 'XYZ'))
        angles[7].rotate(Euler((0, 0, -(math.pi - CONSTANTS['octahedron']['dihedral_angle']) / 2), 'XYZ'))

        angles[8].z = math.radians(-36)
        angles[8].y = math.pi
        angles[8].rotate(Euler((CONSTANTS['octahedron']['dihedral_angle'] / 2, 0, 0), 'XYZ'))

        angles[9].x = math.pi
        angles[9].z = HALF_PI
        angles[9].rotate(Euler((0, -(math.pi - CONSTANTS['octahedron']['dihedral_angle']) / 2, 0), 'XYZ'))

        angles[10].x = math.pi
        angles[10].z = math.radians(36)
        angles[10].rotate(Euler((-CONSTANTS['octahedron']['dihedral_angle'] / 2, 0, 0), 'XYZ'))

        angles[11].z = math.radians(342)
        angles[11].rotate(Euler((0, math.pi + (math.pi - CONSTANTS['octahedron']['dihedral_angle']) / 2, 0), 'XYZ'))

        return [(a.x, a.y, a.z) for a in angles]


class Icosahedron(Mesh):

    def __init__(self, name, size, number_h_offset: float = 0.0, number_v_offset: float = 0.0):
        super().__init__(name)
        self.size = size
        self.number_h_offset = number_h_offset
        self.number_v_offset = number_v_offset

        # Calculate the necessary constants https://dmccooey.com/polyhedra/Icosahedron.html
        edge_length = size / 2 / CONSTANTS['icosahedron']['inscribed_r']

        c0 = edge_length * CONSTANTS['icosahedron']['c0']
        c1 = edge_length * CONSTANTS['icosahedron']['c1']

        self.vertices = [(c1, 0.0, c0), (c1, 0.0, -c0), (-c1, 0.0, c0), (-c1, 0.0, -c0), (c0, c1, 0.0), (c0, -c1, 0.0),
                         (-c0, c1, 0.0), (-c0, -c1, 0.0), (0.0, c0, c1), (0.0, c0, -c1), (0.0, -c0, c1),
                         (0.0, -c0, -c1)]
        self.faces = [[0, 2, 10], [0, 10, 5], [0, 5, 4], [0, 4, 8], [0, 8, 2], [3, 1, 11], [3, 11, 7], [3, 7, 6],
                      [3, 6, 9], [3, 9, 1], [2, 6, 7], [2, 7, 10], [10, 7, 11], [10, 11, 5], [5, 11, 1], [5, 1, 4],
                      [4, 1, 9], [4, 9, 8], [8, 9, 6], [8, 6, 2]]

        self.base_font_scale = 0.3

    def get_numbers(self):
        return numbers(20)

    def get_number_locations(self):
        # Numbers are placed at the dual polyhedron (dodecahedron) vertices
        dual_e = self.size / 2 / CONSTANTS['octahedron']['circumscribed_r']

        c0 = CONSTANTS['octahedron']['c0'] * dual_e
        c1 = CONSTANTS['octahedron']['c1'] * dual_e
        s = CONSTANTS['octahedron']['c2'] * dual_e

        # Base positions at dodecahedron vertices
        base_positions = [
            Vector((0, s, c1)),      # Face 0
            Vector((-c0, -c0, -c0)), # Face 1
            Vector((s, c1, 0)),      # Face 2
            Vector((s, -c1, 0)),     # Face 3
            Vector((-c0, -c0, c0)),  # Face 4
            Vector((c1, 0, -s)),     # Face 5
            Vector((-c0, c0, c0)),   # Face 6
            Vector((0, s, -c1)),     # Face 7
            Vector((c1, 0, s)),      # Face 8
            Vector((-c0, c0, -c0)),  # Face 9
            Vector((c0, -c0, c0)),   # Face 10
            Vector((-c1, 0, -s)),    # Face 11
            Vector((0, -s, c1)),     # Face 12
            Vector((c0, -c0, -c0)),  # Face 13
            Vector((-c1, 0, s)),     # Face 14
            Vector((c0, c0, -c0)),   # Face 15
            Vector((-s, c1, 0)),     # Face 16
            Vector((-s, -c1, 0)),    # Face 17
            Vector((c0, c0, c0)),    # Face 18
            Vector((0, -s, -c1))     # Face 19
        ]

        # Get the rotations to understand number orientation
        rotations = self.get_number_rotations()

        locations = []
        h_scale = self.number_h_offset * self.size / 6
        v_scale = self.number_v_offset * self.size / 6

        for base_pos, rot in zip(base_positions, rotations):
            # Create rotation matrix from Euler angles
            euler = Euler(rot, 'XYZ')
            rot_matrix = euler.to_matrix()

            # In the number's local space, X is right, Y is up (before rotation)
            local_right = Vector((1, 0, 0))
            local_up = Vector((0, 1, 0))

            world_right = rot_matrix @ local_right
            world_up = rot_matrix @ local_up

            # Apply offsets in the number's coordinate system
            pos = base_pos.copy() + world_right * h_scale + world_up * v_scale
            locations.append((pos.x, pos.y, pos.z))

        return locations

    def get_number_rotations(self):
        """
        Calculate rotation angles for number placement on icosahedron faces.

        Note: Some angles are empirically determined. See ICOSAHEDRON_ROTATION_ANGLES
        for details and the TODO about calculating them analytically.

        Returns:
            List of rotation tuples (x, y, z) for each face
        """
        angles = [Euler((0, 0, 0), 'XYZ') for _ in range(20)]

        dihedral_half = (math.pi - CONSTANTS['icosahedron']['dihedral_angle']) / 2

        angles[0].x = -dihedral_half

        angles[1].x = -ICOSAHEDRON_ROTATION_ANGLES['angle_1']
        angles[1].y = -ICOSAHEDRON_ROTATION_ANGLES['angle_2']
        angles[1].z = -ICOSAHEDRON_ROTATION_ANGLES['angle_3']

        angles[2].x = HALF_PI
        angles[2].y = 5 * SIXTH_PI
        angles[2].z = math.pi - dihedral_half

        angles[3].x = HALF_PI
        angles[3].y = -SIXTH_PI
        angles[3].z = dihedral_half

        angles[4].x = -ICOSAHEDRON_ROTATION_ANGLES['angle_1']
        angles[4].y = -ICOSAHEDRON_ROTATION_ANGLES['angle_4']
        angles[4].z = ICOSAHEDRON_ROTATION_ANGLES['angle_5']

        angles[5].x = HALF_PI
        angles[5].y = THIRD_PI
        angles[5].z = HALF_PI
        angles[5].rotate(Euler((0, dihedral_half, 0), 'XYZ'))

        angles[6].x = -ICOSAHEDRON_ROTATION_ANGLES['angle_1']
        angles[6].y = ICOSAHEDRON_ROTATION_ANGLES['angle_4']
        angles[6].z = ICOSAHEDRON_ROTATION_ANGLES['angle_8']

        angles[7].x = -dihedral_half
        angles[7].y = math.pi

        angles[8].x = -HALF_PI
        angles[8].y = -THIRD_PI
        angles[8].z = -HALF_PI
        angles[8].rotate(Euler((0, -dihedral_half, 0), 'XYZ'))

        angles[9].x = -ICOSAHEDRON_ROTATION_ANGLES['angle_6']
        angles[9].y = ICOSAHEDRON_ROTATION_ANGLES['angle_4']
        angles[9].z = -ICOSAHEDRON_ROTATION_ANGLES['angle_5']

        angles[10].x = -ICOSAHEDRON_ROTATION_ANGLES['angle_1']
        angles[10].y = ICOSAHEDRON_ROTATION_ANGLES['angle_4']
        angles[10].z = -ICOSAHEDRON_ROTATION_ANGLES['angle_5']

        angles[11].x = HALF_PI
        angles[11].y = -THIRD_PI
        angles[11].z = -HALF_PI
        angles[11].rotate(Euler((0, -dihedral_half, 0), 'XYZ'))

        angles[12].x = -dihedral_half
        angles[12].z = math.pi

        angles[13].x = ICOSAHEDRON_ROTATION_ANGLES['angle_7']
        angles[13].y = ICOSAHEDRON_ROTATION_ANGLES['angle_4']
        angles[13].z = ICOSAHEDRON_ROTATION_ANGLES['angle_8']

        angles[14].x = -HALF_PI
        angles[14].y = THIRD_PI
        angles[14].z = HALF_PI
        angles[14].rotate(Euler((0, dihedral_half, 0), 'XYZ'))

        angles[15].x = -ICOSAHEDRON_ROTATION_ANGLES['angle_1']
        angles[15].y = -ICOSAHEDRON_ROTATION_ANGLES['angle_2']
        angles[15].z = -ICOSAHEDRON_ROTATION_ANGLES['angle_8']

        angles[16].x = HALF_PI
        angles[16].y = 7 * SIXTH_PI
        angles[16].z = math.pi + dihedral_half

        angles[17].x = HALF_PI
        angles[17].y = SIXTH_PI
        angles[17].z = -dihedral_half

        angles[18].x = -ICOSAHEDRON_ROTATION_ANGLES['angle_1']
        angles[18].y = -ICOSAHEDRON_ROTATION_ANGLES['angle_4']
        angles[18].z = -ICOSAHEDRON_ROTATION_ANGLES['angle_8']

        angles[19].x = math.pi
        angles[19].z = 2 * THIRD_PI
        angles[19].rotate(Euler((-dihedral_half, 0, 0), 'XYZ'))

        return [(a.x, a.y, a.z) for a in angles]


class SquashedPentagonalTrapezohedron(Mesh):
    """
    Pentagonal trapezohedron mesh generator (base for D10 and D100).

    This shape has 10 kite-shaped faces and is the standard shape for d10 dice.
    The shape can be "squashed" along the vertical axis by adjusting the height parameter.
    """

    def __init__(self, name: str, size: float, height: float, number_v_offset: float, number_h_offset: float = 0.0):
        """
        Initialize a pentagonal trapezohedron mesh.

        Args:
            name: Name for the mesh object
            size: Face-to-face size of the die
            height: Height scaling factor (1.0 = regular, <1.0 = squashed, >1.0 = elongated)
            number_v_offset: Vertical offset for number placement (0=bottom, 1=top of face)
            number_h_offset: Horizontal offset for number placement
        """
        super().__init__(name)
        self.size = size
        self.height = height
        self.number_v_offset = number_v_offset
        self.number_h_offset = number_h_offset

        antiprism_e = size / 2 / CONSTANTS['pentagonal_trap']['inscribed_r']

        c0 = CONSTANTS['pentagonal_trap']['c0'] * antiprism_e
        c1 = CONSTANTS['pentagonal_trap']['c1'] * antiprism_e
        c2 = CONSTANTS['pentagonal_trap']['c2'] * antiprism_e
        c3 = CONSTANTS['pentagonal_trap']['c3'] * antiprism_e

        scaled_base_height = CONSTANTS['pentagonal_trap']['base_height'] * size
        scaled_base_width = CONSTANTS['pentagonal_trap']['base_width'] * size

        scaled_height = scaled_base_height * height
        scaled_width = leg_b(scaled_height, size / 2)
        width = scaled_width / scaled_base_width

        # TODO figure out where this angle comes from
        self.vertices = [(0.0, c0, c1), (0.0, c0, -c1), (0.0, -c0, c1), (0.0, -c0, -c1), (c3, c3, c3), (c3, c3, -c3),
                         (-c3, -c3, c3), (-c3, -c3, -c3), (c2, -c1, 0.0), (-c2, c1, 0.0), (c0, c1, 0.0),
                         (-c0, -c1, 0.0)]

        def transform(v):
            # rotate the vectors, so the trapezohedron is up right
            vector = Vector(v)
            vector.rotate(CONSTANTS['pentagonal_trap']['angle'])

            # scale the body
            vector.z *= height
            vector.y *= width
            vector.x *= width
            return vector.x, vector.y, vector.z

        self.vertices = list(map(transform, self.vertices))

        self.faces = [[8, 2, 6, 11], [8, 11, 7, 3], [8, 3, 1, 5], [8, 5, 10, 4], [8, 4, 0, 2], [9, 0, 4, 10],
                      [9, 10, 5, 1], [9, 1, 3, 7], [9, 7, 11, 6], [9, 6, 2, 0]]

    def get_number_locations(self):
        vectors = [Vector(v) for v in self.vertices]

        # Face vertex pairs for vertical lerp
        face_vertices_data = [
            (vectors[6], vectors[8]),  # Face 0
            (vectors[3], vectors[9]),  # Face 1
            (vectors[1], vectors[8]),  # Face 2
            (vectors[4], vectors[9]),  # Face 3
            (vectors[10], vectors[8]), # Face 4
            (vectors[11], vectors[9]), # Face 5
            (vectors[7], vectors[8]),  # Face 6
            (vectors[2], vectors[9]),  # Face 7
            (vectors[0], vectors[8]),  # Face 8
            (vectors[5], vectors[9])   # Face 9
        ]

        # Get the rotations to understand number orientation
        rotations = self.get_number_rotations()

        locations = []
        lerp_factor = self.number_v_offset
        h_scale = self.number_h_offset * self.size / 4
        v_scale = self.number_v_offset * self.size / 4

        for (v1, v2), rot in zip(face_vertices_data, rotations):
            # Base position from vertical offset (lerp between two opposite vertices)
            base_pos = v1.lerp(v2, lerp_factor)

            # Create rotation matrix from Euler angles
            euler = Euler(rot, 'XYZ')
            rot_matrix = euler.to_matrix()

            # In the number's local space, X is right, Y is up (before rotation)
            local_right = Vector((1, 0, 0))
            local_up = Vector((0, 1, 0))

            world_right = rot_matrix @ local_right
            world_up = rot_matrix @ local_up

            # Apply offsets in the number's coordinate system
            pos = base_pos + world_right * h_scale + world_up * v_scale
            locations.append((pos.x, pos.y, pos.z))

        return locations

    def get_number_rotations(self):
        a = Vector(self.vertices[9])
        b = Vector(self.vertices[10]) - Vector(self.vertices[8])
        number_angle = HALF_PI - a.angle(b)
        return [
            (number_angle, 0, -HALF_PI - math.pi * 6 / 5),
            (math.pi + number_angle, 0, -HALF_PI - math.pi * 8 / 5),
            (number_angle, 0, -HALF_PI - math.pi * 2 / 5),
            (math.pi + number_angle, 0, -HALF_PI - math.pi * 4 / 5),
            (number_angle, 0, -HALF_PI),
            (math.pi + number_angle, 0, -HALF_PI),
            (number_angle, 0, -HALF_PI - math.pi * 4 / 5),
            (math.pi + number_angle, 0, -HALF_PI - math.pi * 2 / 5),
            (number_angle, 0, -HALF_PI - math.pi * 8 / 5),
            (math.pi + number_angle, 0, -HALF_PI - math.pi * 6 / 5)
        ]


class D10Mesh(SquashedPentagonalTrapezohedron):

    def __init__(self, name, size, height, number_v_offset, number_h_offset: float = 0.0):
        super().__init__(name, size, height, number_v_offset, number_h_offset)
        self.base_font_scale = 0.6

    def get_numbers(self):
        return [str((i + 1) % 10) for i in range(10)]


class D100Mesh(SquashedPentagonalTrapezohedron):

    def __init__(self, name, size, height, number_v_offset, number_h_offset: float = 0.0):
        super().__init__(name, size, height, number_v_offset, number_h_offset)
        self.base_font_scale = 0.45

    def get_numbers(self):
        return [f'{str((i + 1) % 10)}0' for i in range(10)]


class CustomTrapezohedron(Mesh):
    """
    Custom trapezohedron (d10-style) with independent top/bottom point heights.

    Supports any even face count (minimum 6 faces). Top/bottom heights scale the positive/negative Z halves independently.
    """

    def __init__(self, name: str, size: float, num_faces: int, height: float, number_v_offset: float, number_h_offset: float = 0.0):
        Mesh.__init__(self, name)
        # Ensure an even face count of at least 6 (>= triangular trapezohedron)
        self.num_faces = max(6, num_faces if num_faces % 2 == 0 else num_faces + 1)
        self.num_sides = self.num_faces // 2
        self.size = size
        self.height = height
        self.number_v_offset = number_v_offset
        self.number_h_offset = number_h_offset
        self.base_font_scale = 0.5

        def build_antiprism(n: int):
            step = 2 * math.pi / n
            half = step / 2.0
            r = 1.0 / (2.0 * math.sin(math.pi / n))
            lateral_sq = 1.0 - 2 * r * r * (1 - math.cos(math.pi / n))
            h = math.sqrt(max(lateral_sq, 1e-8))
            z_top = h / 2.0
            z_bot = -h / 2.0

            verts = []
            for i in range(n):
                ang = i * step
                verts.append((r * math.cos(ang), r * math.sin(ang), z_top))
            for i in range(n):
                ang = i * step + half
                verts.append((r * math.cos(ang), r * math.sin(ang), z_bot))

            faces = []
            faces.append(list(range(n)))  # top
            faces.append(list(range(2 * n - 1, n - 1, -1)))  # bottom
            for i in range(n):
                a = i
                b = n + i
                c = n + ((i - 1) % n)
                faces.append([a, b, c])
                d = (i + 1) % n
                faces.append([a, d, b])
            return verts, faces

        def dual_mesh(verts, faces):
            vectors = [Vector(v) for v in verts]
            dual_verts = []
            for f in faces:
                v0, v1, v2 = (vectors[f[0]], vectors[f[1]], vectors[f[2]])
                normal = (v1 - v0).cross(v2 - v0)
                if normal.length == 0:
                    dual_verts.append(Vector((0, 0, 0)))
                    continue
                plane_offset = normal.dot(v0)
                dual_verts.append(normal / plane_offset)

            dual_faces = []
            for vi, v in enumerate(vectors):
                adjacent = []
                for fi, f in enumerate(faces):
                    if vi in f:
                        centroid = sum((vectors[idx] for idx in f), Vector((0, 0, 0))) / len(f)
                        adjacent.append((fi, centroid))

                axis = v.normalized()
                ref = Vector((1, 0, 0)) if abs(axis.x) < 0.9 else Vector((0, 1, 0))
                tangent = axis.cross(ref).normalized()
                bitangent = axis.cross(tangent).normalized()

                def angle_of(item):
                    fi, cent = item
                    vec = (dual_verts[fi] - v).normalized()
                    x = vec.dot(tangent)
                    y = vec.dot(bitangent)
                    return math.atan2(y, x)

                adjacent.sort(key=angle_of)
                dual_faces.append([fi for fi, _ in adjacent])

            return dual_verts, dual_faces

        # Build dual of a uniform antiprism to get an accurate trapezohedron
        anti_verts, anti_faces = build_antiprism(self.num_sides)
        trap_verts, trap_faces = dual_mesh(anti_verts, anti_faces)

        # Scale XY to requested size, Z independently to requested point heights
        xs = [v.x for v in trap_verts]
        ys = [v.y for v in trap_verts]
        zs = [v.z for v in trap_verts]
        current_radius = max(max(abs(min(xs)), abs(max(xs))), max(abs(min(ys)), abs(max(ys))), 1e-6)
        current_top = max(zs)
        current_bottom = min(zs)

        target_radius = size * 0.5
        target_top = target_radius * height
        target_bottom = -target_radius * height

        scale_xy = target_radius / current_radius
        scale_z = (target_top - target_bottom) / (current_top - current_bottom)

        def scale_vert(v: Vector):
            return (v.x * scale_xy, v.y * scale_xy, (v.z - current_bottom) * scale_z + target_bottom)

        self.vertices = [scale_vert(v) for v in trap_verts]
        self.faces = trap_faces

    def _face_frames(self):
        """
        Build local frames (center, right, up, normal) for each face with consistent orientation.
        """
        vectors = [Vector(v) for v in self.vertices]
        frames = []

        for face in self.faces:
            verts = [vectors[idx] for idx in face]
            normal = (verts[1] - verts[0]).cross(verts[2] - verts[0])
            if normal.length == 0:
                normal = Vector((0, 0, 1))
            normal.normalize()

            center = sum(verts, Vector((0, 0, 0))) / len(verts)
            if normal.dot(center) < 0:
                normal = -normal

            # Up points toward the apex (top or bottom) projected onto the face
            apex = max(verts, key=lambda v: abs(v.z))
            up_dir = apex - center
            up_dir = up_dir - normal * up_dir.dot(normal)
            if up_dir.length < 1e-8:
                up_dir = Vector((0, 1, 0))
            up_dir.normalize()

            right = up_dir.cross(normal)
            if right.length < 1e-8:
                right = Vector((1, 0, 0))
            right.normalize()

            frames.append({
                'center': center,
                'normal': normal,
                'up': up_dir,
                'right': right,
            })

        return frames

    def get_numbers(self):
        return numbers(self.num_faces)

    def get_number_locations(self):
        frames = self._face_frames()
        h_scale = self.number_h_offset * self.size / 4.0
        v_scale = self.number_v_offset * self.size / 4.0
        locations = []

        for frame in frames:
            base_pos = frame['center']
            pos = base_pos + frame['right'] * h_scale + frame['up'] * v_scale
            locations.append((pos.x, pos.y, pos.z))

        return locations

    def get_number_rotations(self):
        rotations = []
        for frame in self._face_frames():
            rot_matrix = Matrix((frame['right'], frame['up'], frame['normal'])).transposed()
            euler = rot_matrix.to_euler('XYZ')
            rotations.append((euler.x, euler.y, euler.z))
        return rotations


def numbers(n: int) -> List[str]:
    """
    Generate a list of number strings from 1 to n.

    Args:
        n: The count of numbers to generate

    Returns:
        List of string numbers from "1" to str(n)
    """
    return [str(i + 1) for i in range(n)]


def set_origin(o: bpy.types.Object, v: Vector) -> None:
    """
    Set the origin of an object to a specific location.

    Args:
        o: The Blender object to modify
        v: The new origin location as a Vector
    """
    me = o.data
    mw = o.matrix_world
    current = o.location
    T = Matrix.Translation(current - v)
    me.transform(T)
    mw.translation = mw @ v


def _calculate_bounds(vertices) -> Optional[Tuple[float, float, float, float, float, float]]:
    """
    Calculate the bounding box of a mesh's vertices.

    Args:
        vertices: Iterator or collection of mesh vertices

    Returns:
        Tuple of (min_x, max_x, min_y, max_y, min_z, max_z) or None if no vertices
    """
    iterator = iter(vertices)
    try:
        first_vertex = next(iterator)
    except StopIteration:
        return None

    min_x = max_x = first_vertex.co.x
    min_y = max_y = first_vertex.co.y
    min_z = max_z = first_vertex.co.z

    for v in iterator:
        x, y, z = v.co.x, v.co.y, v.co.z
        min_x = min(min_x, x)
        max_x = max(max_x, x)
        min_y = min(min_y, y)
        max_y = max(max_y, y)
        min_z = min(min_z, z)
        max_z = max(max_z, z)

    return min_x, max_x, min_y, max_y, min_z, max_z


def set_origin_center_bounds(o: bpy.types.Object) -> None:
    """
    Set an object's origin to the center of its bounding box.

    Args:
        o: The Blender object to modify
    """
    me = o.data
    bounds = _calculate_bounds(me.vertices)
    if bounds is None:
        return

    min_x, max_x, min_y, max_y, min_z, max_z = bounds
    set_origin(o, Vector(((min_x + max_x) / 2, (min_y + max_y) / 2, (min_z + max_z) / 2)))


def set_origin_min_bounds(o: bpy.types.Object) -> None:
    """
    Set an object's origin to the bottom-left corner of its bounding box.

    Args:
        o: The Blender object to modify
    """
    me = o.data
    bounds = _calculate_bounds(me.vertices)
    if bounds is None:
        return

    min_x, _, min_y, _, min_z, max_z = bounds
    set_origin(o, Vector((min_x, min_y, (min_z + max_z) / 2)))


def create_mesh(context, vertices: List[Tuple[float, float, float]],
                faces: List[List[int]], name: str) -> bpy.types.Object:
    """
    Create a Blender mesh object from vertices and faces.

    Args:
        context: Blender context
        vertices: List of vertex coordinates as (x, y, z) tuples
        faces: List of face definitions (each face is a list of vertex indices)
        name: Name for the mesh

    Returns:
        The created Blender object
    """
    verts = [Vector(i) for i in vertices]

    # Blender can handle n-gons directly, no need for createPolys
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    return object_data_add(context, mesh, operator=None)


def create_mesh_object(name: str,
                       vertices: List[Tuple[float, float, float]],
                       faces: List[List[int]],
                       collection: Optional[bpy.types.Collection] = None) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    target_collection = collection or bpy.context.collection or bpy.context.scene.collection
    target_collection.objects.link(obj)
    return obj


def rebuild_mesh_object(obj: bpy.types.Object,
                        vertices: List[Tuple[float, float, float]],
                        faces: List[List[int]]) -> None:
    if obj is None or obj.type != 'MESH':
        return

    old_mesh = obj.data
    materials = [material for material in old_mesh.materials]

    new_mesh = bpy.data.meshes.new(old_mesh.name)
    new_mesh.from_pydata(vertices, [], faces)
    new_mesh.update()
    for material in materials:
        new_mesh.materials.append(material)

    obj.data = new_mesh
    if old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)


def create_dice_collection(context, name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    parent_collection = context.collection if context.collection is not None else context.scene.collection
    parent_collection.children.link(collection)
    return collection


def get_dice_type_label(dice_type: str) -> str:
    labels = {
        'D4': 'D4',
        'D4_CRYSTAL': 'D4 Crystal',
        'D4_SHARD': 'D4 Shard',
        'D6': 'D6',
        'D8': 'D8',
        'D10': 'D10',
        'D12': 'D12',
        'D20': 'D20',
        'D100': 'D100',
        'CUSTOM_CRYSTAL': 'Custom Crystal',
        'CUSTOM_SHARD': 'Custom Shard',
        'CUSTOM_BIPYRAMID': 'Custom Bipyramid',
        'CUSTOM_TRAP': 'Custom Trapezohedron',
    }
    return labels.get(dice_type, dice_type.replace('_', ' ').title())


def move_object_to_collection(obj: Optional[bpy.types.Object], target_collection: bpy.types.Collection) -> None:
    if obj is None or target_collection is None:
        return

    if target_collection not in obj.users_collection:
        target_collection.objects.link(obj)

    for collection in list(obj.users_collection):
        if collection != target_collection:
            collection.objects.unlink(obj)


def organize_dice_objects_in_collection(body_object: bpy.types.Object,
                                        target_collection: bpy.types.Collection,
                                        extra_objects: Optional[List[Optional[bpy.types.Object]]] = None) -> None:
    if body_object is None or target_collection is None:
        return

    objects_to_move: List[Optional[bpy.types.Object]] = [body_object]

    numbers_name = body_object.get("dice_numbers_name")
    if numbers_name:
        objects_to_move.append(bpy.data.objects.get(numbers_name))

    critical_name = body_object.get("dice_critical_numbers_name")
    if critical_name:
        objects_to_move.append(bpy.data.objects.get(critical_name))

    fin_support_name = body_object.get(FIN_SUPPORT_OBJECT_KEY)
    if fin_support_name:
        objects_to_move.append(bpy.data.objects.get(fin_support_name))

    if extra_objects:
        objects_to_move.extend(extra_objects)

    seen = set()
    for obj in objects_to_move:
        if obj is None or obj.name in seen:
            continue
        seen.add(obj.name)
        move_object_to_collection(obj, target_collection)


def ensure_material(name: str, base_color: Tuple[float, float, float, float]) -> bpy.types.Material:
    """
    Create or retrieve a material with the specified name and color.

    Args:
        name: Name of the material
        base_color: RGBA color tuple (values 0.0-1.0)

    Returns:
        The material object
    """
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name=name)
    material.use_nodes = True
    if material.node_tree:
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = base_color
    return material


def assign_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    """
    Assign a material to an object, replacing any existing materials.

    Args:
        obj: The Blender object
        material: The material to assign
    """
    if obj.data.materials:
        obj.data.materials.clear()
    obj.data.materials.append(material)


def apply_transform(ob: bpy.types.Object, use_location: bool = False,
                    use_rotation: bool = False, use_scale: bool = False) -> None:
    """
    Apply transforms to an object at a low level without operators.

    Based on: https://blender.stackexchange.com/questions/159538/

    Args:
        ob: The object to transform
        use_location: Apply location transform
        use_rotation: Apply rotation transform
        use_scale: Apply scale transform
    """
    mb = ob.matrix_basis
    I = Matrix()
    loc, rot, scale = mb.decompose()

    # rotation
    T = Matrix.Translation(loc)
    # R = rot.to_matrix().to_4x4()
    R = mb.to_3x3().normalized().to_4x4()
    S = Matrix.Diagonal(scale).to_4x4()

    transform = [I, I, I]
    basis = [T, R, S]

    def swap(i):
        transform[i], basis[i] = basis[i], transform[i]

    if use_location:
        swap(0)
    if use_rotation:
        swap(1)
    if use_scale:
        swap(2)

    M = transform[0] @ transform[1] @ transform[2]
    if hasattr(ob.data, "transform"):
        ob.data.transform(M)
    for c in ob.children:
        c.matrix_local = M @ c.matrix_local

    ob.matrix_basis = basis[0] @ basis[1] @ basis[2]


def join(objects):
    """Join a list of objects into one and return the result."""
    if not objects:
        return None

    view_layer = bpy.context.view_layer

    # Deselect everything first
    for ob in view_layer.objects:
        ob.select_set(False)

    # Select the objects we want to join
    for ob in objects:
        ob.select_set(True)

    # Set the active object (the one that will remain after the join)
    view_layer.objects.active = objects[0]

    # Run the join operator in the current context
    bpy.ops.object.join()

    return objects[0]


FONT_EXTENSIONS = (".ttf", ".otf")


def validate_font_path(filepath: str) -> str:
    """
    Validate that a font file path exists and has a valid extension.

    Args:
        filepath: Path to the font file

    Returns:
        The filepath if valid, empty string otherwise
    """
    if not filepath:
        return ''

    if not os.path.isfile(filepath):
        return ''

    if os.path.splitext(filepath)[1].lower() not in FONT_EXTENSIONS:
        return ''

    return filepath


def validate_svg_path(filepath: str) -> str:
    """
    Validate that an SVG file path exists and has the .svg extension.

    Args:
        filepath: Path to the SVG file

    Returns:
        The filepath if valid, empty string otherwise
    """
    if not filepath:
        return ''

    if not os.path.isfile(filepath):
        return ''

    if os.path.splitext(filepath)[1].lower() != '.svg':
        return ''

    return filepath


def validate_dice_parameters(size: float, number_depth: float, number_scale: float) -> Tuple[bool, str]:
    """
    Validate dice generation parameters to ensure they produce valid geometry.

    Args:
        size: The face-to-face size of the die
        number_depth: Depth of number engravings
        number_scale: Scale of the numbers

    Returns:
        Tuple of (is_valid, error_message). error_message is empty if valid.
    """
    if size <= 0:
        return False, "Dice size must be greater than 0"

    if number_depth < 0:
        return False, "Number depth cannot be negative"

    if number_depth >= size / 2:
        return False, f"Number depth ({number_depth}) is too large for dice size ({size}). Should be less than {size/2}"

    if number_scale <= 0:
        return False, "Number scale must be greater than 0"

    return True, ""


SETTINGS_ATTRS = [
    "size",
    "dice_finish",
    "bumper_scale",
    "font_path",
    "number_scale",
    "number_depth",
    "add_fin_supports",
    "fin_support_contour_offset",
    "fin_support_connection_thickness",
    "fin_support_thickness",
    "fin_support_drop",
    "fin_support_raft_margin",
    "fin_support_raft_thickness",
    "fin_support_raft_taper",
    "add_numbers",
    "number_indicator_type",
    "period_indicator_scale",
    "period_indicator_space",
    "bar_indicator_height",
    "bar_indicator_width",
    "bar_indicator_space",
    "center_bar",
    "number_v_offset",
    "number_center_offset",
    "number_h_offset",
    "num_faces",
    "base_height",
    "point_height",
    "top_point_height",
    "bottom_point_height",
    "height",
    "custom_image_path",
    "custom_image_face",
    "custom_image_scale",
    "use_critical_face_material",
    "critical_face_material",
    "dot_indicator_scale",
    "dot_indicator_space",
]


def _sanitize_setting_value(value):
    """Convert RNA property arrays to plain Python tuples to avoid stale references."""
    if isinstance(value, str):
        return value
    if hasattr(value, '__iter__') and hasattr(value, '__len__'):
        try:
            return tuple(value)
        except TypeError:
            pass
    return value


def collect_settings_from_op(op, settings_template):
    return {
        attr: _sanitize_setting_value(getattr(op, attr, getattr(settings_template, attr)))
        for attr in SETTINGS_ATTRS
    }


def apply_settings(settings_obj, values):
    for key, value in values.items():
        setattr(settings_obj, key, value)


def snapshot_settings(settings_obj):
    return {attr: _sanitize_setting_value(getattr(settings_obj, attr)) for attr in SETTINGS_ATTRS}


def resolve_settings_owner(obj):
    if obj is None or not hasattr(obj, "dice_gen_settings"):
        return None

    body_name = obj.get("dice_body_name")
    if body_name and body_name in bpy.data.objects:
        body_obj = bpy.data.objects[body_name]
        if hasattr(body_obj, "dice_gen_settings") and body_obj.get("dice_gen_type") is not None:
            return body_obj

    if obj.get("dice_gen_type") is not None:
        return obj

    numbers_name = obj.get("dice_numbers_name")
    if numbers_name and numbers_name in bpy.data.objects:
        numbers_obj = bpy.data.objects[numbers_name]
        if numbers_obj.get("dice_gen_type") is not None:
            return numbers_obj

    return None


def get_font(filepath: str) -> bpy.types.VectorFont:
    """
    Load a font from a file path, falling back to Blender's default font if loading fails.

    Args:
        filepath: Path to the font file (TTF or OTF)

    Returns:
        The loaded font object
    """
    if filepath:
        try:
            bpy.data.fonts.load(filepath=filepath, check_existing=True)
            return next(filter(lambda x: x.filepath == filepath, bpy.data.fonts))
        except (RuntimeError, OSError) as e:
            print(f"Warning: Could not load font from '{filepath}': {e}. Using default font.")
        except StopIteration:
            print(f"Warning: Font loaded but not found in bpy.data.fonts: '{filepath}'. Using default font.")

    # Fall back to Blender's built-in font
    bpy.data.fonts.load(filepath='<builtin>', check_existing=True)
    return bpy.data.fonts[0]


def apply_boolean_modifier(body_object, numbers_object, modifier_name='boolean',
                           remember_key="dice_numbers_name", show_viewport=False):
    """
    Add a BOOLEAN modifier to body_object that targets
    :param context:
    :param body_object:
    :param numbers_object
    :return:
    """
    numbers_boolean = body_object.modifiers.new(type='BOOLEAN', name=modifier_name)
    numbers_boolean.object = bpy.data.objects[numbers_object.name]
    numbers_boolean.show_viewport = show_viewport
    if hasattr(numbers_boolean, "operation"):
        numbers_boolean.operation = 'DIFFERENCE'
    if hasattr(numbers_boolean, "solver"):
        # Prefer FLOAT when available; fallback to other supported solvers.
        for solver_name in ("FLOAT", "EXACT", "FAST"):
            try:
                numbers_boolean.solver = solver_name
                break
            except (TypeError, ValueError, AttributeError):
                continue

    if remember_key:
        body_object[remember_key] = numbers_object.name


def remove_object_if_exists(name: str) -> None:
    if not name:
        return

    obj = bpy.data.objects.get(name)
    if obj is None:
        return

    bpy.data.objects.remove(obj, do_unlink=True)


def remove_modifier_if_exists(obj: bpy.types.Object, modifier_name: str) -> None:
    if obj is None:
        return

    modifier = obj.modifiers.get(modifier_name)
    if modifier is not None:
        obj.modifiers.remove(modifier)


def clear_panel_artifacts(body_object: bpy.types.Object) -> None:
    if body_object is None:
        return

    remove_modifier_if_exists(body_object, PANEL_POCKET_BOOLEAN_NAME)
    remove_modifier_if_exists(body_object, PANEL_TOP_FACE_BOOLEAN_NAME)

    for key in (PANEL_OBJECT_KEY, PANEL_CUTTER_KEY, PANEL_NUMBER_CUTTER_KEY, PANEL_TOP_FACE_CUTTER_KEY):
        object_name = body_object.get(key)
        if object_name:
            remove_object_if_exists(object_name)
            del body_object[key]


def clear_fin_support_artifacts(body_object: bpy.types.Object) -> None:
    if body_object is None:
        return

    support_name = body_object.get(FIN_SUPPORT_OBJECT_KEY)
    if support_name:
        remove_object_if_exists(support_name)
        del body_object[FIN_SUPPORT_OBJECT_KEY]


def dedupe_loop_points(points: List[Vector], tolerance: float = 1e-5) -> List[Vector]:
    unique: List[Vector] = []
    for point in points:
        if not any((point - existing).length <= tolerance for existing in unique):
            unique.append(point.copy())
    return unique


def polygon_area_xy(points: List[Vector]) -> float:
    if len(points) < 3:
        return 0.0

    area = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area += point.x * next_point.y - next_point.x * point.y
    return area * 0.5


def offset_convex_loop(points: List[Vector], offset: float) -> List[Vector]:
    if len(points) < 3 or abs(offset) <= 1e-6:
        return [point.copy() for point in points]

    orientation = 1.0 if polygon_area_xy(points) >= 0 else -1.0
    offset_points: List[Vector] = []

    for index, point in enumerate(points):
        previous_point = points[index - 1]
        next_point = points[(index + 1) % len(points)]
        previous_edge = Vector((point.x - previous_point.x, point.y - previous_point.y, 0.0))
        next_edge = Vector((next_point.x - point.x, next_point.y - point.y, 0.0))

        if previous_edge.length <= 1e-6 or next_edge.length <= 1e-6:
            offset_points.append(point.copy())
            continue

        previous_edge.normalize()
        next_edge.normalize()

        if orientation > 0:
            previous_normal = Vector((previous_edge.y, -previous_edge.x, 0.0))
            next_normal = Vector((next_edge.y, -next_edge.x, 0.0))
        else:
            previous_normal = Vector((-previous_edge.y, previous_edge.x, 0.0))
            next_normal = Vector((-next_edge.y, next_edge.x, 0.0))

        miter = previous_normal + next_normal
        if miter.length <= 1e-6:
            offset_points.append(point + next_normal * offset)
            continue

        miter.normalize()
        scale = offset / max(miter.dot(next_normal), 0.2)
        offset_points.append(point + miter * scale)

    return offset_points


def build_fin_support_loop(vertices: List[Tuple[float, float, float]],
                           faces: List[List[int]],
                           plane_z: float,
                           fallback_band: float) -> List[Vector]:
    plane_points: List[Vector] = []
    epsilon = 1e-5

    for face in faces:
        face_points: List[Vector] = []
        for edge_index, start_index in enumerate(face):
            end_index = face[(edge_index + 1) % len(face)]
            start = Vector(vertices[start_index])
            end = Vector(vertices[end_index])
            start_distance = start.z - plane_z
            end_distance = end.z - plane_z

            if abs(start_distance) <= epsilon and abs(end_distance) <= epsilon:
                face_points.extend([start, end])
                continue

            if abs(start_distance) <= epsilon:
                face_points.append(start)
                continue

            if abs(end_distance) <= epsilon:
                face_points.append(end)
                continue

            if start_distance * end_distance < 0:
                factor = (plane_z - start.z) / (end.z - start.z)
                face_points.append(start.lerp(end, factor))

        plane_points.extend(dedupe_loop_points(face_points))

    plane_points = dedupe_loop_points(plane_points)

    if len(plane_points) < 3:
        band_limit = plane_z + max(fallback_band, 0.05)
        plane_points = dedupe_loop_points([
            Vector((vertex[0], vertex[1], plane_z))
            for vertex in vertices
            if vertex[2] <= band_limit
        ])

    if len(plane_points) < 3:
        return []

    center = sum(plane_points, Vector((0.0, 0.0, 0.0))) / len(plane_points)
    plane_points.sort(key=lambda point: math.atan2(point.y - center.y, point.x - center.x))

    if polygon_area_xy(plane_points) < 0:
        plane_points.reverse()

    return plane_points


def append_fin_segment(vertices: List[Tuple[float, float, float]],
                       faces: List[List[int]],
                       top_start: Vector,
                       top_end: Vector,
                       base_start: Vector,
                       base_end: Vector,
                       start_half_thickness: float,
                       end_half_thickness: float,
                       base_start_half_thickness: float,
                       base_end_half_thickness: float,
                       orientation_sign: float) -> None:
    edge = Vector((top_end.x - top_start.x, top_end.y - top_start.y, 0.0))
    if edge.length <= 1e-6:
        return

    edge.normalize()
    if orientation_sign >= 0:
        normal = Vector((edge.y, -edge.x, 0.0))
    else:
        normal = Vector((-edge.y, edge.x, 0.0))

    segment_vertices = [
        top_start + normal * start_half_thickness,
        top_end + normal * end_half_thickness,
        top_end - normal * end_half_thickness,
        top_start - normal * start_half_thickness,
        base_start + normal * base_start_half_thickness,
        base_end + normal * base_end_half_thickness,
        base_end - normal * base_end_half_thickness,
        base_start - normal * base_start_half_thickness,
    ]
    start = len(vertices)
    vertices.extend([(vertex.x, vertex.y, vertex.z) for vertex in segment_vertices])
    faces.extend([
        [start + 0, start + 1, start + 2, start + 3],
        [start + 4, start + 7, start + 6, start + 5],
        [start + 0, start + 4, start + 5, start + 1],
        [start + 1, start + 5, start + 6, start + 2],
        [start + 2, start + 6, start + 7, start + 3],
        [start + 3, start + 7, start + 4, start + 0],
    ])


def append_loop_prism(vertices: List[Tuple[float, float, float]],
                      faces: List[List[int]],
                      top_loop: List[Vector],
                      bottom_loop: List[Vector]) -> None:
    if len(top_loop) < 3 or len(top_loop) != len(bottom_loop):
        return

    start = len(vertices)
    vertices.extend([(vertex.x, vertex.y, vertex.z) for vertex in top_loop])
    vertices.extend([(vertex.x, vertex.y, vertex.z) for vertex in bottom_loop])

    count = len(top_loop)
    faces.append([start + index for index in range(count)])
    faces.append([start + count + index for index in reversed(range(count))])

    for index in range(count):
        next_index = (index + 1) % count
        faces.append([
            start + index,
            start + next_index,
            start + count + next_index,
            start + count + index,
        ])


def get_fin_support_edges(vertices: List[Tuple[float, float, float]],
                          faces: List[List[int]],
                          contour_height: float) -> Tuple[Optional[Vector], List[Vector]]:
    vertex_vectors = [Vector(vertex) for vertex in vertices]
    if not vertex_vectors:
        return None, []

    bottom_index = min(
        range(len(vertex_vectors)),
        key=lambda index: (
            vertex_vectors[index].z,
            vertex_vectors[index].x * vertex_vectors[index].x + vertex_vectors[index].y * vertex_vectors[index].y,
        ),
    )
    bottom_point = vertex_vectors[bottom_index]

    neighbor_indices = set()
    for face in faces:
        if bottom_index not in face:
            continue
        count = len(face)
        for index, vertex_index in enumerate(face):
            if vertex_index != bottom_index:
                continue
            neighbor_indices.add(face[(index - 1) % count])
            neighbor_indices.add(face[(index + 1) % count])

    edge_points: List[Vector] = []
    target_height = max(bottom_point.z + contour_height, bottom_point.z + 0.01)
    for neighbor_index in neighbor_indices:
        neighbor = vertex_vectors[neighbor_index]
        if neighbor.z <= bottom_point.z + 1e-6:
            continue
        factor = min(max((target_height - bottom_point.z) / (neighbor.z - bottom_point.z), 0.0), 1.0)
        edge_points.append(bottom_point.lerp(neighbor, factor))

    if len(edge_points) < 3:
        edge_points = [vertex_vectors[index] for index in neighbor_indices]

    if len(edge_points) < 3:
        return bottom_point, []

    edge_points = dedupe_loop_points(edge_points)
    edge_points.sort(key=lambda point: math.atan2(point.y - bottom_point.y, point.x - bottom_point.x))
    return bottom_point, edge_points


def get_fin_support_edge_limit(vertices: List[Tuple[float, float, float]],
                               faces: List[List[int]]) -> float:
    vertex_vectors = [Vector(vertex) for vertex in vertices]
    if not vertex_vectors:
        return 0.0

    bottom_index = min(
        range(len(vertex_vectors)),
        key=lambda index: (
            vertex_vectors[index].z,
            vertex_vectors[index].x * vertex_vectors[index].x + vertex_vectors[index].y * vertex_vectors[index].y,
        ),
    )
    bottom_point = vertex_vectors[bottom_index]

    max_length = 0.0
    for face in faces:
        if bottom_index not in face:
            continue
        count = len(face)
        for index, vertex_index in enumerate(face):
            if vertex_index != bottom_index:
                continue
            for neighbor_index in (face[(index - 1) % count], face[(index + 1) % count]):
                neighbor = vertex_vectors[neighbor_index]
                max_length = max(max_length, (neighbor - bottom_point).length)

    return max_length


def generate_fin_supports(context,
                          body_object: bpy.types.Object,
                          mesh_vertices: List[Tuple[float, float, float]],
                          mesh_faces: List[List[int]],
                          settings_values: Dict[str, Any]) -> Optional[bpy.types.Object]:
    clear_fin_support_artifacts(body_object)

    if not settings_values.get("add_fin_supports", False):
        return None

    edge_limit = get_fin_support_edge_limit(mesh_vertices, mesh_faces)
    contour_offset = max(settings_values.get("fin_support_contour_offset", 0.6), 0.05)
    if edge_limit > 0:
        contour_offset = min(contour_offset, edge_limit)
    connection_thickness = max(settings_values.get("fin_support_connection_thickness", 0.5), 0.1)
    fin_thickness = max(settings_values.get("fin_support_thickness", 2.0), 0.1)
    fin_drop = max(settings_values.get("fin_support_drop", 6.0), 0.25)
    raft_margin = max(settings_values.get("fin_support_raft_margin", 2.0), 0.0)
    raft_thickness = max(settings_values.get("fin_support_raft_thickness", 1.2), 0.0)
    raft_taper = max(settings_values.get("fin_support_raft_taper", 0.8), 0.0)

    bottom_point, edge_points = get_fin_support_edges(mesh_vertices, mesh_faces, contour_offset)
    if bottom_point is None or len(edge_points) < 3:
        return None

    mesh_center = sum((Vector(vertex) for vertex in mesh_vertices), Vector((0.0, 0.0, 0.0))) / len(mesh_vertices)

    def body_overlap_point(point: Vector) -> Vector:
        inward = mesh_center - point
        if inward.length <= 1e-6:
            return point.copy()
        return point + inward.normalized() * FIN_SUPPORT_BODY_INTERSECTION

    overlapped_bottom_point = body_overlap_point(bottom_point)
    bottom_projection = Vector((overlapped_bottom_point.x, overlapped_bottom_point.y, 0.0))
    raft_top_z = 0.0
    raft_bottom_z = -raft_thickness
    raft_seed = [Vector((point.x, point.y, raft_top_z)) for point in edge_points]
    raft_loop = offset_convex_loop(raft_seed, raft_margin)
    raft_bottom_loop = offset_convex_loop(raft_loop, -raft_taper) if raft_taper > 0 else [point.copy() for point in raft_loop]
    if len(raft_bottom_loop) != len(raft_loop) or abs(polygon_area_xy(raft_bottom_loop)) <= 1e-6:
        raft_bottom_loop = [point.copy() for point in raft_loop]

    support_vertices: List[Tuple[float, float, float]] = []
    support_faces: List[List[int]] = []
    orientation_sign = 1.0 if polygon_area_xy(edge_points) >= 0 else -1.0
    connection_half_thickness = connection_thickness * 0.5
    edge_half_thickness = fin_thickness * 0.5

    for edge_point in edge_points:
        top_point = body_overlap_point(edge_point)
        base_point = Vector((top_point.x, top_point.y, raft_top_z))
        append_fin_segment(
            support_vertices,
            support_faces,
            overlapped_bottom_point,
            top_point,
            bottom_projection,
            base_point,
            connection_half_thickness,
            connection_half_thickness,
            edge_half_thickness,
            edge_half_thickness,
            orientation_sign,
        )

    if raft_thickness > 0 and len(raft_loop) >= 3:
        append_loop_prism(
            support_vertices,
            support_faces,
            raft_loop,
            [Vector((point.x, point.y, raft_bottom_z)) for point in raft_bottom_loop],
        )

    if not support_vertices or not support_faces:
        return None

    collection = body_object.users_collection[0] if body_object.users_collection else context.collection
    support_name = f"{body_object.name}_fin_supports"
    support_object = create_mesh_object(support_name, support_vertices, support_faces, collection)
    support_object.parent = body_object
    support_object.matrix_parent_inverse = Matrix.Identity(4)
    support_object["dice_body_name"] = body_object.name
    support_material = ensure_material("Dice Supports", (0.78, 0.88, 0.48, 1.0))
    assign_material(support_object, support_material)
    body_object[FIN_SUPPORT_OBJECT_KEY] = support_object.name
    return support_object


@contextmanager
def ensure_object_mode(active_obj):
    """Temporarily switch to OBJECT mode for mesh edits and restore the prior mode."""
    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active
    previous_mode = active_obj.mode if active_obj else None

    try:
        if active_obj and view_layer.objects.active != active_obj:
            view_layer.objects.active = active_obj

        if active_obj and active_obj.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                pass

        yield
    finally:
        if active_obj and previous_mode and previous_mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode=previous_mode)
            except RuntimeError:
                pass

        if previous_active and previous_active != view_layer.objects.active:
            view_layer.objects.active = previous_active


def apply_bumpers_to_mesh(mesh_data, bumper_scale):
    inset_amount = 0.4 * bumper_scale
    extrude_amount = inset_amount * (0.5 / 0.3)

    if inset_amount <= 0 and extrude_amount <= 0:
        return

    bm = bmesh.new()
    bm.from_mesh(mesh_data)

    if not bm.faces:
        bm.free()
        return

    for face in bm.faces:
        face.tag = True

    inset_result = bmesh.ops.inset_individual(
        bm,
        faces=list(bm.faces),
        thickness=inset_amount,
        depth=0.0,
        use_even_offset=True,
    )

    inset_faces = list(inset_result.get("faces", []))

    # After the inset operation, Blender reports the new rim faces in
    # the "faces" result, while the original faces remain as the inset
    # centers. We want the raised bumper on the rim, so operate on the
    # inset result directly instead of inverting the set.
    rim_faces = inset_faces

    if extrude_amount > 0 and rim_faces:
        bm.normal_update()
        rim_verts = set()

        for face in rim_faces:
            rim_verts.update(face.verts)

        extrude_result = bmesh.ops.extrude_face_region(bm, geom=rim_faces)
        extruded_geom = extrude_result.get("geom", [])
        extruded_verts = [
            ele for ele in extruded_geom
            if isinstance(ele, bmesh.types.BMVert) and ele not in rim_verts
        ]

        if extruded_verts:
            bm.normal_update()
            for vert in extruded_verts:
                if vert.normal.length > 0:
                    vert.co += vert.normal.normalized() * extrude_amount

    bm.normal_update()
    bm.to_mesh(mesh_data)
    bm.free()


def configure_dice_finish_modifier(body_object, dice_finish, bumper_scale=1):
    if body_object is None or body_object.type != 'MESH':
        return

    with ensure_object_mode(body_object):
        modifier_name = "dice_bevel"
        bevel_modifier = body_object.modifiers.get(modifier_name)
        bumper_base_key = "dice_base_mesh_name"

        if dice_finish != "bumpers":
            base_mesh_name = body_object.get(bumper_base_key)
            if base_mesh_name and base_mesh_name in bpy.data.meshes:
                base_mesh = bpy.data.meshes[base_mesh_name]
                if body_object.data != base_mesh:
                    previous_mesh = body_object.data
                    body_object.data = base_mesh.copy()
                    if previous_mesh.users == 0 and previous_mesh != base_mesh:
                        bpy.data.meshes.remove(previous_mesh)

                base_mesh.use_fake_user = False
                if base_mesh.users == 0:
                    bpy.data.meshes.remove(base_mesh)

                if bumper_base_key in body_object:
                    del body_object[bumper_base_key]

        if dice_finish == "bumpers":
            if bevel_modifier:
                body_object.modifiers.remove(bevel_modifier)

            base_mesh = None
            base_mesh_name = body_object.get(bumper_base_key)

            if base_mesh_name and base_mesh_name in bpy.data.meshes:
                base_mesh = bpy.data.meshes[base_mesh_name]
            else:
                base_mesh = body_object.data.copy()
                base_mesh.use_fake_user = True
                body_object[bumper_base_key] = base_mesh.name

            working_mesh = base_mesh.copy()
            apply_bumpers_to_mesh(working_mesh, bumper_scale)

            previous_mesh = body_object.data
            body_object.data = working_mesh

            if previous_mesh not in (base_mesh, working_mesh) and previous_mesh.users == 0:
                bpy.data.meshes.remove(previous_mesh)

            return

        if dice_finish == "sharp":
            if bevel_modifier:
                body_object.modifiers.remove(bevel_modifier)
            return

        if bevel_modifier is None:
            bevel_modifier = body_object.modifiers.new(type='BEVEL', name=modifier_name)

        bevel_modifier.limit_method = 'NONE'
        bevel_modifier.use_clamp_overlap = False
        bevel_modifier.width = 0.3
        bevel_modifier.segments = 1 if dice_finish == "chamfer" else 5

        if hasattr(bevel_modifier, "affect"):
            bevel_modifier.affect = 'EDGES'


def create_svg_mesh(context, filepath, scale, depth, name):
    existing_objects = set(bpy.data.objects)
    existing_collections = set(bpy.data.collections)
    new_collections = []

    try:
        bpy.ops.import_curve.svg(filepath=filepath)
    except (RuntimeError, OSError):
        return None

    new_collections = [col for col in bpy.data.collections if col not in existing_collections]
    imported_objects = [ob for ob in bpy.data.objects if ob not in existing_objects]
    imported_object_names = [ob.name for ob in imported_objects]
    curve_object_names = [ob.name for ob in imported_objects if ob.type == 'CURVE']
    curve_objects = [bpy.data.objects[name] for name in curve_object_names if name in bpy.data.objects]

    def cleanup_new_collections():
        for collection in new_collections:
            if collection.objects or collection.children:
                continue

            for parent in bpy.data.collections:
                if parent.children.get(collection.name):
                    parent.children.unlink(collection)

            for scene in bpy.data.scenes:
                if scene.collection.children.get(collection.name):
                    scene.collection.children.unlink(collection)

            try:
                bpy.data.collections.remove(collection)
            except RuntimeError:
                # If the collection still has users for any reason, skip removal
                pass

    if not curve_objects:
        for obj_name in imported_object_names:
            if obj_name in bpy.data.objects:
                bpy.data.objects.remove(bpy.data.objects[obj_name], do_unlink=True)
        cleanup_new_collections()
        return None

    mesh_objects = []
    for curve_obj in curve_objects:
        curve_obj.data.materials.clear()
        if hasattr(curve_obj.data, "color_attributes"):
            for color_attr in list(curve_obj.data.color_attributes):
                curve_obj.data.color_attributes.remove(color_attr)

        curve_obj.data.extrude = depth

        mesh = curve_obj.to_mesh().copy()
        mesh.materials.clear()
        if hasattr(mesh, "color_attributes"):
            for color_attr in list(mesh.color_attributes):
                mesh.color_attributes.remove(color_attr)
        new_obj = object_data_add(context, mesh, operator=None)
        mesh_objects.append(new_obj)

    for curve_name in curve_object_names:
        if curve_name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[curve_name], do_unlink=True)

    if not mesh_objects:
        cleanup_new_collections()
        return None

    for obj_name in imported_object_names:
        if obj_name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[obj_name], do_unlink=True)

    cleanup_new_collections()

    svg_mesh = join(mesh_objects)
    svg_mesh.name = name

    current_dimension = max(svg_mesh.dimensions.x, svg_mesh.dimensions.y)
    current_dimension = current_dimension if current_dimension else 1
    uniform_scale = scale / current_dimension
    svg_mesh.scale = (uniform_scale, uniform_scale, 1)

    apply_transform(svg_mesh, use_scale=True)
    return svg_mesh


def create_text_mesh(context, text: str, font_path: str, font_size: float,
                     name: str, extrude: float = 0) -> bpy.types.Object:
    """
    Create a mesh object from text using a font.

    Args:
        context: Blender context
        text: Text string to create
        font_path: Path to font file (TTF or OTF)
        font_size: Size of the font
        name: Name for the created object
        extrude: Extrusion depth for 3D text

    Returns:
        The created mesh object
    """
    # load the font
    font = get_font(font_path)

    # create the text curve
    font_curve = bpy.data.curves.new(type='FONT', name=name)
    font_curve.body = text
    font_curve.font = font
    font_curve.size = font_size
    font_curve.extrude = extrude
    font_curve.offset = 0

    # create object from curve
    curve_obj = bpy.data.objects.new('temp_curve_obj', font_curve)

    # convert curve to mesh
    mesh = curve_obj.to_mesh().copy()
    curve_obj.to_mesh_clear()
    bpy.data.objects.remove(curve_obj)
    bpy.data.curves.remove(font_curve)
    return object_data_add(context, mesh, operator=None)


def add_period_indicator(context, mesh_object: bpy.types.Object, number: str,
                         font_path: str, font_size: float, number_depth: float,
                         period_indicator_scale: float, period_indicator_space: float) -> bpy.types.Object:
    """
    Add a period indicator to numbers 6 and 9 for orientation.

    Args:
        context: Blender context
        mesh_object: The number mesh to add indicator to
        number: The number string ('6' or '9')
        font_path: Path to font file
        font_size: Base font size
        number_depth: Depth of the number extrusion
        period_indicator_scale: Scale factor for the period
        period_indicator_space: Spacing between number and period

    Returns:
        The combined mesh object with period indicator
    """
    p_obj = create_text_mesh(context, '.', font_path, font_size * period_indicator_scale,
                            f'period_{number}', number_depth)

    # move origin of period to the bottom left corner of the mesh
    set_origin_min_bounds(p_obj)

    space = (1 / 20) * font_size * period_indicator_space

    # move period to the bottom right of the number
    p_obj.location = Vector((mesh_object.location.x + (mesh_object.dimensions.x / 2) + space,
                             mesh_object.location.y - (mesh_object.dimensions.y / 2), 0))

    # join the period to the number
    return join([mesh_object, p_obj])


def add_bar_indicator(context, mesh_object: bpy.types.Object, font_size: float,
                      number_depth: float, bar_indicator_height: float,
                      bar_indicator_width: float, bar_indicator_space: float,
                      center_bar: bool) -> bpy.types.Object:
    """
    Add a bar indicator to numbers 6 and 9 for orientation.

    Args:
        context: Blender context
        mesh_object: The number mesh to add indicator to
        font_size: Base font size
        number_depth: Depth of the number extrusion
        bar_indicator_height: Height scale of the bar
        bar_indicator_width: Width scale of the bar
        bar_indicator_space: Spacing between number and bar
        center_bar: Whether to center-align the bar with the number

    Returns:
        The combined mesh object with bar indicator
    """
    # create a simple rectangle
    bar_width = mesh_object.dimensions.x * bar_indicator_width
    bar_height = (1 / 15) * font_size * bar_indicator_height
    bar_space = (1 / 20) * font_size * bar_indicator_space
    bar_obj = create_mesh(context,
                          [(-bar_width / 2, -bar_space, number_depth),
                           (bar_width / 2, -bar_space, number_depth),
                           (-bar_width / 2, -bar_space - bar_height, number_depth),
                           (bar_width / 2, -bar_space - bar_height, number_depth),
                           (-bar_width / 2, -bar_space, -number_depth),
                           (bar_width / 2, -bar_space, -number_depth),
                           (-bar_width / 2, -bar_space - bar_height, -number_depth),
                           (bar_width / 2, -bar_space - bar_height, -number_depth)],
                          [[0, 1, 3, 2], [2, 3, 7, 6], [3, 1, 5, 7], [1, 0, 4, 5], [0, 2, 6, 4], [4, 6, 7, 5]],
                          'bar_indicator')

    # move bar below the number
    bar_obj.location = Vector(
        (mesh_object.location.x, mesh_object.location.y - (mesh_object.dimensions.y / 2), 0))

    # join the bar to the number
    mesh_object = join([mesh_object, bar_obj])

    # recenter the mesh
    if center_bar:
        mesh_object.location = Vector((0, 0, 0))
        set_origin_center_bounds(mesh_object)

    return mesh_object


def add_dot_indicator(context, mesh_object: bpy.types.Object, font_size: float,
                      number_depth: float, dot_indicator_scale: float,
                      dot_indicator_space: float) -> bpy.types.Object:
    """
    Add a small dot indicator below numbers 6 and 9 for orientation.

    Args:
        context: Blender context
        mesh_object: The number mesh to add indicator to
        font_size: Base font size
        number_depth: Depth of the number extrusion
        dot_indicator_scale: Scale factor for the dot
        dot_indicator_space: Spacing between number and dot

    Returns:
        The combined mesh object with dot indicator
    """
    dot_diameter = (1 / 12) * font_size * dot_indicator_scale
    dot_space = (1 / 20) * font_size * dot_indicator_space

    # Create a small cylinder (octagon prism) as mesh for boolean cutting
    radius = dot_diameter / 2
    segments = 8
    verts = []
    faces = []

    # Top circle at +number_depth
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        verts.append((radius * math.cos(angle), radius * math.sin(angle), number_depth))

    # Bottom circle at -number_depth
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        verts.append((radius * math.cos(angle), radius * math.sin(angle), -number_depth))

    # Top face
    faces.append(list(range(segments)))
    # Bottom face (reversed winding)
    faces.append(list(range(2 * segments - 1, segments - 1, -1)))
    # Side faces
    for i in range(segments):
        next_i = (i + 1) % segments
        faces.append([i, next_i, next_i + segments, i + segments])

    dot_obj = create_mesh(context, verts, faces, 'dot_indicator')

    # Position dot centered below the number
    dot_obj.location = Vector((
        mesh_object.location.x,
        mesh_object.location.y - (mesh_object.dimensions.y / 2) - dot_space - radius,
        0
    ))

    # Join dot to number
    return join([mesh_object, dot_obj])


def create_numbers(context, numbers, locations, rotations, font_path, font_size, number_depth, number_indicator_type,
                   period_indicator_scale, period_indicator_space, bar_indicator_height, bar_indicator_width,
                   bar_indicator_space, center_bar, custom_image_face=0, custom_image_path='',
                   custom_image_scale=1, original_indices=None,
                   material_name="Dice Numbers", material_color=(0, 0, 0, 1),
                   dot_indicator_scale=1, dot_indicator_space=1):
    number_objs = []
    # create the number meshes
    for i in range(len(locations)):
        index_value = original_indices[i] if original_indices and i < len(original_indices) else i
        number_object = create_number(context, numbers[i], font_path, font_size, number_depth, locations[i],
                                      rotations[i], number_indicator_type, period_indicator_scale,
                                      period_indicator_space, bar_indicator_height, bar_indicator_width,
                                      bar_indicator_space, center_bar,
                                      custom_image_face=custom_image_face, custom_image_path=custom_image_path,
                                      custom_image_scale=custom_image_scale, index=index_value,
                                      dot_indicator_scale=dot_indicator_scale,
                                      dot_indicator_space=dot_indicator_space)
        number_objs.append(number_object)

    # join the numbers into a single object
    if len(number_objs):
        numbers = join(number_objs)
        apply_transform(numbers, use_rotation=True, use_location=True)
        numbers_material = ensure_material(material_name, tuple(material_color))
        assign_material(numbers, numbers_material)
        return numbers

    return None


def create_number(context, number, font_path, font_size, number_depth, location, rotation, number_indicator_type,
                  period_indicator_scale, period_indicator_space, bar_indicator_height, bar_indicator_width,
                  bar_indicator_space, center_bar, custom_image_face=0, custom_image_path='',
                  custom_image_scale=1, index=0,
                  dot_indicator_scale=1, dot_indicator_space=1):
    """
    Create a number mesh that will be used in a boolean modifier
    """
    use_custom_image = custom_image_path and (custom_image_face == index + 1)

    mesh_object = None

    if use_custom_image:
        mesh_object = create_svg_mesh(context, custom_image_path, font_size * custom_image_scale, number_depth,
                                      f'custom_image_{index + 1}')

    if mesh_object is None:
        # add number
        mesh_object = create_text_mesh(context, number, font_path, font_size, f'number_{number}', number_depth)

    # set origin to bounding box center
    set_origin_center_bounds(mesh_object)

    if not use_custom_image:
        if number in ('6', '9'):
            # Add orientation indicators for 6 and 9
            if number_indicator_type == NUMBER_IND_PERIOD:
                mesh_object = add_period_indicator(context, mesh_object, number, font_path, font_size,
                                                   number_depth, period_indicator_scale, period_indicator_space)
            elif number_indicator_type == NUMBER_IND_BAR:
                mesh_object = add_bar_indicator(context, mesh_object, font_size, number_depth,
                                                bar_indicator_height, bar_indicator_width,
                                                bar_indicator_space, center_bar)
            elif number_indicator_type == NUMBER_IND_DOT:
                mesh_object = add_dot_indicator(context, mesh_object, font_size, number_depth,
                                                dot_indicator_scale, dot_indicator_space)

    mesh_object.location.x = location[0]
    mesh_object.location.y = location[1]
    mesh_object.location.z = location[2]

    mesh_object.rotation_euler.x = rotation[0]
    mesh_object.rotation_euler.y = rotation[1]
    mesh_object.rotation_euler.z = rotation[2]

    for f in mesh_object.data.polygons:
        f.use_smooth = False

    return mesh_object


def _normalize_die_type(dice_type: str) -> str:
    """Map internal class names or operator enum values to a canonical type string."""
    class_map = {
        'Tetrahedron': 'D4',
        'D4Crystal': 'D4_CRYSTAL',
        'D4Shard': 'D4_SHARD',
        'Cube': 'D6',
        'Octahedron': 'D8',
        'D10Mesh': 'D10',
        'D100Mesh': 'D100',
        'Dodecahedron': 'D12',
        'Icosahedron': 'D20',
        'CustomCrystal': 'CUSTOM_CRYSTAL',
        'CustomShard': 'CUSTOM_SHARD',
        'CustomBipyramid': 'CUSTOM_BIPYRAMID',
        'CustomTrapezohedron': 'CUSTOM_TRAP',
    }
    return class_map.get(dice_type, dice_type)


def supports_number_indicators(dice_type: str, num_faces: int) -> bool:
    """
    Return True only for dice types that contain both '6' and '9' faces,
    since orientation indicators exist solely to disambiguate those two values.
    """
    t = _normalize_die_type(dice_type)
    # Standard dice that have both 6 and 9 in their number range
    if t in ['D10', 'D12', 'D20', 'D100']:
        return True
    # Custom dice generate numbers 1..num_faces, so we need at least 9 faces
    # to guarantee both 6 and 9 exist.
    if t in ['CUSTOM_TRAP', 'CUSTOM_CRYSTAL', 'CUSTOM_SHARD', 'CUSTOM_BIPYRAMID']:
        return num_faces >= 9
    return False


def _polygon_area_2d(points: List[Vector]) -> float:
    area = 0.0
    count = len(points)
    for i in range(count):
        p1 = points[i]
        p2 = points[(i + 1) % count]
        area += (p1.x * p2.y) - (p2.x * p1.y)
    return area * 0.5


def _cross_2d(a: Vector, b: Vector) -> float:
    return a.x * b.y - a.y * b.x


def _line_intersection_2d(p1: Vector, d1: Vector, p2: Vector, d2: Vector) -> Optional[Vector]:
    denom = _cross_2d(d1, d2)
    if abs(denom) < 1e-9:
        return None

    diff = p2 - p1
    t = _cross_2d(diff, d2) / denom
    return p1 + d1 * t


def _inset_convex_polygon_2d(points: List[Vector], inset: float) -> Optional[List[Vector]]:
    if len(points) < 3:
        return None

    points_2d = [Vector((p.x, p.y)) for p in points]
    if _polygon_area_2d(points_2d) < 0:
        points_2d.reverse()

    inset_points: List[Vector] = []
    count = len(points_2d)

    for i in range(count):
        prev_point = points_2d[(i - 1) % count]
        current_point = points_2d[i]
        next_point = points_2d[(i + 1) % count]

        prev_edge = current_point - prev_point
        next_edge = next_point - current_point

        if prev_edge.length < 1e-8 or next_edge.length < 1e-8:
            return None

        prev_dir = prev_edge.normalized()
        next_dir = next_edge.normalized()

        prev_normal = Vector((-prev_dir.y, prev_dir.x))
        next_normal = Vector((-next_dir.y, next_dir.x))

        prev_shifted = current_point + prev_normal * inset
        next_shifted = current_point + next_normal * inset

        intersection = _line_intersection_2d(prev_shifted, prev_dir, next_shifted, next_dir)
        if intersection is None:
            bisector = prev_normal + next_normal
            if bisector.length < 1e-8:
                return None
            bisector.normalize()
            denom = bisector.dot(prev_normal)
            if abs(denom) < 1e-8:
                return None
            intersection = current_point + bisector * (inset / denom)

        inset_points.append(intersection)

    if abs(_polygon_area_2d(inset_points)) < 1e-6:
        return None

    return inset_points


def _append_face_prism(vertices_out: List[Tuple[float, float, float]],
                       faces_out: List[List[int]],
                       polygon_2d: List[Vector],
                       center: Vector,
                       face_right: Vector,
                       face_up: Vector,
                       face_normal: Vector,
                       top_offset: float,
                       bottom_offset: float) -> None:
    count = len(polygon_2d)
    base_index = len(vertices_out)

    for point in polygon_2d:
        base_3d = center + face_right * point.x + face_up * point.y
        top_vertex = base_3d + (face_normal * top_offset)
        vertices_out.append((top_vertex.x, top_vertex.y, top_vertex.z))

    for point in polygon_2d:
        base_3d = center + face_right * point.x + face_up * point.y
        bottom_vertex = base_3d + (face_normal * bottom_offset)
        vertices_out.append((bottom_vertex.x, bottom_vertex.y, bottom_vertex.z))

    top_face = [base_index + i for i in range(count)]
    bottom_face = [base_index + count + i for i in range(count)]
    faces_out.append(top_face)
    faces_out.append(list(reversed(bottom_face)))

    for i in range(count):
        next_i = (i + 1) % count
        faces_out.append([
            base_index + i,
            base_index + next_i,
            base_index + count + next_i,
            base_index + count + i
        ])


def create_face_panels(context,
                       source_vertices: List[Tuple[float, float, float]],
                       source_faces: List[List[int]],
                       panel_edge_inset: float,
                       panel_tolerance: float,
                       panel_thickness: float,
                       panel_recess_depth: float,
                       skip_face_index: int = 0) -> Tuple[Optional[bpy.types.Object], Optional[bpy.types.Object]]:
    if not source_vertices or not source_faces:
        return None, None

    panel_vertices: List[Tuple[float, float, float]] = []
    panel_faces: List[List[int]] = []
    cutter_vertices: List[Tuple[float, float, float]] = []
    cutter_faces: List[List[int]] = []

    vectors = [Vector(v) for v in source_vertices]

    safe_tolerance = max(panel_tolerance, 0.0)
    safe_recess_depth = max(panel_recess_depth, 0.05)
    safe_thickness = max(min(panel_thickness, safe_recess_depth), 0.05)
    panel_top_inset = safe_recess_depth - safe_thickness
    panel_inset = max(panel_edge_inset + safe_tolerance, 0.01)
    pocket_inset = max(panel_edge_inset, 0.01)
    pocket_depth = safe_recess_depth + safe_tolerance

    for face_idx, face in enumerate(source_faces, start=1):
        if skip_face_index and face_idx == skip_face_index:
            continue

        if len(face) < 3:
            continue

        face_vertices = [vectors[index] for index in face]
        center = sum(face_vertices, Vector((0, 0, 0))) / len(face_vertices)

        normal = (face_vertices[1] - face_vertices[0]).cross(face_vertices[2] - face_vertices[0])
        if normal.length < 1e-8:
            continue

        normal.normalize()
        if normal.dot(center) < 0:
            normal = -normal

        right = face_vertices[1] - face_vertices[0]
        right -= normal * right.dot(normal)
        if right.length < 1e-8:
            right = face_vertices[2] - face_vertices[0]
            right -= normal * right.dot(normal)
        if right.length < 1e-8:
            continue
        right.normalize()

        up = normal.cross(right)
        if up.length < 1e-8:
            continue
        up.normalize()

        face_2d = []
        for vert in face_vertices:
            local = vert - center
            face_2d.append(Vector((local.dot(right), local.dot(up))))

        pocket_poly = _inset_convex_polygon_2d(face_2d, pocket_inset)
        panel_poly = _inset_convex_polygon_2d(face_2d, panel_inset)
        if pocket_poly is None or panel_poly is None:
            continue

        _append_face_prism(
            panel_vertices,
            panel_faces,
            panel_poly,
            center,
            right,
            up,
            normal,
            -panel_top_inset,
            -(panel_top_inset + safe_thickness),
        )

        _append_face_prism(
            cutter_vertices,
            cutter_faces,
            pocket_poly,
            center,
            right,
            up,
            normal,
            0.05,
            -pocket_depth,
        )

    if not panel_faces or not cutter_faces:
        return None, None

    panel_object = create_mesh(context, panel_vertices, panel_faces, "dice_face_panels")
    panel_object.matrix_world = Matrix()
    panel_material = ensure_material("Dice Panels", (0.95, 0.95, 0.95, 1))
    assign_material(panel_object, panel_material)

    cutter_object = create_mesh(context, cutter_vertices, cutter_faces, "dice_panel_cutter")
    cutter_object.matrix_world = Matrix()
    cutter_object.display_type = 'WIRE'
    cutter_object.hide_render = True
    cutter_object.hide_set(True)

    return panel_object, cutter_object


def offset_number_locations_for_panels(locations: List[Tuple[float, float, float]],
                                       rotations: List[Tuple[float, float, float]],
                                       panel_thickness: float,
                                       panel_recess_depth: float) -> List[Tuple[float, float, float]]:
    safe_recess_depth = max(panel_recess_depth, 0.0)
    safe_thickness = max(min(panel_thickness, safe_recess_depth), 0.0)
    inset_distance = (safe_recess_depth - safe_thickness) + (safe_thickness * 0.5)

    shifted_locations: List[Tuple[float, float, float]] = []

    for location, rotation in zip(locations, rotations):
        loc_vec = Vector(location)
        normal = Euler(rotation, 'XYZ').to_matrix() @ Vector((0, 0, 1))
        if normal.length < 1e-8:
            normal = loc_vec.normalized() if loc_vec.length > 1e-8 else Vector((0, 0, 1))
        else:
            normal.normalize()

        if loc_vec.length > 1e-8 and normal.dot(loc_vec) < 0:
            normal = -normal

        shifted = loc_vec - normal * inset_distance
        shifted_locations.append((shifted.x, shifted.y, shifted.z))

    return shifted_locations


def _parse_face_value(value_text: str) -> Optional[int]:
    text = str(value_text).strip()
    cleaned = re.sub(r"[^0-9\-]", "", text)
    if cleaned in ("", "-"):
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def get_number_face_indices(mesh: Mesh) -> List[int]:
    numbers = mesh.get_numbers()
    locations = mesh.get_number_locations()
    faces = mesh.faces or []
    vertices = mesh.vertices or []

    if not numbers or not locations or not faces or not vertices:
        return []

    vectors = [Vector(v) for v in vertices]
    face_frames: List[Tuple[int, Vector, Vector]] = []

    for face_idx, face in enumerate(faces, start=1):
        if len(face) < 3:
            continue

        face_vertices = [vectors[idx] for idx in face]
        center = sum(face_vertices, Vector((0, 0, 0))) / len(face_vertices)

        normal = (face_vertices[1] - face_vertices[0]).cross(face_vertices[2] - face_vertices[0])
        if normal.length < 1e-8:
            continue

        normal.normalize()
        # Keep a stable outward-ish normal for distance tests.
        if center.length > 1e-8 and normal.dot(center) < 0:
            normal = -normal

        face_frames.append((face_idx, center, normal))

    if not face_frames:
        return []

    mapping: List[int] = []

    for location in locations:
        loc_vec = Vector(location)
        best_face_idx = 0
        best_plane_distance = float("inf")
        best_center_distance = float("inf")

        for face_idx, center, normal in face_frames:
            plane_distance = abs((loc_vec - center).dot(normal))
            center_distance = (loc_vec - center).length

            if (
                plane_distance < best_plane_distance - 1e-6
                or (
                    abs(plane_distance - best_plane_distance) <= 1e-6
                    and center_distance < best_center_distance
                )
            ):
                best_plane_distance = plane_distance
                best_center_distance = center_distance
                best_face_idx = face_idx

        mapping.append(best_face_idx)

    return mapping


def get_number_indices_for_face(mesh: Mesh, face_index: int) -> List[int]:
    if face_index <= 0:
        return []

    mapped_faces = get_number_face_indices(mesh)
    if mapped_faces:
        return [idx for idx, mapped_face in enumerate(mapped_faces) if mapped_face == face_index]

    numbers_count = len(mesh.get_numbers())
    face_count = len(mesh.faces) if mesh.faces else 0
    if numbers_count <= 0 or face_count <= 0:
        return []

    face_zero = face_index - 1
    if face_zero < 0 or face_zero >= face_count:
        return []

    if numbers_count == face_count:
        return [face_zero]

    if numbers_count % face_count == 0:
        per_face = numbers_count // face_count
        start = face_zero * per_face
        return list(range(start, min(start + per_face, numbers_count)))

    return [min(face_zero, numbers_count - 1)]


def get_highest_value_face_index(mesh: Mesh) -> int:
    numbers = mesh.get_numbers()
    if not numbers or not mesh.faces:
        return 0

    number_face_map = get_number_face_indices(mesh)
    if len(number_face_map) < len(numbers):
        number_face_map = number_face_map + [0] * (len(numbers) - len(number_face_map))

    best_face = 0
    best_value = float("-inf")
    fallback_face = len(mesh.faces) if mesh.faces else 0

    for number_idx, number_text in enumerate(numbers):
        parsed_value = _parse_face_value(number_text)
        if parsed_value is None:
            continue

        face_idx = number_face_map[number_idx] if number_idx < len(number_face_map) else 0
        if face_idx <= 0:
            face_idx = min(number_idx + 1, fallback_face if fallback_face > 0 else number_idx + 1)

        if parsed_value > best_value:
            best_value = parsed_value
            best_face = face_idx

    # D10 / D100 convention: '0' (or '00') represents the highest value (10 / 100),
    # but _parse_face_value reads it as integer 0. Correct the critical face.
    d10_zero_fix = ('0' in numbers and best_value == 9)
    d100_zero_fix = ('00' in numbers and best_value == 90)
    if d10_zero_fix or d100_zero_fix:
        target_text = '0' if d10_zero_fix else '00'
        for number_idx, number_text in enumerate(numbers):
            if number_text == target_text:
                face_idx = number_face_map[number_idx] if number_idx < len(number_face_map) else 0
                if face_idx > 0:
                    return face_idx

    return best_face


def create_numbers_object_for_mesh(context,
                                   mesh: Mesh,
                                   size: float,
                                   number_scale: float,
                                   number_depth: float,
                                   font_path: str,
                                   number_indicator_type: str = NUMBER_IND_NONE,
                                   period_indicator_scale: float = 1,
                                   period_indicator_space: float = 1,
                                   bar_indicator_height: float = 1,
                                   bar_indicator_width: float = 1,
                                   bar_indicator_space: float = 1,
                                   center_bar: bool = True,
                                   custom_image_face: int = 0,
                                   custom_image_path: str = '',
                                   custom_image_scale: float = 1,
                                   location_override: Optional[List[Tuple[float, float, float]]] = None,
                                    include_indices: Optional[List[int]] = None,
                                    use_critical_face_material: bool = False,
                                    critical_face_material: Tuple[float, float, float, float] = (1.0, 0.0, 0.0, 1.0),
                                    dot_indicator_scale: float = 1,
                                    dot_indicator_space: float = 1) -> List[bpy.types.Object]:
    all_numbers = mesh.get_numbers()
    if location_override is not None:
        all_locations = location_override
    else:
        all_locations = mesh.transform_number_locations(mesh.get_number_locations())
    all_rotations = mesh.transform_number_rotations(mesh.get_number_rotations())

    if len(all_numbers) != len(all_locations) or len(all_numbers) != len(all_rotations):
        return []

    # Determine critical face indices from the full mesh before filtering
    critical_indices_set = set()
    if use_critical_face_material and mesh.faces:
        highest_face = get_highest_value_face_index(mesh)
        if highest_face > 0:
            critical_indices_set = set(get_number_indices_for_face(mesh, highest_face))

        # D4 Tetrahedron special case: numbers are vertex-oriented (each value
        # appears on 3 different faces). Instead of painting an entire face
        # (which would paint 3 different numbers), paint every instance of the
        # highest numeric value across the die.
        if isinstance(mesh, Tetrahedron):
            numeric_values = [(_parse_face_value(txt), txt, idx)
                              for idx, txt in enumerate(all_numbers)]
            numeric_values = [(v, txt, idx) for v, txt, idx in numeric_values if v is not None]
            if numeric_values:
                max_value = max(v for v, _, _ in numeric_values)
                critical_indices_set = {idx for v, _, idx in numeric_values if v == max_value}

    if include_indices is None:
        indices = list(range(len(all_numbers)))
    else:
        indices = [
            idx for idx in include_indices
            if 0 <= idx < len(all_numbers) and idx < len(all_locations) and idx < len(all_rotations)
        ]

    if not indices:
        return []

    regular_indices = [idx for idx in indices if idx not in critical_indices_set]
    critical_indices = [idx for idx in indices if idx in critical_indices_set]

    font_size = mesh.base_font_scale * size * number_scale
    result = []

    if regular_indices:
        numbers = [all_numbers[idx] for idx in regular_indices]
        locations = [all_locations[idx] for idx in regular_indices]
        rotations = [all_rotations[idx] for idx in regular_indices]
        regular_obj = create_numbers(
            context,
            numbers,
            locations,
            rotations,
            font_path,
            font_size,
            number_depth,
            number_indicator_type,
            period_indicator_scale,
            period_indicator_space,
            bar_indicator_height,
            bar_indicator_width,
            bar_indicator_space,
            center_bar,
            custom_image_face=custom_image_face,
            custom_image_path=custom_image_path,
            custom_image_scale=custom_image_scale,
            original_indices=regular_indices,
            material_name="Dice Numbers",
            material_color=(0, 0, 0, 1),
            dot_indicator_scale=dot_indicator_scale,
            dot_indicator_space=dot_indicator_space,
        )
        if regular_obj is not None:
            result.append(regular_obj)

    if critical_indices:
        numbers = [all_numbers[idx] for idx in critical_indices]
        locations = [all_locations[idx] for idx in critical_indices]
        rotations = [all_rotations[idx] for idx in critical_indices]
        critical_obj = create_numbers(
            context,
            numbers,
            locations,
            rotations,
            font_path,
            font_size,
            number_depth,
            number_indicator_type,
            period_indicator_scale,
            period_indicator_space,
            bar_indicator_height,
            bar_indicator_width,
            bar_indicator_space,
            center_bar,
            custom_image_face=custom_image_face,
            custom_image_path=custom_image_path,
            custom_image_scale=custom_image_scale,
            original_indices=critical_indices,
            material_name="Critical Number",
            material_color=critical_face_material,
            dot_indicator_scale=dot_indicator_scale,
            dot_indicator_space=dot_indicator_space,
        )
        if critical_obj is not None:
            result.append(critical_obj)

    return result


def create_panel_number_cutters(context,
                                mesh: Mesh,
                                size: float,
                                number_scale: float,
                                panel_thickness: float,
                                panel_recess_depth: float,
                                font_path: str,
                                number_indicator_type: str = NUMBER_IND_NONE,
                                period_indicator_scale: float = 1,
                                period_indicator_space: float = 1,
                                bar_indicator_height: float = 1,
                                bar_indicator_width: float = 1,
                                bar_indicator_space: float = 1,
                                center_bar: bool = True,
                                custom_image_face: int = 0,
                                custom_image_path: str = '',
                                custom_image_scale: float = 1,
                                exclude_face_index: int = 0) -> Optional[bpy.types.Object]:
    rotations = mesh.transform_number_rotations(mesh.get_number_rotations())
    shifted_locations = offset_number_locations_for_panels(
        mesh.transform_number_locations(mesh.get_number_locations()),
        rotations,
        panel_thickness,
        panel_recess_depth,
    )

    cutter_depth = max(panel_thickness + 0.4, 0.6)
    exclude_indices = set(get_number_indices_for_face(mesh, exclude_face_index))
    include_indices = [
        idx for idx in range(len(mesh.get_numbers()))
        if idx not in exclude_indices
    ]

    result = create_numbers_object_for_mesh(
        context,
        mesh,
        size,
        number_scale,
        cutter_depth,
        font_path,
        number_indicator_type,
        period_indicator_scale,
        period_indicator_space,
        bar_indicator_height,
        bar_indicator_width,
        bar_indicator_space,
        center_bar,
        custom_image_face=custom_image_face,
        custom_image_path=custom_image_path,
        custom_image_scale=custom_image_scale,
        location_override=shifted_locations,
        include_indices=include_indices,
    )
    return result[0] if result else None


def create_top_face_direct_cutter(context,
                                  mesh: Mesh,
                                  top_face_index: int,
                                  size: float,
                                  number_scale: float,
                                  depth: float,
                                  scale_multiplier: float,
                                  font_path: str,
                                  number_indicator_type: str = NUMBER_IND_NONE,
                                  period_indicator_scale: float = 1,
                                  period_indicator_space: float = 1,
                                  bar_indicator_height: float = 1,
                                  bar_indicator_width: float = 1,
                                  bar_indicator_space: float = 1,
                                  center_bar: bool = True,
                                  custom_image_path: str = '',
                                  custom_image_scale: float = 1) -> Optional[bpy.types.Object]:
    if top_face_index <= 0:
        return None

    top_face_number_indices = get_number_indices_for_face(mesh, top_face_index)
    if not top_face_number_indices:
        return None

    depth_value = max(depth, 0.1)
    scaled_number_scale = max(number_scale * scale_multiplier, 0.05)
    forced_custom_face = (top_face_number_indices[0] + 1) if custom_image_path else 0

    result = create_numbers_object_for_mesh(
        context,
        mesh,
        size,
        scaled_number_scale,
        depth_value,
        font_path,
        number_indicator_type,
        period_indicator_scale,
        period_indicator_space,
        bar_indicator_height,
        bar_indicator_width,
        bar_indicator_space,
        center_bar,
        custom_image_face=forced_custom_face,
        custom_image_path=custom_image_path,
        custom_image_scale=custom_image_scale,
        include_indices=top_face_number_indices,
    )
    return result[0] if result else None


def execute_generator(op, context, mesh_cls, name: str, **kwargs) -> Dict[str, str]:
    """
    Main execution function for dice generation operators.

    This function coordinates the entire dice generation process:
    1. Validates input parameters
    2. Creates the dice geometry
    3. Applies finishing (bevel, bumpers, etc.)
    4. Generates and applies numbers
    5. Saves settings for regeneration

    Args:
        op: The operator instance containing user parameters
        context: Blender context
        mesh_cls: The Mesh subclass to instantiate (e.g., Cube, Icosahedron)
        name: Base name for the dice type
        **kwargs: Additional arguments to pass to the mesh_cls constructor

    Returns:
        Dictionary with 'FINISHED' status on success, 'CANCELLED' on failure
    """
    # Validate and sanitize file paths
    op.font_path = validate_font_path(op.font_path)
    op.custom_image_path = validate_svg_path(op.custom_image_path)

    # create the cube mesh
    die = mesh_cls("dice_body", op.size, **kwargs)
    die.apply_print_layout(getattr(op, "fin_support_drop", 0.0) if getattr(op, "add_fin_supports", False) else 0.0)
    die_obj = die.create(context)
    configure_dice_finish_modifier(die_obj, op.dice_finish, getattr(op, "bumper_scale", 1))
    body_material = ensure_material("Dice Body", (0.95, 0.95, 0.9, 1))
    assign_material(die_obj, body_material)

    settings_template = die_obj.dice_gen_settings
    settings_values = collect_settings_from_op(op, settings_template)

    numbers_objects = []
    # create number curves
    if op.add_numbers:
        numbers_objects = die.create_numbers(
            context, op.size, op.number_scale, op.number_depth, op.font_path,
            op.number_indicator_type, op.period_indicator_scale, op.period_indicator_space,
            op.bar_indicator_height, op.bar_indicator_width, op.bar_indicator_space, op.center_bar,
            custom_image_face=op.custom_image_face, custom_image_path=op.custom_image_path,
            custom_image_scale=op.custom_image_scale,
            use_critical_face_material=getattr(op, "use_critical_face_material", False),
            critical_face_material=tuple(getattr(op, "critical_face_material", (1.0, 0.0, 0.0, 1.0))),
            dot_indicator_scale=getattr(op, "dot_indicator_scale", 1),
            dot_indicator_space=getattr(op, "dot_indicator_space", 1),
        )

    # Always tag the body so export/update can find it
    die_obj["dice_gen_type"] = mesh_cls.__name__
    apply_settings(die_obj.dice_gen_settings, settings_values)

    for num_obj in numbers_objects:
        num_obj["dice_body_name"] = die_obj.name
        num_obj["dice_gen_type"] = mesh_cls.__name__
        apply_settings(num_obj.dice_gen_settings, settings_values)

    return {'FINISHED'}


# Common properties
def DiceSizeProperty(default: float):
    return FloatProperty(
        name='Dice Size',
        description='Size of the die (mm)',
        min=1,
        soft_min=1,
        max=100,
        soft_max=100,
        default=default
    )


def DiceFinishProperty():
    return EnumProperty(
        name='Dice Type',
        items=(
            ('sharp', 'Sharp', 'Keep edges sharp'),
            ('chamfer', 'Chamfer', 'Add a light bevel'),
            ('fillet', 'Fillet', 'Round edges with additional bevel segments'),
            ('bumpers', 'Bumpers', 'Inset faces and raise the face borders'),
        ),
        default='sharp',
        description='Edge treatment for the dice body'
    )


def BumperScaleProperty():
    return FloatProperty(
        name='Bumper Size',
        description='Scale the inset and extrusion used to create bumper edges',
        min=0,
        soft_min=0,
        max=5,
        soft_max=5,
        default=1,
    )


AddFinSupportsProperty = BoolProperty(
    name='Generate Fin Supports',
    description='Create contour-style fin supports for resin printing',
    default=False
)


FinSupportContourOffsetProperty = FloatProperty(
    name='Fin Edge Height',
    description='How far up the point-down support edges the fins should climb',
    min=0.05,
    soft_min=0.05,
    soft_max=30,
    default=6.0
)


FinSupportThicknessProperty = FloatProperty(
    name='Bottom Edge Thickness',
    description='Thickness of the fin where it meets the raft',
    min=0.1,
    soft_min=0.1,
    max=5,
    soft_max=5,
    default=2.0
)


FinSupportConnectionThicknessProperty = FloatProperty(
    name='Top Edge Thickness',
    description='Thickness of the fin where it intersects the die edge',
    min=0.1,
    soft_min=0.1,
    max=5,
    soft_max=5,
    default=0.5
)


FinSupportFlareProperty = FloatProperty(
    name='Fin Base Flare',
    description='Additional wall width added at the raft end of each fin',
    min=0.0,
    soft_min=0.0,
    max=5,
    soft_max=2,
    default=0.8
)


FinSupportDropProperty = FloatProperty(
    name='Fin Drop',
    description='Vertical drop from the die to the fin raft',
    min=0.25,
    soft_min=0.25,
    max=30,
    soft_max=15,
    default=6.0
)


FinSupportRaftMarginProperty = FloatProperty(
    name='Raft Margin',
    description='Outward offset applied to the fin raft footprint',
    min=0.0,
    soft_min=0.0,
    max=10,
    soft_max=5,
    default=2.0
)


FinSupportRaftThicknessProperty = FloatProperty(
    name='Raft Thickness',
    description='Thickness of the fin support raft',
    min=0.0,
    soft_min=0.0,
    max=10,
    soft_max=4,
    default=1.2
)


FinSupportRaftTaperProperty = FloatProperty(
    name='Raft Taper',
    description='Amount the raft narrows toward the build plate for easier removal',
    min=0.0,
    soft_min=0.0,
    max=10,
    soft_max=4,
    default=0.8
)


AddNumbersProperty = BoolProperty(
    name='Generate Numbers',
    default=True
)

NumberScaleProperty = FloatProperty(
    name='Number Scale',
    description='Size of the numbers on the die',
    min=0.1,
    soft_min=0.1,
    max=2,
    soft_max=2,
    default=1
)

NumberDepthProperty = FloatProperty(
    name='Number Depth',
    description='Depth of the numbers on the die (mm)',
    min=0.1,
    soft_min=0.1,
    max=2,
    soft_max=2,
    default=0.75
)

FontPathProperty = StringProperty(
    name='Font',
    description='Number font (TTF or OTF)',
    maxlen=1024,
    subtype='FILE_PATH',
    default=DEFAULT_SYSTEM_FONT
)

CustomImagePathProperty = StringProperty(
    name='Custom Image (SVG)',
    description='SVG file to engrave on a selected face',
    maxlen=1024,
    subtype='FILE_PATH'
)

def CustomImageFaceProperty(default=0):
    """
    Create a CustomImageFace property with configurable default.
    Pass the highest face number for the dice type to default to that face.
    """
    return IntProperty(
        name='Custom Image Face',
        description='1-based face index to replace with the custom image (0 disables the feature)',
        min=0,
        soft_min=0,
        default=default
    )

CustomImageScaleProperty = FloatProperty(
    name='Custom Image Scale',
    description='Scale multiplier for the custom image relative to the number size',
    min=0.01,
    soft_min=0.01,
    max=10,
    soft_max=10,
    default=1
)


# Indicator properties
def NumberIndicatorTypeProperty(default: str = NUMBER_IND_PERIOD):
    return EnumProperty(
        name='Orientation Indicator',
        items=((NUMBER_IND_NONE, 'None', 'No indicator'),
               (NUMBER_IND_BAR, 'Bar', 'Horizontal bar'),
               (NUMBER_IND_PERIOD, 'Period', 'Period after number'),
               (NUMBER_IND_DOT, 'Dot', 'Small dot below number')),
        default=default,
        description='Orientation indicator for numbers 6 and 9'
    )


PeriodIndicatorScaleProperty = FloatProperty(
    name='Period Scale',
    description='Scale of the period orientation indicator',
    min=0.1,
    soft_min=0.1,
    max=2,
    soft_max=2,
    default=1
)

PeriodIndicatorSpaceProperty = FloatProperty(
    name='Period Space',
    description='Space between the period orientation indicator and the number',
    min=0,
    soft_min=0,
    max=3,
    soft_max=3,
    default=1
)

BarIndicatorHeightProperty = FloatProperty(
    name='Bar Height',
    description='Height scale of the bar orientation indicator',
    min=0.1,
    soft_min=0.1,
    max=3,
    soft_max=3,
    default=1
)

BarIndicatorWidthProperty = FloatProperty(
    name='Bar Width',
    description='Width scale of the bar orientation indicator',
    min=0.1,
    soft_min=0.1,
    max=2,
    soft_max=2,
    default=1
)

BarIndicatorSpaceProperty = FloatProperty(
    name='Bar Space',
    description='Space between the bar orientation indicator and the number',
    min=0,
    soft_min=0,
    max=3,
    soft_max=3,
    default=1
)

CenterBarProperty = BoolProperty(
    name='Center Align Bar',
    description='If true, the bar indicator is included in the vertical alignment of the number',
    default=True
)

DotIndicatorScaleProperty = FloatProperty(
    name='Dot Scale',
    description='Scale of the dot orientation indicator relative to the number',
    min=0.1,
    soft_min=0.1,
    max=3,
    soft_max=3,
    default=1
)

DotIndicatorSpaceProperty = FloatProperty(
    name='Dot Space',
    description='Space between the dot orientation indicator and the number',
    min=0,
    soft_min=0,
    max=3,
    soft_max=3,
    default=1
)

UseCriticalFaceMaterialProperty = BoolProperty(
    name='Use Critical Face Material',
    description='Assign a distinct material to the highest-value face label',
    default=False
)

CriticalFaceMaterialProperty = FloatVectorProperty(
    name='Critical Face Material',
    description='Material color for the highest-value face label',
    subtype='COLOR',
    size=4,
    min=0.0,
    max=1.0,
    default=(1.0, 0.0, 0.0, 1.0)
)



def NumberVOffsetProperty(default: float): return FloatProperty(
    name='Number V Offset',
    description='Vertical offset of the number positioning',
    min=0.0,
    soft_min=0.0,
    max=1,
    soft_max=1,
    default=default
)


UseFacePanelsProperty = BoolProperty(
    name='Create Face Panels',
    description='Generate inset face pockets and separate printable panel inserts',
    default=False
)

PanelEdgeInsetProperty = FloatProperty(
    name='Panel Edge Inset',
    description='Distance from the original face edge to panel edge (mm)',
    min=0.1,
    soft_min=0.1,
    max=10,
    soft_max=10,
    default=2.0
)

PanelToleranceProperty = FloatProperty(
    name='Panel Tolerance',
    description='Extra clearance between panel and pocket walls (mm)',
    min=0.0,
    soft_min=0.0,
    max=0.5,
    soft_max=0.5,
    default=0.15
)

PanelThicknessProperty = FloatProperty(
    name='Panel Thickness',
    description='Thickness of printed face panels (mm)',
    min=0.2,
    soft_min=0.2,
    max=6,
    soft_max=6,
    default=1.2
)

PanelRecessDepthProperty = FloatProperty(
    name='Panel Recess Depth',
    description='Depth of recessed panel pockets in the die body (mm)',
    min=0.2,
    soft_min=0.2,
    max=8,
    soft_max=8,
    default=1.6
)

PanelTopFaceFlushProperty = BoolProperty(
    name='Flush Highest Value Face',
    description='Leave the highest face value flush (no panel) and engrave directly into the body',
    default=False
)

PanelTopFaceScaleProperty = FloatProperty(
    name='Highest Value Face Scale',
    description='Scale multiplier for engraving on the highest value flush face',
    min=0.1,
    soft_min=0.1,
    max=5,
    soft_max=5,
    default=1.0
)

PanelTopFaceDepthProperty = FloatProperty(
    name='Highest Value Face Depth',
    description='Engraving depth for the highest value flush face (mm)',
    min=0.1,
    soft_min=0.1,
    max=5,
    soft_max=5,
    default=0.9
)


class DiceGenSettings(bpy.types.PropertyGroup):
    size: FloatProperty(
        name="Dice Size",
        description="Size of the die (mm)",
        min=1,
        soft_min=1,
        max=100,
        soft_max=100,
        default=20
    )

    dice_finish: DiceFinishProperty()

    bumper_scale: BumperScaleProperty()

    font_path: FontPathProperty

    custom_image_path: CustomImagePathProperty

    custom_image_face: CustomImageFaceProperty(0)

    custom_image_scale: CustomImageScaleProperty

    use_critical_face_material: UseCriticalFaceMaterialProperty

    critical_face_material: CriticalFaceMaterialProperty

    number_scale: NumberScaleProperty

    number_depth: NumberDepthProperty

    add_fin_supports: AddFinSupportsProperty

    fin_support_contour_offset: FinSupportContourOffsetProperty

    fin_support_connection_thickness: FinSupportConnectionThicknessProperty

    fin_support_thickness: FinSupportThicknessProperty

    fin_support_drop: FinSupportDropProperty

    fin_support_raft_margin: FinSupportRaftMarginProperty

    fin_support_raft_thickness: FinSupportRaftThicknessProperty

    fin_support_raft_taper: FinSupportRaftTaperProperty


    add_numbers: AddNumbersProperty

    number_indicator_type: NumberIndicatorTypeProperty()

    period_indicator_scale: PeriodIndicatorScaleProperty

    period_indicator_space: PeriodIndicatorSpaceProperty

    bar_indicator_height: BarIndicatorHeightProperty

    bar_indicator_width: BarIndicatorWidthProperty

    bar_indicator_space: BarIndicatorSpaceProperty

    center_bar: CenterBarProperty

    dot_indicator_scale: DotIndicatorScaleProperty

    dot_indicator_space: DotIndicatorSpaceProperty

    number_v_offset: NumberVOffsetProperty(0.0)

    number_center_offset: FloatProperty(
        name='Number Center Offset',
        description='Distance of numbers from the center of a face',
        min=0.0,
        soft_min=0.0,
        max=1,
        soft_max=1,
        default=0.5
    )

    num_faces: IntProperty(
        name='Number of Faces',
        description='Number of faces on custom dice',
        min=3,
        soft_min=3,
        max=100,
        soft_max=40,
        default=6,
        step=1
    )

    base_height: FloatProperty(
        name='Base Height',
        description='Base height of the die (height of a face) (mm)',
        min=1,
        soft_min=1,
        max=100,
        soft_max=100,
        default=14
    )

    point_height: FloatProperty(
        name='Point Height',
        description='Point height of the die (mm)',
        min=1,
        soft_min=1,
        max=100,
        soft_max=100,
        default=7
    )

    top_point_height: FloatProperty(
        name='Top Point Height',
        description='Top point height of the die',
        min=0.25,
        soft_min=0.25,
        max=2,
        soft_max=2,
        default=7
    )

    bottom_point_height: FloatProperty(
        name='Bottom Point Height',
        description='Bottom point height of the die',
        min=0.25,
        soft_min=0.25,
        max=2.5,
        soft_max=2.5,
        default=7
    )

    height: FloatProperty(
        name='Dice Height',
        description='Height of the die',
        min=0.0,
        soft_min=0.0,
        max=100,
        soft_max=100,
        default=2 / 3
    )

    number_h_offset: FloatProperty(
        name='Number Horizontal Offset',
        description='Horizontal offset for number positioning on dice faces',
        min=-1.0,
        soft_min=-1.0,
        max=1.0,
        soft_max=1.0,
        default=0.0
    )


# ============================================================================
# UNITY-READY EXPORT WORKFLOW
# ============================================================================

UNITY_MATERIAL_MAP = {
    "Dice Body": "MAT_Die_Body",
    "Dice Numbers": "MAT_Die_Label",
    "Critical Number": "MAT_Die_Label_Critical",
    "Dice Supports": "MAT_Die_Support",
    "Dice Panels": "MAT_Die_Panel",
}


def _get_unity_type_label(body_obj: bpy.types.Object) -> str:
    """Resolve a clean dice type string from object metadata."""
    die_type = body_obj.get("dice_gen_type", "")
    if not die_type:
        return "Unknown"
    # Map internal class names to user-friendly labels
    label_map = {
        "Tetrahedron": "D4",
        "D4Crystal": "D4_Crystal",
        "D4Shard": "D4_Shard",
        "CustomCrystal": "Custom_Crystal",
        "CustomShard": "Custom_Shard",
        "CustomBipyramid": "Custom_Bipyramid",
        "CustomTrapezohedron": "Custom_Trap",
        "Cube": "D6",
        "Octahedron": "D8",
        "D10Mesh": "D10",
        "D100Mesh": "D100",
        "Dodecahedron": "D12",
        "Icosahedron": "D20",
    }
    return label_map.get(die_type, die_type)


def _rename_materials_for_unity(obj: bpy.types.Object) -> None:
    """Rename materials on the object to Unity-friendly names."""
    for slot in obj.material_slots:
        if slot.material and slot.material.name in UNITY_MATERIAL_MAP:
            slot.material.name = UNITY_MATERIAL_MAP[slot.material.name]


def _duplicate_object(obj: bpy.types.Object) -> Optional[bpy.types.Object]:
    """Duplicate an object in the view layer and return the copy."""
    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active

    for ob in view_layer.objects:
        ob.select_set(False)
    obj.select_set(True)
    view_layer.objects.active = obj

    bpy.ops.object.duplicate()
    copy = view_layer.objects.active

    view_layer.objects.active = previous_active
    if copy is None or copy == obj:
        return None
    return copy


def _remove_boolean_modifiers(obj: bpy.types.Object) -> None:
    """Remove all BOOLEAN modifiers from an object."""
    for modifier in list(obj.modifiers):
        if modifier.type == 'BOOLEAN':
            obj.modifiers.remove(modifier)


def _rename_object_and_data(obj: bpy.types.Object, new_name: str) -> None:
    """Rename an object and its mesh data block."""
    obj.name = new_name
    if obj.data:
        obj.data.name = new_name


def _prepare_unity_export_set(body_obj: bpy.types.Object) -> List[bpy.types.Object]:
    """
    Create temporary export copies of the dice body and all its associated
    number/critical pieces. Removes boolean modifiers from the body so it
    stays solid, applies transforms, renames everything Unity-friendly, and
    renames materials to MAT_* conventions.

    Returns a list of export-ready objects (body, numbers, critical).
    """
    if body_obj is None or body_obj.type != 'MESH':
        return []

    dice_type = _get_unity_type_label(body_obj)
    export_objects: List[bpy.types.Object] = []

    # --- Body ---
    body_copy = _duplicate_object(body_obj)
    if body_copy is None:
        return []
    _remove_boolean_modifiers(body_copy)
    apply_transform(body_copy, use_location=True, use_rotation=True, use_scale=True)
    _rename_object_and_data(body_copy, f"GG_{dice_type}_Body")
    _rename_materials_for_unity(body_copy)
    export_objects.append(body_copy)

    # --- Numbers (regular) ---
    numbers_name = body_obj.get("dice_numbers_name")
    if numbers_name:
        numbers_obj = bpy.data.objects.get(numbers_name)
        if numbers_obj and numbers_obj.type == 'MESH':
            num_copy = _duplicate_object(numbers_obj)
            if num_copy:
                apply_transform(num_copy, use_location=True, use_rotation=True, use_scale=True)
                _rename_object_and_data(num_copy, f"GG_{dice_type}_Numbers")
                _rename_materials_for_unity(num_copy)
                export_objects.append(num_copy)

    # --- Critical numbers ---
    critical_name = body_obj.get("dice_critical_numbers_name")
    if critical_name:
        critical_obj = bpy.data.objects.get(critical_name)
        if critical_obj and critical_obj.type == 'MESH':
            crit_copy = _duplicate_object(critical_obj)
            if crit_copy:
                apply_transform(crit_copy, use_location=True, use_rotation=True, use_scale=True)
                _rename_object_and_data(crit_copy, f"GG_{dice_type}_Numbers_Critical")
                _rename_materials_for_unity(crit_copy)
                export_objects.append(crit_copy)

    return export_objects


def _export_objects_fbx(objects: List[bpy.types.Object], filepath: str) -> bool:
    """Export multiple objects to a single FBX file."""
    if not objects:
        return False

    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active

    for ob in view_layer.objects:
        ob.select_set(False)
    for ob in objects:
        ob.select_set(True)
    view_layer.objects.active = objects[0]

    try:
        bpy.ops.export_scene.fbx(
            filepath=filepath,
            use_selection=True,
            apply_unit_scale=True,
            apply_scale_options='FBX_SCALE_ALL',
            axis_forward='-Z',
            axis_up='Y',
            bake_space_transform=True,
            mesh_smooth_type='OFF',
            use_mesh_edges=False,
            use_tspace=False,
            use_custom_props=False,
            add_leaf_bones=False,
            use_armature_deform_only=False,
        )
        success = True
    except RuntimeError:
        success = False

    view_layer.objects.active = previous_active
    return success


class DICE_OT_export_unity_ready(bpy.types.Operator):
    """Export selected dice bodies as Unity-ready FBX meshes.
    Exports the body, regular numbers, and critical numbers as separate
    objects with Unity-friendly material names (MAT_Die_Body,
    MAT_Die_Label, MAT_Die_Label_Critical) so they can be customized
    individually in Unity."""
    bl_idname = "dicegen.export_unity_ready"
    bl_label = "Export Unity-Ready FBX"
    bl_options = {'REGISTER'}

    export_format: EnumProperty(
        name="Format",
        items=(
            ('FBX', 'FBX', 'Autodesk FBX'),
            ('GLB', 'glTF Binary', 'glTF 2.0 Binary'),
        ),
        default='FBX',
    )

    def execute(self, context):
        selected = list(context.selected_objects)
        if not selected:
            self.report({'WARNING'}, "No objects selected. Select dice bodies to export.")
            return {'CANCELLED'}

        # Resolve candidates: selected meshes that are dice bodies (have dice_gen_type
        # but NOT dice_body_name — the latter marks number cutter objects).
        candidates = [ob for ob in selected if ob.type == 'MESH'
                      and ob.get("dice_gen_type") is not None
                      and ob.get("dice_body_name") is None]
        if not candidates:
            self.report({'WARNING'}, "No valid dice bodies selected. Make sure you select the die body (not the number cutters).")
            return {'CANCELLED'}

        if not bpy.data.filepath:
            self.report({'ERROR'}, "Save your .blend file first so the exporter knows where to write.")
            return {'CANCELLED'}

        base_dir = bpy.path.abspath("//exports/unity/")
        exported = 0
        failed = 0

        all_temp_objects: List[bpy.types.Object] = []

        for body_obj in candidates:
            dice_type = _get_unity_type_label(body_obj)
            type_dir = os.path.join(base_dir, dice_type.lower().replace("_", ""))
            os.makedirs(type_dir, exist_ok=True)

            export_set = _prepare_unity_export_set(body_obj)
            if not export_set:
                failed += 1
                continue

            all_temp_objects.extend(export_set)

            filename = f"grangol_{dice_type.lower()}_default"
            if self.export_format == 'FBX':
                filepath = os.path.join(type_dir, filename + ".fbx")
                ok = _export_objects_fbx(export_set, filepath)
            else:
                filepath = os.path.join(type_dir, filename + ".glb")
                ok = self._export_objects_glb(export_set, filepath)

            if ok:
                exported += 1
                self.report({'INFO'}, f"Exported: {filepath} ({len(export_set)} objects)")
            else:
                failed += 1
                self.report({'ERROR'}, f"Failed to export: {filepath}")

        # Clean up temporary export objects
        for temp_obj in all_temp_objects:
            if temp_obj.name in bpy.data.objects:
                mesh_data = temp_obj.data
                bpy.data.objects.remove(temp_obj, do_unlink=True)
                if mesh_data and mesh_data.users == 0:
                    bpy.data.meshes.remove(mesh_data)

        # Re-select original selection
        for ob in selected:
            if ob.name in context.view_layer.objects:
                ob.select_set(True)

        if exported == 0:
            self.report({'ERROR'}, "Export failed for all selected dice.")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Exported {exported} dice ({failed} failed). Output: {base_dir}")
        return {'FINISHED'}

    def _export_objects_glb(self, objects: List[bpy.types.Object], filepath: str) -> bool:
        if not objects:
            return False

        view_layer = bpy.context.view_layer
        previous_active = view_layer.objects.active

        for ob in view_layer.objects:
            ob.select_set(False)
        for ob in objects:
            ob.select_set(True)
        view_layer.objects.active = objects[0]

        try:
            bpy.ops.export_scene.gltf(
                filepath=filepath,
                use_selection=True,
                export_format='GLB',
                export_yup=True,
            )
            success = True
        except RuntimeError:
            success = False

        view_layer.objects.active = previous_active
        return success


# ============================================================================
# OLD OPERATOR CLASSES - REMOVED
# All dice generation now uses DICE_OT_add_from_preset operator
# The individual operator classes (DiceGeneratorBase, D4Generator, D6Generator, etc.)
# have been removed as they are no longer used. The Add Mesh menu now calls
# DICE_OT_add_from_preset directly.
# Removed ~577 lines of duplicate code
# ============================================================================

class OBJECT_OT_dice_gen_update(bpy.types.Operator):
    bl_idname = "object.dice_gen_update"
    bl_label = "Update Dice Numbers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ob = context.object
        settings_owner = resolve_settings_owner(ob)

        if settings_owner is None:
            self.report({'ERROR'}, "Object has no dice settings")
            return {'CANCELLED'}

        settings_values = snapshot_settings(settings_owner.dice_gen_settings)
        die_type = settings_owner.get("dice_gen_type")

        numbers_obj = None
        if settings_owner.get("dice_body_name"):
            numbers_obj = settings_owner
        elif ob.get("dice_numbers_name"):
            numbers_obj = bpy.data.objects.get(ob.get("dice_numbers_name"))

        body_obj = None
        if settings_owner.get("dice_body_name"):
            body_obj = bpy.data.objects.get(settings_owner.get("dice_body_name"))
        else:
            body_obj = ob

        if body_obj is None or die_type is None:
            self.report({'ERROR'}, "Object is not a generated die")
            return {'CANCELLED'}

        mesh_cls_map = {
            "Tetrahedron": Tetrahedron,
            "D4Crystal": D4Crystal,
            "D4Shard": D4Shard,
            "CustomCrystal": CustomCrystal,
            "CustomShard": CustomShard,
            "CustomBipyramid": CustomBipyramid,
            "CustomTrapezohedron": CustomTrapezohedron,
            "Cube": Cube,
            "Octahedron": Octahedron,
            "Dodecahedron": Dodecahedron,
            "Icosahedron": Icosahedron,
            "D10Mesh": D10Mesh,
            "D100Mesh": D100Mesh,
        }

        mesh_cls = mesh_cls_map.get(die_type)
        if mesh_cls is None:
            self.report({'ERROR'}, f"Unknown dice type: {die_type}")
            return {'CANCELLED'}

        size = settings_values["size"]

        if die_type == "Tetrahedron":
            die = mesh_cls(
                body_obj.name,
                size,
                settings_values["number_center_offset"],
                settings_values["number_h_offset"],
                settings_values["number_v_offset"],
            )
        elif die_type == "D4Crystal":
            die = mesh_cls(
                body_obj.name,
                size,
                settings_values["base_height"],
                settings_values["top_point_height"],
                settings_values["bottom_point_height"],
                settings_values["number_h_offset"],
                settings_values["number_v_offset"],
            )
        elif die_type == "CustomCrystal":
            die = mesh_cls(
                body_obj.name,
                size,
                settings_values["num_faces"],
                settings_values["base_height"],
                settings_values["top_point_height"],
                settings_values["bottom_point_height"],
                settings_values["number_h_offset"],
                settings_values["number_v_offset"],
            )
        elif die_type == "D4Shard":
            die = mesh_cls(
                body_obj.name,
                size,
                settings_values["top_point_height"],
                settings_values["bottom_point_height"],
                settings_values["number_v_offset"],
                settings_values["number_h_offset"],
            )
        elif die_type == "CustomShard":
            die = mesh_cls(
                body_obj.name,
                size,
                settings_values["num_faces"],
                settings_values["top_point_height"],
                settings_values["bottom_point_height"],
                settings_values["number_v_offset"],
                settings_values["number_h_offset"],
            )
        elif die_type == "CustomBipyramid":
            die = mesh_cls(
                body_obj.name,
                size,
                settings_values["num_faces"],
                settings_values["top_point_height"],
                settings_values["bottom_point_height"],
                settings_values["number_h_offset"],
                settings_values["number_v_offset"],
            )
        elif die_type == "CustomTrapezohedron":
            die = mesh_cls(
                body_obj.name,
                size,
                settings_values["num_faces"],
                settings_values["height"],
                settings_values["number_v_offset"],
                settings_values["number_h_offset"],
            )
        elif die_type in ("D10Mesh", "D100Mesh"):
            die = mesh_cls(
                body_obj.name,
                size,
                settings_values["height"],
                settings_values["number_v_offset"],
                settings_values["number_h_offset"],
            )
        else:
            die = mesh_cls(body_obj.name, size, settings_values["number_h_offset"], settings_values["number_v_offset"])

        die.apply_print_layout(settings_values["fin_support_drop"] if settings_values.get("add_fin_supports") else 0.0)

        font_path = validate_font_path(settings_values["font_path"]) if settings_values["font_path"] else ""
        custom_image_path = validate_svg_path(settings_values["custom_image_path"]) if settings_values["custom_image_path"] else ""
        settings_values["font_path"] = font_path
        settings_values["custom_image_path"] = custom_image_path

        old_numbers_name = body_obj.get("dice_numbers_name")
        old_critical_name = body_obj.get("dice_critical_numbers_name")
        if settings_owner.get("dice_body_name"):
            owner_name = settings_owner.name
            if owner_name == old_critical_name:
                pass  # already tracked
            else:
                old_numbers_name = owner_name

        for mod_name in ('boolean', 'boolean_critical'):
            remove_modifier_if_exists(body_obj, mod_name)

        for key in ("dice_numbers_name", "dice_critical_numbers_name"):
            if key in body_obj:
                del body_obj[key]

        for name in (old_numbers_name, old_critical_name):
            if name and name != body_obj.name:
                remove_object_if_exists(name)

        clear_panel_artifacts(body_obj)
        clear_fin_support_artifacts(body_obj)
        rebuild_mesh_object(body_obj, die.get_output_vertices(), die.faces)
        die.dice_mesh = body_obj
        configure_dice_finish_modifier(
            body_obj,
            settings_values.get("dice_finish", "sharp"),
            settings_values.get("bumper_scale", 1),
        )

        indicator_type = NUMBER_IND_NONE
        if supports_number_indicators(die_type, settings_values["num_faces"]):
            indicator_type = settings_values["number_indicator_type"]

        new_numbers_objects = []
        if settings_values["add_numbers"]:
            new_numbers_objects = create_numbers_object_for_mesh(
                context,
                die,
                size,
                settings_values["number_scale"],
                settings_values["number_depth"],
                font_path,
                indicator_type,
                settings_values["period_indicator_scale"],
                settings_values["period_indicator_space"],
                settings_values["bar_indicator_height"],
                settings_values["bar_indicator_width"],
                settings_values["bar_indicator_space"],
                settings_values["center_bar"],
                settings_values["custom_image_face"],
                custom_image_path,
                settings_values["custom_image_scale"],
                use_critical_face_material=settings_values.get("use_critical_face_material", False),
                critical_face_material=settings_values.get("critical_face_material", (1.0, 0.0, 0.0, 1.0)),
                dot_indicator_scale=settings_values.get("dot_indicator_scale", 1),
                dot_indicator_space=settings_values.get("dot_indicator_space", 1),
            )

            for idx, num_obj in enumerate(new_numbers_objects):
                num_obj.name = "dice_numbers" if idx == 0 else "dice_numbers_critical"
                mod_name = 'boolean' if idx == 0 else 'boolean_critical'
                remember = 'dice_numbers_name' if idx == 0 else 'dice_critical_numbers_name'
                apply_boolean_modifier(body_obj, num_obj, modifier_name=mod_name, remember_key=remember)
                num_obj["dice_body_name"] = body_obj.name
                num_obj["dice_gen_type"] = die_type
                apply_settings(num_obj.dice_gen_settings, settings_values)

        fin_support_object = generate_fin_supports(
            context,
            body_obj,
            die.get_output_vertices(),
            die.faces,
            settings_values,
        )
        if settings_values.get("add_fin_supports") and fin_support_object is None:
            self.report({'WARNING'}, "Could not regenerate fin supports for this die.")

        body_obj["dice_gen_type"] = die_type
        apply_settings(body_obj.dice_gen_settings, settings_values)

        target_collection = body_obj.users_collection[0] if body_obj.users_collection else context.scene.collection
        extra_objs = list(new_numbers_objects)
        if fin_support_object is not None:
            extra_objs.append(fin_support_object)
        organize_dice_objects_in_collection(
            body_obj,
            target_collection,
            extra_objects=extra_objs,
        )

        return {'FINISHED'}


class OBJECT_PT_dice_gen(bpy.types.Panel):
    bl_label = "Dice Gen"
    bl_idname = "OBJECT_PT_dice_gen"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    @classmethod
    def poll(cls, context):
        return resolve_settings_owner(context.object) is not None

    def draw(self, context):
        """Draw the dice generation settings panel with organized property groups."""
        layout = self.layout
        settings_owner = resolve_settings_owner(context.object)
        if settings_owner is None:
            layout.label(text="No dice settings found")
            return

        settings = settings_owner.dice_gen_settings

        # Font Settings
        box = layout.box()
        box.label(text="Font", icon='FONT_DATA')
        box.prop(settings, "font_path")

        # Number Settings
        box = layout.box()
        box.label(text="Numbers", icon='OUTLINER_OB_FONT')
        box.prop(settings, "number_scale")
        box.prop(settings, "number_depth")
        box.prop(settings, "use_critical_face_material")
        if settings.use_critical_face_material:
            box.prop(settings, "critical_face_material")
        box.prop(settings, "number_indicator_type")
        if settings.number_indicator_type == NUMBER_IND_DOT:
            box.prop(settings, "dot_indicator_scale")
            box.prop(settings, "dot_indicator_space")

        # Custom Image Settings
        box = layout.box()
        box.label(text="Custom Image", icon='IMAGE_DATA')
        box.prop(settings, "custom_image_path")
        row = box.row()
        row.enabled = bool(settings.custom_image_path)
        row.prop(settings, "custom_image_face")
        row.prop(settings, "custom_image_scale")

        box = layout.box()
        box.label(text="Fin Supports", icon='MOD_SOLIDIFY')
        box.prop(settings, "add_fin_supports")
        if settings.add_fin_supports:
            box.prop(settings, "fin_support_contour_offset")
            box.prop(settings, "fin_support_connection_thickness")
            box.prop(settings, "fin_support_thickness")
            box.prop(settings, "fin_support_drop")
            box.prop(settings, "fin_support_raft_margin")
            box.prop(settings, "fin_support_raft_thickness")
            box.prop(settings, "fin_support_raft_taper")

        layout.separator()
        box = layout.box()
        box.label(text="Unity Export", icon='EXPORT')
        box.operator("dicegen.export_unity_ready", text="Export Selected as FBX")
        box.label(text="Output: //exports/unity/")

        layout.separator()
        layout.operator("object.dice_gen_update", text="Regenerate Dice", icon='FILE_REFRESH')


class MeshDiceAdd(Menu):
    """
    Dice menu under "Add Mesh"
    """

    bl_idname = 'VIEW3D_MT_mesh_dice_add'
    bl_label = 'Dice'

    def draw(self, context):
        layout = self.layout
        layout.operator_context = 'INVOKE_REGION_WIN'

        # Use the sidebar operator for everything - single code path
        op = layout.operator('dicegen.add_from_preset', text='D4 Tetrahedron')
        op.dice_type = 'D4'

        op = layout.operator('dicegen.add_from_preset', text='D4 Crystal')
        op.dice_type = 'D4_CRYSTAL'

        op = layout.operator('dicegen.add_from_preset', text='D4 Shard')
        op.dice_type = 'D4_SHARD'

        op = layout.operator('dicegen.add_from_preset', text='D6 Cube')
        op.dice_type = 'D6'

        op = layout.operator('dicegen.add_from_preset', text='D8 Octahedron')
        op.dice_type = 'D8'

        op = layout.operator('dicegen.add_from_preset', text='D10 Trapezohedron')
        op.dice_type = 'D10'

        op = layout.operator('dicegen.add_from_preset', text='D100 Trapezohedron')
        op.dice_type = 'D100'

        op = layout.operator('dicegen.add_from_preset', text='D12 Dodecahedron')
        op.dice_type = 'D12'

        op = layout.operator('dicegen.add_from_preset', text='D20 Icosahedron')
        op.dice_type = 'D20'

        layout.separator()

        op = layout.operator('dicegen.add_from_preset', text='Custom Trapezohedron')
        op.dice_type = 'CUSTOM_TRAP'

        op = layout.operator('dicegen.add_from_preset', text='Custom Crystal')
        op.dice_type = 'CUSTOM_CRYSTAL'

        op = layout.operator('dicegen.add_from_preset', text='Custom Shard')
        op.dice_type = 'CUSTOM_SHARD'

        op = layout.operator('dicegen.add_from_preset', text='Custom Bipyramid')
        op.dice_type = 'CUSTOM_BIPYRAMID'


# Define "Extras" menu
def menu_func(self, context):
    layout = self.layout
    layout.operator_context = 'INVOKE_REGION_WIN'

    layout.separator()
    layout.menu('VIEW3D_MT_mesh_dice_add', text='Dice', icon='CUBE')


class DiceGenPresets(bpy.types.PropertyGroup):
    """PropertyGroup to store persistent dice generation settings in the scene"""

    dice_finish: DiceFinishProperty()
    bumper_scale: BumperScaleProperty()

    size: FloatProperty(
        name="Dice Size",
        description="Size of the die (mm)",
        min=1,
        soft_min=1,
        max=100,
        soft_max=100,
        default=20
    )

    add_fin_supports: AddFinSupportsProperty
    fin_support_contour_offset: FinSupportContourOffsetProperty
    fin_support_connection_thickness: FinSupportConnectionThicknessProperty
    fin_support_thickness: FinSupportThicknessProperty
    fin_support_drop: FinSupportDropProperty
    fin_support_raft_margin: FinSupportRaftMarginProperty
    fin_support_raft_thickness: FinSupportRaftThicknessProperty
    fin_support_raft_taper: FinSupportRaftTaperProperty

    add_numbers: AddNumbersProperty
    number_scale: NumberScaleProperty
    number_depth: NumberDepthProperty
    font_path: FontPathProperty

    number_indicator_type: NumberIndicatorTypeProperty()
    period_indicator_scale: PeriodIndicatorScaleProperty
    period_indicator_space: PeriodIndicatorSpaceProperty
    bar_indicator_height: BarIndicatorHeightProperty
    bar_indicator_width: BarIndicatorWidthProperty
    bar_indicator_space: BarIndicatorSpaceProperty
    center_bar: CenterBarProperty

    dot_indicator_scale: DotIndicatorScaleProperty

    dot_indicator_space: DotIndicatorSpaceProperty

    custom_image_path: CustomImagePathProperty
    custom_image_face: CustomImageFaceProperty(20)
    custom_image_scale: CustomImageScaleProperty

    use_critical_face_material: UseCriticalFaceMaterialProperty

    critical_face_material: CriticalFaceMaterialProperty

    number_center_offset: FloatProperty(
        name='Number Center Offset',
        description='Distance of numbers from the center of a face (D4 only)',
        min=0.0,
        soft_min=0.0,
        max=1,
        soft_max=1,
        default=0.5
    )

    num_faces: IntProperty(
        name='Number of Faces',
        description='Number of faces on custom dice',
        min=3,
        soft_min=3,
        max=100,
        soft_max=40,
        default=6,
        step=1
    )

    # Geometry-specific properties
    base_height: FloatProperty(
        name='Base Height',
        description='Base height of the die (D4 Crystal) (mm)',
        min=1,
        soft_min=1,
        max=100,
        soft_max=100,
        default=14
    )
    point_height: FloatProperty(
        name='Point Height',
        description='Point height of the die (D4 Crystal) (mm)',
        min=1,
        soft_min=1,
        max=100,
        soft_max=100,
        default=7
    )
    top_point_height: FloatProperty(
        name='Top Point Height',
        description='Top point height of the die',
        min=0.25,
        soft_min=0.25,
        max=100,
        soft_max=100,
        default=7
    )
    bottom_point_height: FloatProperty(
        name='Bottom Point Height',
        description='Bottom point height of the die',
        min=0.25,
        soft_min=0.25,
        max=100,
        soft_max=100,
        default=7
    )
    height: FloatProperty(
        name='Dice Height',
        description='Height of the die (D10/D100)',
        min=0.45,
        soft_min=0.45,
        max=2,
        soft_max=2,
        default=2 / 3
    )

    top_point_height_shard: FloatProperty(
        name='Top Point Height (Shard)',
        description='Top point height for shard dice (relative multiplier)',
        min=0.25,
        soft_min=0.25,
        max=2,
        soft_max=2,
        default=0.75
    )
    bottom_point_height_shard: FloatProperty(
        name='Bottom Point Height (Shard)',
        description='Bottom point height for shard dice (relative multiplier)',
        min=0.25,
        soft_min=0.25,
        max=2.5,
        soft_max=2.5,
        default=1.75
    )

    number_h_offset: FloatProperty(
        name='Number Horizontal Offset',
        description='Horizontal offset for number positioning on dice faces',
        min=-1.0,
        soft_min=-1.0,
        max=1.0,
        soft_max=1.0,
        default=0.0
    )

    number_v_offset_d4_shard: FloatProperty(
        name='Number Vertical Offset (D4 Shard)',
        description='Vertical offset of numbers for D4 Shard',
        min=0,
        soft_min=0,
        max=1,
        soft_max=1,
        default=0.75
    )
    number_v_offset: FloatProperty(
        name='Number Vertical Offset (D10/D100)',
        description='Vertical offset of numbers for D10 and D100',
        min=0,
        soft_min=0,
        max=1,
        soft_max=1,
        default=0.33
    )


class DICE_OT_add_from_preset(bpy.types.Operator):
    """Add a dice to the scene using preset settings"""
    bl_idname = 'dicegen.add_from_preset'
    bl_label = 'Add Dice'
    bl_options = {'REGISTER', 'UNDO'}

    dice_type: EnumProperty(
        name="Dice Type",
        items=[
            ('D4', 'D4', 'Tetrahedron'),
            ('D4_CRYSTAL', 'D4 Crystal', 'Crystal D4'),
            ('D4_SHARD', 'D4 Shard', 'Shard D4'),
            ('D6', 'D6', 'Cube'),
            ('D8', 'D8', 'Octahedron'),
            ('D10', 'D10', 'Trapezohedron'),
            ('D12', 'D12', 'Dodecahedron'),
            ('D20', 'D20', 'Icosahedron'),
            ('D100', 'D100', 'Trapezohedron'),
            ('CUSTOM_CRYSTAL', 'Custom Crystal', 'Custom Crystal Dice'),
            ('CUSTOM_SHARD', 'Custom Shard', 'Custom Shard Dice'),
            ('CUSTOM_BIPYRAMID', 'Custom Bipyramid', 'Custom Bipyramid Dice'),
            ('CUSTOM_TRAP', 'Custom Trapezohedron', 'Custom D10-style Trapezohedron'),
        ]
    )

    # Properties from presets - these will override preset values when set
    dice_finish: DiceFinishProperty()
    bumper_scale: BumperScaleProperty()
    size: FloatProperty(
        name="Dice Size",
        description="Size of the die (mm)",
        min=1,
        soft_min=1,
        max=100,
        soft_max=100,
        default=20
    )
    add_fin_supports: AddFinSupportsProperty
    fin_support_contour_offset: FinSupportContourOffsetProperty
    fin_support_connection_thickness: FinSupportConnectionThicknessProperty
    fin_support_thickness: FinSupportThicknessProperty
    fin_support_drop: FinSupportDropProperty
    fin_support_raft_margin: FinSupportRaftMarginProperty
    fin_support_raft_thickness: FinSupportRaftThicknessProperty
    fin_support_raft_taper: FinSupportRaftTaperProperty
    add_numbers: AddNumbersProperty
    number_scale: NumberScaleProperty
    number_depth: NumberDepthProperty
    font_path: FontPathProperty
    number_indicator_type: NumberIndicatorTypeProperty()
    period_indicator_scale: PeriodIndicatorScaleProperty
    period_indicator_space: PeriodIndicatorSpaceProperty
    bar_indicator_height: BarIndicatorHeightProperty
    bar_indicator_width: BarIndicatorWidthProperty
    bar_indicator_space: BarIndicatorSpaceProperty
    center_bar: CenterBarProperty
    dot_indicator_scale: DotIndicatorScaleProperty
    dot_indicator_space: DotIndicatorSpaceProperty
    custom_image_path: CustomImagePathProperty
    custom_image_face: IntProperty(
        name='Custom Image Face',
        description='1-based face index to replace with the custom image (0 disables the feature)',
        min=0,
        soft_min=0,
        default=0
    )
    custom_image_scale: CustomImageScaleProperty
    use_critical_face_material: UseCriticalFaceMaterialProperty
    critical_face_material: CriticalFaceMaterialProperty

    # Geometry-specific properties
    number_center_offset: FloatProperty(
        name='Number Center Offset',
        description='Distance of numbers from the center of a face (D4 only)',
        min=0.0,
        soft_min=0.0,
        max=1,
        soft_max=1,
        default=0.5
    )
    num_faces: IntProperty(
        name='Number of Faces',
        description='Number of faces on custom dice',
        min=3,
        soft_min=3,
        max=100,
        soft_max=40,
        default=6,
        step=2
    )
    base_height: FloatProperty(
        name='Base Height',
        description='Base height of the die (D4 Crystal) (mm)',
        min=1,
        soft_min=1,
        max=100,
        soft_max=100,
        default=14
    )
    point_height: FloatProperty(
        name='Point Height',
        description='Point height of the die (D4 Crystal) (mm)',
        min=1,
        soft_min=1,
        max=100,
        soft_max=100,
        default=7
    )
    top_point_height: FloatProperty(
        name='Top Point Height',
        description='Top point height of the die',
        min=0.25,
        soft_min=0.25,
        max=100,
        soft_max=100,
        default=3
    )
    bottom_point_height: FloatProperty(
        name='Bottom Point Height',
        description='Bottom point height of the die',
        min=0.25,
        soft_min=0.25,
        max=100,
        soft_max=100,
        default=3
    )
    height: FloatProperty(
        name='Dice Height',
        description='Height of the die (D10/D100)',
        min=0.45,
        soft_min=0.45,
        max=2,
        soft_max=2,
        default=2 / 3
    )
    number_v_offset: FloatProperty(
        name='Number Vertical Offset',
        description='Vertical offset of numbers on the dice faces',
        min=0,
        soft_min=0,
        max=1,
        soft_max=1,
        default=0.0
    )

    number_h_offset: FloatProperty(
        name='Number Horizontal Offset',
        description='Horizontal offset for number positioning on dice faces',
        min=-1.0,
        soft_min=-1.0,
        max=1.0,
        soft_max=1.0,
        default=0.0
    )

    def draw(self, context):
        """Draw the operator panel with only relevant properties for the selected dice type"""
        layout = self.layout

        # Define which properties are relevant for each dice type
        _indicator_props = [
            'number_indicator_type', 'period_indicator_scale', 'period_indicator_space',
            'bar_indicator_height', 'bar_indicator_width', 'bar_indicator_space', 'center_bar',
            'dot_indicator_scale', 'dot_indicator_space',
        ]

        property_relevance = {
            'D4': ['size', 'number_center_offset', 'add_numbers', 'number_scale', 'number_depth',
                   'number_h_offset', 'number_v_offset', 'font_path', 'custom_image_path', 'custom_image_face', 'custom_image_scale', 'use_critical_face_material', 'critical_face_material'],
            'D4_CRYSTAL': ['size', 'base_height', 'top_point_height', 'bottom_point_height', 'add_numbers', 'number_scale',
                          'number_depth', 'number_h_offset', 'number_v_offset', 'font_path', 'custom_image_path', 'custom_image_face', 'custom_image_scale', 'use_critical_face_material', 'critical_face_material'],
            'D4_SHARD': ['size', 'top_point_height', 'bottom_point_height',
                        'add_numbers', 'number_scale', 'number_depth', 'number_h_offset', 'number_v_offset', 'font_path',
                        'custom_image_path', 'custom_image_face', 'custom_image_scale', 'use_critical_face_material', 'critical_face_material'],
            'D6': ['size', 'add_numbers', 'number_scale', 'number_depth', 'number_h_offset', 'number_v_offset', 'font_path',
                   'custom_image_path', 'custom_image_face', 'custom_image_scale', 'use_critical_face_material', 'critical_face_material'],
            'D8': ['size', 'add_numbers', 'number_scale', 'number_depth', 'number_h_offset', 'number_v_offset', 'font_path',
                   'custom_image_path', 'custom_image_face', 'custom_image_scale', 'use_critical_face_material', 'critical_face_material'],
            'D10': ['size', 'height', 'add_numbers', 'number_scale', 'number_depth', 'number_h_offset', 'number_v_offset',
                   'font_path'] + _indicator_props +
                   ['custom_image_path', 'custom_image_face', 'custom_image_scale', 'use_critical_face_material', 'critical_face_material'],
            'D100': ['size', 'height', 'add_numbers', 'number_scale', 'number_depth', 'number_h_offset', 'number_v_offset',
                    'font_path'] + _indicator_props +
                    ['custom_image_path', 'custom_image_face', 'custom_image_scale', 'use_critical_face_material', 'critical_face_material'],
            'CUSTOM_TRAP': ['size', 'num_faces', 'height', 'add_numbers', 'number_scale',
                            'number_depth', 'number_h_offset', 'number_v_offset', 'font_path'] + _indicator_props +
                            ['custom_image_path', 'custom_image_face', 'custom_image_scale', 'use_critical_face_material', 'critical_face_material'],
            'D12': ['size', 'add_numbers', 'number_scale', 'number_depth', 'number_h_offset', 'number_v_offset', 'font_path'] + _indicator_props +
                    ['custom_image_path', 'custom_image_face', 'custom_image_scale', 'use_critical_face_material', 'critical_face_material'],
            'D20': ['size', 'add_numbers', 'number_scale', 'number_depth', 'number_h_offset', 'number_v_offset', 'font_path'] + _indicator_props +
                    ['custom_image_path', 'custom_image_face', 'custom_image_scale', 'use_critical_face_material', 'critical_face_material'],
            'CUSTOM_CRYSTAL': ['size', 'num_faces', 'base_height', 'top_point_height', 'bottom_point_height', 'add_numbers',
                              'number_scale', 'number_depth', 'number_h_offset', 'number_v_offset', 'font_path'] + _indicator_props +
                              ['custom_image_path', 'custom_image_face', 'custom_image_scale', 'use_critical_face_material', 'critical_face_material'],
            'CUSTOM_SHARD': ['size', 'num_faces', 'top_point_height', 'bottom_point_height',
                            'add_numbers', 'number_scale', 'number_depth', 'number_h_offset', 'number_v_offset', 'font_path'] + _indicator_props +
                            ['custom_image_path', 'custom_image_face', 'custom_image_scale', 'use_critical_face_material', 'critical_face_material'],
            'CUSTOM_BIPYRAMID': ['size', 'num_faces', 'top_point_height', 'bottom_point_height',
                                'add_numbers', 'number_scale', 'number_depth', 'number_h_offset', 'number_v_offset', 'font_path'] + _indicator_props +
                                ['custom_image_path', 'custom_image_face', 'custom_image_scale', 'use_critical_face_material', 'critical_face_material'],
        }

        # Always show dice finish first
        layout.prop(self, "dice_finish")
        if self.dice_finish == "bumpers":
            layout.prop(self, "bumper_scale")

        # Get relevant properties for this dice type
        relevant_props = property_relevance.get(self.dice_type, [])

        # Clamp face counts for dice types that require even counts and a minimum of 6
        if self.dice_type in ['CUSTOM_TRAP', 'CUSTOM_BIPYRAMID']:
            if self.num_faces < 6:
                self.num_faces = 6
            if self.num_faces % 2 != 0:
                self.num_faces += 1

        # Draw properties in order
        for prop_name in relevant_props:
            if hasattr(self, prop_name):
                # Special handling for number indicator properties
                if prop_name == 'number_indicator_type':
                    supports_indicators = supports_number_indicators(self.dice_type, self.num_faces)
                    if self.add_numbers and supports_indicators:
                        layout.prop(self, prop_name)
                elif prop_name in ['period_indicator_scale', 'period_indicator_space']:
                    supports_indicators = supports_number_indicators(self.dice_type, self.num_faces)
                    if self.add_numbers and supports_indicators and self.number_indicator_type == 'period':
                        layout.prop(self, prop_name)
                elif prop_name in ['bar_indicator_height', 'bar_indicator_width', 'bar_indicator_space', 'center_bar']:
                    supports_indicators = supports_number_indicators(self.dice_type, self.num_faces)
                    if self.add_numbers and supports_indicators and self.number_indicator_type == 'bar':
                        layout.prop(self, prop_name)
                elif prop_name in ['dot_indicator_scale', 'dot_indicator_space']:
                    supports_indicators = supports_number_indicators(self.dice_type, self.num_faces)
                    if self.add_numbers and supports_indicators and self.number_indicator_type == 'dot':
                        layout.prop(self, prop_name)
                else:
                    layout.prop(self, prop_name)

        layout.separator()
        layout.prop(self, "add_fin_supports")
        if self.add_fin_supports:
            layout.prop(self, "fin_support_contour_offset")
            layout.prop(self, "fin_support_connection_thickness")
            layout.prop(self, "fin_support_thickness")
            layout.prop(self, "fin_support_drop")
            layout.prop(self, "fin_support_raft_margin")
            layout.prop(self, "fin_support_raft_thickness")
            layout.prop(self, "fin_support_raft_taper")

    def invoke(self, context, event):
        """Initialize operator properties from presets when invoked"""
        presets = context.scene.dicegen_presets

        # Copy values from presets
        self.dice_finish = presets.dice_finish
        self.bumper_scale = presets.bumper_scale
        self.size = presets.size
        self.add_fin_supports = presets.add_fin_supports
        self.fin_support_contour_offset = presets.fin_support_contour_offset
        self.fin_support_connection_thickness = presets.fin_support_connection_thickness
        self.fin_support_thickness = presets.fin_support_thickness
        self.fin_support_drop = presets.fin_support_drop
        self.fin_support_raft_margin = presets.fin_support_raft_margin
        self.fin_support_raft_thickness = presets.fin_support_raft_thickness
        self.fin_support_raft_taper = presets.fin_support_raft_taper
        self.add_numbers = presets.add_numbers
        self.number_scale = presets.number_scale
        self.number_depth = presets.number_depth
        self.font_path = presets.font_path
        self.number_indicator_type = presets.number_indicator_type
        self.period_indicator_scale = presets.period_indicator_scale
        self.period_indicator_space = presets.period_indicator_space
        self.bar_indicator_height = presets.bar_indicator_height
        self.bar_indicator_width = presets.bar_indicator_width
        self.bar_indicator_space = presets.bar_indicator_space
        self.center_bar = presets.center_bar
        self.dot_indicator_scale = presets.dot_indicator_scale
        self.dot_indicator_space = presets.dot_indicator_space
        self.custom_image_path = presets.custom_image_path
        self.custom_image_scale = presets.custom_image_scale
        self.use_critical_face_material = presets.use_critical_face_material
        self.critical_face_material = presets.critical_face_material
        self.number_center_offset = presets.number_center_offset
        self.base_height = presets.base_height
        self.point_height = presets.point_height
        self.top_point_height = presets.top_point_height
        self.bottom_point_height = presets.bottom_point_height
        self.height = presets.height
        self.num_faces = presets.num_faces
        self.number_h_offset = presets.number_h_offset

        # Default height for custom trapezohedron set to 1.0
        if self.dice_type == 'CUSTOM_TRAP':
            self.height = 1.0

        # Set number_v_offset based on dice type
        # Shard-type dice use 0.75, D10/D100 use 0.33, custom trapezohedron uses 0.0, all others use 0.0
        if self.dice_type in ['D4_SHARD', 'CUSTOM_SHARD']:
            self.number_v_offset = presets.number_v_offset_d4_shard  # 0.75
        elif self.dice_type in ['D10', 'D100']:
            self.number_v_offset = presets.number_v_offset  # 0.33
        elif self.dice_type == 'CUSTOM_TRAP':
            self.number_v_offset = 0.0
        else:
            self.number_v_offset = 0.0  # D4, D6, D8, D12, D20, D4_CRYSTAL, CUSTOM_CRYSTAL

        # Set point heights based on dice type
        # Crystal dice use absolute mm (7mm default), shards use relative multipliers (0.75, 1.75)
        if self.dice_type in ['D4_SHARD', 'CUSTOM_SHARD']:
            # For shards, use relative multiplier defaults
            self.top_point_height = presets.top_point_height_shard
            self.bottom_point_height = presets.bottom_point_height_shard
        elif self.dice_type == 'CUSTOM_BIPYRAMID':
            # Dedicated defaults for bipyramid (8 faces, symmetric points)
            self.num_faces = 8
            self.top_point_height = 2
            self.bottom_point_height = 2
        elif self.dice_type == 'CUSTOM_TRAP':
            # Defaults for custom trapezohedron
            self.num_faces = 10

        # Set custom_image_face based on dice type (highest face)
        dice_face_map = {
            'D4': 4,
            'D4_CRYSTAL': 4,
            'D4_SHARD': 4,
            'D6': 6,
            'D8': 8,
            'D10': 10,
            'D12': 12,
            'D20': 20,
            'D100': 10,  # D100 uses same faces as D10
            'CUSTOM_TRAP': self.num_faces,
            'CUSTOM_CRYSTAL': self.num_faces,
            'CUSTOM_SHARD': self.num_faces,
            'CUSTOM_BIPYRAMID': self.num_faces,  # num_faces now represents total face count
        }
        self.custom_image_face = dice_face_map.get(self.dice_type, presets.custom_image_face)

        # Enforce even face count and minimum 6 (total faces)
        if self.dice_type in ['CUSTOM_TRAP', 'CUSTOM_BIPYRAMID']:
            if self.num_faces < 6:
                self.num_faces = 6
            if self.num_faces % 2 != 0:
                self.num_faces += 1
        elif self.dice_type in ['CUSTOM_CRYSTAL', 'CUSTOM_SHARD']:
            if self.num_faces < 3:
                self.num_faces = 3

        return self.execute(context)

    def execute(self, context):
        # Map dice type to mesh class and generator params
        dice_map = {
            'D4': (Tetrahedron, 'd4', {'number_center_offset': self.number_center_offset, 'number_h_offset': self.number_h_offset, 'number_v_offset': self.number_v_offset}),
            'D4_CRYSTAL': (D4Crystal, 'd4Crystal', {'base_height': self.base_height, 'top_point_height': self.top_point_height, 'bottom_point_height': self.bottom_point_height, 'number_h_offset': self.number_h_offset, 'number_v_offset': self.number_v_offset}),
            'D4_SHARD': (D4Shard, 'd4Shard', {'top_point_height': self.top_point_height, 'bottom_point_height': self.bottom_point_height, 'number_v_offset': self.number_v_offset, 'number_h_offset': self.number_h_offset}),
            'CUSTOM_CRYSTAL': (CustomCrystal, 'customCrystal', {'num_faces': self.num_faces, 'base_height': self.base_height, 'top_point_height': self.top_point_height, 'bottom_point_height': self.bottom_point_height, 'number_h_offset': self.number_h_offset, 'number_v_offset': self.number_v_offset}),
            'CUSTOM_SHARD': (CustomShard, 'customShard', {'num_faces': self.num_faces, 'top_point_height': self.top_point_height, 'bottom_point_height': self.bottom_point_height, 'number_v_offset': self.number_v_offset, 'number_h_offset': self.number_h_offset}),
            'CUSTOM_BIPYRAMID': (CustomBipyramid, 'customBipyramid', {'num_faces': self.num_faces, 'top_point_height': self.top_point_height, 'bottom_point_height': self.bottom_point_height, 'number_h_offset': self.number_h_offset, 'number_v_offset': self.number_v_offset}),
            'D6': (Cube, 'd6', {'number_h_offset': self.number_h_offset, 'number_v_offset': self.number_v_offset}),
            'D8': (Octahedron, 'd8', {'number_h_offset': self.number_h_offset, 'number_v_offset': self.number_v_offset}),
            'D10': (D10Mesh, 'd10', {'height': self.height, 'number_v_offset': self.number_v_offset, 'number_h_offset': self.number_h_offset}),
            'D12': (Dodecahedron, 'd12', {'number_h_offset': self.number_h_offset, 'number_v_offset': self.number_v_offset}),
            'D20': (Icosahedron, 'd20', {'number_h_offset': self.number_h_offset, 'number_v_offset': self.number_v_offset}),
            'D100': (D100Mesh, 'd100', {'height': self.height, 'number_v_offset': self.number_v_offset, 'number_h_offset': self.number_h_offset}),
            'CUSTOM_TRAP': (CustomTrapezohedron, 'customTrapezohedron', {'num_faces': self.num_faces, 'height': self.height, 'number_v_offset': self.number_v_offset, 'number_h_offset': self.number_h_offset}),
        }

        if self.dice_type not in dice_map:
            self.report({'ERROR'}, f"Unknown dice type: {self.dice_type}")
            return {'CANCELLED'}

        mesh_class, name_prefix, extra_params = dice_map[self.dice_type]

        # Create the mesh
        mesh = mesh_class("dice_body", self.size, **extra_params)
        mesh.apply_print_layout(self.fin_support_drop if self.add_fin_supports else 0.0)
        dice_obj = mesh.create(context)

        # Apply dice finish
        configure_dice_finish_modifier(dice_obj, self.dice_finish, self.bumper_scale)
        body_material = ensure_material("Dice Body", (0.95, 0.95, 0.9, 1))
        assign_material(dice_obj, body_material)
        clear_panel_artifacts(dice_obj)
        clear_fin_support_artifacts(dice_obj)
        remove_modifier_if_exists(dice_obj, 'boolean')
        if "dice_numbers_name" in dice_obj:
            del dice_obj["dice_numbers_name"]

        font_path = validate_font_path(self.font_path) if self.font_path else ''
        custom_image_path = validate_svg_path(self.custom_image_path) if self.custom_image_path else ''

        indicator_type = NUMBER_IND_NONE
        if supports_number_indicators(self.dice_type, self.num_faces):
            indicator_type = self.number_indicator_type

        # Collect settings for saving
        settings_values = {}
        for attr in SETTINGS_ATTRS:
            if hasattr(self, attr):
                settings_values[attr] = getattr(self, attr)
        settings_values["font_path"] = font_path
        settings_values["custom_image_path"] = custom_image_path

        numbers_objects = []
        if self.add_numbers:
            numbers_objects = create_numbers_object_for_mesh(
                context,
                mesh,
                self.size,
                self.number_scale,
                self.number_depth,
                font_path,
                indicator_type,
                self.period_indicator_scale,
                self.period_indicator_space,
                self.bar_indicator_height,
                self.bar_indicator_width,
                self.bar_indicator_space,
                self.center_bar,
                custom_image_face=self.custom_image_face,
                custom_image_path=custom_image_path,
                custom_image_scale=self.custom_image_scale,
                use_critical_face_material=self.use_critical_face_material,
                critical_face_material=tuple(self.critical_face_material),
                dot_indicator_scale=self.dot_indicator_scale,
                dot_indicator_space=self.dot_indicator_space,
            )

            for idx, num_obj in enumerate(numbers_objects):
                num_obj.name = "dice_numbers" if idx == 0 else "dice_numbers_critical"
                mod_name = 'boolean' if idx == 0 else 'boolean_critical'
                remember = 'dice_numbers_name' if idx == 0 else 'dice_critical_numbers_name'
                apply_boolean_modifier(dice_obj, num_obj, modifier_name=mod_name, remember_key=remember)
                num_obj["dice_body_name"] = dice_obj.name

        fin_support_object = generate_fin_supports(
            context,
            dice_obj,
            mesh.get_output_vertices(),
            mesh.faces,
            settings_values,
        )
        if self.add_fin_supports and fin_support_object is None:
            self.report({'WARNING'}, "Could not build fin supports for this die.")

        # Store metadata
        target_object = numbers_objects[0] if numbers_objects else dice_obj
        dice_obj["dice_gen_type"] = mesh_class.__name__
        target_object["dice_gen_type"] = mesh_class.__name__

        # Store settings on the object
        apply_settings(dice_obj.dice_gen_settings, settings_values)
        apply_settings(target_object.dice_gen_settings, settings_values)

        dice_collection = create_dice_collection(context, get_dice_type_label(self.dice_type))
        extra_objs = list(numbers_objects)
        if fin_support_object is not None:
            extra_objs.append(fin_support_object)
        organize_dice_objects_in_collection(
            dice_obj,
            dice_collection,
            extra_objects=extra_objs,
        )

        return {'FINISHED'}


class VIEW3D_PT_dice_gen_sidebar(bpy.types.Panel):
    """DiceGen panel in 3D viewport sidebar (N panel)"""
    bl_label = "DiceGen5"
    bl_idname = "VIEW3D_PT_dice_gen_sidebar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'DiceGen5'

    def draw(self, context):
        layout = self.layout
        presets = context.scene.dicegen_presets

        # Dice Finish Settings
        box = layout.box()
        box.label(text="Dice Finish", icon='MOD_SUBSURF')
        box.prop(presets, "dice_finish")
        if presets.dice_finish == "bumpers":
            box.prop(presets, "bumper_scale")

        # Size Settings
        box = layout.box()
        box.label(text="Size", icon='EMPTY_ARROWS')
        box.prop(presets, "size")

        # Number Settings
        box = layout.box()
        box.label(text="Numbers", icon='OUTLINER_OB_FONT')
        box.prop(presets, "add_numbers")
        if presets.add_numbers:
            box.prop(presets, "number_scale")
            box.prop(presets, "number_depth")
            box.prop(presets, "font_path")
            box.prop(presets, "use_critical_face_material")
            if presets.use_critical_face_material:
                box.prop(presets, "critical_face_material")

            box.label(text="Number Indicators:")
            box.prop(presets, "number_indicator_type")
            if presets.number_indicator_type == NUMBER_IND_PERIOD:
                box.prop(presets, "period_indicator_scale")
                box.prop(presets, "period_indicator_space")
            elif presets.number_indicator_type == NUMBER_IND_BAR:
                box.prop(presets, "bar_indicator_height")
                box.prop(presets, "bar_indicator_width")
                box.prop(presets, "bar_indicator_space")
                box.prop(presets, "center_bar")
            elif presets.number_indicator_type == NUMBER_IND_DOT:
                box.prop(presets, "dot_indicator_scale")
                box.prop(presets, "dot_indicator_space")

        # Custom Image Settings
        box = layout.box()
        box.label(text="Custom Image", icon='IMAGE_DATA')
        box.prop(presets, "custom_image_path")
        if presets.custom_image_path:
            box.prop(presets, "custom_image_scale")
            box.label(text="(Image will appear on highest face)", icon='INFO')

        box = layout.box()
        box.label(text="Fin Supports", icon='MOD_SOLIDIFY')
        box.prop(presets, "add_fin_supports")
        if presets.add_fin_supports:
            box.prop(presets, "fin_support_contour_offset")
            box.prop(presets, "fin_support_connection_thickness")
            box.prop(presets, "fin_support_thickness")
            box.prop(presets, "fin_support_drop")
            box.prop(presets, "fin_support_raft_margin")
            box.prop(presets, "fin_support_raft_thickness")
            box.prop(presets, "fin_support_raft_taper")

        # Dice Type Buttons
        layout.separator()
        box = layout.box()
        box.label(text="Unity Export", icon='EXPORT')
        box.label(text="Select dice bodies, then export:")
        row = box.row()
        row.operator("dicegen.export_unity_ready", text="Export Selected as FBX")
        box.label(text="Output: //exports/unity/", icon='FILE_FOLDER')

        layout.separator()
        box = layout.box()
        box.label(text="Add Dice to Scene", icon='CUBE')

        col = box.column(align=True)
        op = col.operator("dicegen.add_from_preset", text="D4 Tetrahedron")
        op.dice_type = 'D4'

        op = col.operator("dicegen.add_from_preset", text="D4 Crystal")
        op.dice_type = 'D4_CRYSTAL'

        op = col.operator("dicegen.add_from_preset", text="D4 Shard")
        op.dice_type = 'D4_SHARD'

        op = col.operator("dicegen.add_from_preset", text="D6 Cube")
        op.dice_type = 'D6'

        op = col.operator("dicegen.add_from_preset", text="D8 Octahedron")
        op.dice_type = 'D8'

        op = col.operator("dicegen.add_from_preset", text="D10 Trapezohedron")
        op.dice_type = 'D10'

        op = col.operator("dicegen.add_from_preset", text="D12 Dodecahedron")
        op.dice_type = 'D12'

        op = col.operator("dicegen.add_from_preset", text="D20 Icosahedron")
        op.dice_type = 'D20'

        op = col.operator("dicegen.add_from_preset", text="D100 Trapezohedron")
        op.dice_type = 'D100'

        col.separator()

        op = col.operator("dicegen.add_from_preset", text="Custom Crystal")
        op.dice_type = 'CUSTOM_CRYSTAL'

        op = col.operator("dicegen.add_from_preset", text="Custom Shard")
        op.dice_type = 'CUSTOM_SHARD'

        op = col.operator("dicegen.add_from_preset", text="Custom Bipyramid")
        op.dice_type = 'CUSTOM_BIPYRAMID'

        op = col.operator("dicegen.add_from_preset", text="Custom Trapezohedron")
        op.dice_type = 'CUSTOM_TRAP'


classes = [
    DiceGenSettings,
    DiceGenPresets,
    MeshDiceAdd,
    # Old individual operators removed - Add Mesh menu now uses DICE_OT_add_from_preset
    # D4Generator,
    # D4CrystalGenerator,
    # D4ShardGenerator,
    # CustomCrystalGenerator,
    # CustomShardGenerator,
    # D6Generator,
    # D8Generator,
    # D10Generator,
    # D100Generator,
    # D12Generator,
    # D20Generator,
    OBJECT_OT_dice_gen_update,
    OBJECT_PT_dice_gen,
    DICE_OT_add_from_preset,  # Single unified operator for all dice generation
    DICE_OT_export_unity_ready,
    VIEW3D_PT_dice_gen_sidebar
]


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)

    bpy.types.Object.dice_gen_settings = PointerProperty(type=DiceGenSettings)
    bpy.types.Scene.dicegen_presets = PointerProperty(type=DiceGenPresets)

    # Add "Dice" menu to the "Add Mesh" menu
    bpy.types.VIEW3D_MT_mesh_add.append(menu_func)


def unregister():
    # Remove "Dice" menu from the "Add Mesh" menu.
    bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)

    del bpy.types.Object.dice_gen_settings
    del bpy.types.Scene.dicegen_presets

    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
