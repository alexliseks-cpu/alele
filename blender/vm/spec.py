"""
THE CONTRACT shared by the rig, the knife models, the animations and the
Roblox exporter.

The arms are the player's own Roblox R15 avatar arms (RightUpperArm,
RightLowerArm, RightHand, same for Left) - no fingers, no custom arm meshes.
The knife is held by the blocky RightHand: its handle passes through the hand
block exactly like a Roblox tool.

UNITS: the Blender scene is authored in STUDS (1 Blender unit = 1 stud) so it
maps 1:1 to Roblox.  Knife models are modelled in real-world METRES (knife
frames below) and scaled by KNIFE_SCALE so they are proportioned to the R15
hand like a real knife is to a real hand.

Viewmodel space (= Blender armature space, armature object at the origin):
    camera at the origin looking along +Y, +Z up, +X right.
Roblox camera space: camera at the origin looking along -Z, +Y up, +X right.
    roblox(x, y, z) = (x, z, -y)

Bone frames = Roblox joint frames.  Every arm bone's local axes are the axes
of its Roblox part (part +Y runs up the arm towards the shoulder at rest, +X
to the avatar's right, +Z to the avatar's back).  The rest pose is the R15
rest pose: arms hanging straight down, every Motor6D.Transform = identity.

Hand "semantic" frame (used for hand orientation and knife placement):
    +Y distal (out of the bottom of the hand block = where fingers would be)
    +Z palmar (out of the palm face, towards the body at rest)
    +X radial (thumb side, forward at rest) for the RIGHT hand,
       ulnar for the LEFT hand (mirror convention)

Knife frames (all knife bones keep these axes at rest):
    BUTTERFLY  origin = centre between the two pivot pins on the tang,
               +Y towards the blade tip (open knife), +X = blade flat normal,
               +Z = spine side, -Z = sharp edge side.
               Pin A (safe handle, spine side) at (0, 0, +BF_PIN_Z)
               Pin B (bite handle, edge side, carries the latch) at (0, 0, -BF_PIN_Z)
               Open knife: both handles run from their pin towards -Y.
    KARAMBIT   origin = centre of the finger ring, +X = ring axis (flat
               normal), +Y from the ring along the handle towards the blade,
               +Z = spine / back of the handle, -Z = edge side; the hawkbill
               blade curves towards -Z.
"""

FPS = 60                      # bake rate (Roblox keyframes are reduced from this)
STUDS_PER_UNIT = 1.0          # Blender unit -> stud
KNIFE_SCALE = 11.0            # studs per real metre for the knife models

# ----------------------------------------------------------------------------
# R15 block-rig arm (Roblox default proportions, part-local Roblox coords).
# ----------------------------------------------------------------------------
R15 = dict(
    upper_size=(1.0, 1.169, 1.0), lower_size=(1.0, 1.052, 1.0), hand_size=(1.0, 0.3, 1.0),
    torso_size=(2.0, 1.6, 1.0), lower_torso_size=(2.0, 0.4, 1.0),
    torso_shoulder=(1.0, 0.563, 0.0),      # UpperTorso.RightShoulderRigAttachment (x mirrored for left)
    upper_shoulder=(-0.5, 0.42, 0.0),      # RightUpperArm.RightShoulderRigAttachment
    upper_elbow=(0.0, -0.334, 0.0),        # RightUpperArm.RightElbowRigAttachment
    lower_elbow=(0.0, 0.2, 0.0),           # RightLowerArm.RightElbowRigAttachment
    lower_wrist=(0.0, -0.501, 0.0),        # RightLowerArm.RightWristRigAttachment
    hand_wrist=(0.0, 0.125, 0.0),          # RightHand.RightWristRigAttachment
    waist_in_lower=(0.0, 0.2, 0.0),        # LowerTorso.WaistRigAttachment
    waist_in_upper=(0.0, -0.8, 0.0),       # UpperTorso.WaistRigAttachment
)

# Viewmodel placement: UpperTorso centre relative to the camera (Blender
# coords, studs).  Puts the shoulder pivots at (+-1.0, 1.90, -1.69): below
# and in front of the camera, out of view.
UPPER_TORSO_POS = (0.0, 1.90, -2.25)

# Joint limits used only for warnings (deg), hand relative to lower arm.
WRIST_FLEX_LIMIT = 85.0
WRIST_DEV_LIMIT = 45.0

# ----------------------------------------------------------------------------
# Butterfly knife (balisong), knife frame, METRES (scaled by KNIFE_SCALE)
# ----------------------------------------------------------------------------
BF_PIN_Z = 0.0062
BF_PIN_A = (0.0, 0.0, +BF_PIN_Z)     # safe handle pivot (spine side)
BF_PIN_B = (0.0, 0.0, -BF_PIN_Z)     # bite handle pivot (edge side, latch)
BF_HANDLE_LEN = 0.130                # pin -> handle end (towards -Y when open)
BF_HANDLE_FRONT = 0.0075             # handle material ahead of the pin (+Y)
BF_HANDLE_THICK = 0.0136             # X extent of each handle (-T/2 .. +T/2)
BF_HANDLE_WIDTH = 0.0124             # Z extent of each handle (A: 0..W, B: -W..0)
BF_CHANNEL_WIDTH = 0.0038            # X width of the blade groove in each handle
BF_BLADE_LEN = 0.110                 # pin line -> tip
BF_BLADE_HALF_WIDTH = 0.0116         # |Z| max of the blade (fits the closed handles)
BF_BLADE_THICK = 0.0030
BF_TANG_BACK = 0.0085                # tang extends this far behind the pin line
BF_LATCH_PIVOT = (0.0, -(BF_HANDLE_LEN - 0.0065), -0.0055)  # on handle B, knife frame (open)
BF_LATCH_LEN = 0.022
BF_A_CLOSED_DEG = 180.0              # BF_Blade relative to BF_HandleA when a = 1
BF_B_CLOSED_DEG = 180.0              # BF_HandleB relative to BF_Blade when b = 1
BF_LATCH_OPEN_DEG = 150.0            # BF_Latch swing when latch = 1

# ----------------------------------------------------------------------------
# Karambit, knife frame, METRES (scaled by KNIFE_SCALE)
# ----------------------------------------------------------------------------
KR_RING_OUTER_R = 0.0170
KR_RING_INNER_R = 0.0112
KR_RING_THICK = 0.0062               # X extent
KR_HANDLE_START = 0.0150             # handle begins at this Y (overlaps ring)
KR_HANDLE_END = 0.1000               # guard / start of blade at this Y
KR_HANDLE_THICK = 0.0120             # X extent of the handle scales
KR_BLADE_THICK = 0.0042
KR_BLADE_ARC_LEN = 0.0820            # length of the hawkbill blade along its spine
KR_BLADE_CURVE_DEG = 75.0            # how far the blade turns towards -Z

# ----------------------------------------------------------------------------
# Bones (= Roblox part / Pose names), parents first.
# ----------------------------------------------------------------------------
ROOT = "HumanoidRootPart"

ARM_CHAIN = {
    "R": ("RightUpperArm", "RightLowerArm", "RightHand"),
    "L": ("LeftUpperArm", "LeftLowerArm", "LeftHand"),
}
JOINT_NAME = {   # Motor6D names (Roblox R15 convention)
    "CameraBone": "CameraBone", "LowerTorso": "Root", "UpperTorso": "Waist",
    "RightUpperArm": "RightShoulder", "RightLowerArm": "RightElbow", "RightHand": "RightWrist",
    "LeftUpperArm": "LeftShoulder", "LeftLowerArm": "LeftElbow", "LeftHand": "LeftWrist",
    "BF_HandleA": "BF_HandleA", "BF_Blade": "BF_Blade", "BF_HandleB": "BF_HandleB",
    "BF_Latch": "BF_Latch", "KR_Handle": "KR_Handle",
}

BF_BONES = [("BF_HandleA", "RightHand"), ("BF_Blade", "BF_HandleA"),
            ("BF_HandleB", "BF_Blade"), ("BF_Latch", "BF_HandleB")]
KR_BONES = [("KR_Handle", "RightHand")]

BONES = ([(ROOT, None), ("CameraBone", ROOT), ("LowerTorso", ROOT), ("UpperTorso", "LowerTorso"),
          ("RightUpperArm", "UpperTorso"), ("RightLowerArm", "RightUpperArm"), ("RightHand", "RightLowerArm"),
          ("LeftUpperArm", "UpperTorso"), ("LeftLowerArm", "LeftUpperArm"), ("LeftHand", "LeftLowerArm")]
         + BF_BONES + KR_BONES)
BONE_PARENT = dict(BONES)
ARM_BONES = list(ARM_CHAIN["R"] + ARM_CHAIN["L"])
KNIFE_BONES = {"butterfly": [b for b, _ in BF_BONES], "karambit": [b for b, _ in KR_BONES]}
# torso stays at rest so the clips also play on a cloned R15 character
STATIC_BONES = {ROOT, "LowerTorso", "UpperTorso"}


def bones_for(knife):
    keep = {ROOT, "CameraBone", "LowerTorso", "UpperTorso", *ARM_BONES, *KNIFE_BONES[knife]}
    return [b for b, _ in BONES if b in keep]


# Mesh object naming: "<Bone>_Mesh" or "<Bone>_Mesh_<Suffix>".  Knife meshes
# are modelled in the LOCAL frame of their bone (bone head at the origin, knife
# axes) in METRES at rest; the builder scales them by KNIFE_SCALE, places and
# parents them.  Arm preview meshes (R15 blocks) are modelled in studs in the
# part frame and are NOT exported (the avatar's own arms are used in Roblox).
def mesh_bone(mesh_name):
    return mesh_name.split("_Mesh")[0]
