"""
kr_inspect - CS2 karambit inspect on the blocky R15 hand (4.6 s).

Reference: CS2 karambit inspect, ref frames f_0016-f_0085 (ref_specs/karambit_inspect.md).
No fingers exist, so the finger actions become knife + wrist motion:

  * "index finger" = an invisible axle sticking out of the hand block's distal
    face at its radial (thumb-side) edge (HANG_RING).  When the hand "opens"
    the knife slides off the grip onto that axle: its ring axis turns from
    palmar (grip) to distal, so the karambit spins in the plane just past the
    end of the hand block and never cuts through it.  The axle points up-left
    and ~40 deg into the scene, so the spin is foreshortened like CS2 (it
    comes towards the camera on the left and passes behind the hand on the
    right) instead of a flat screen-plane wheel.
  * "fingers close" = the ring slides back onto the radial face and the
    handle re-enters the hand block (ring axis back to palmar).

Beats (t in s, CS2 frame in brackets):
  0.00-0.13  cock: fist rolls ~22 deg CW on screen (ring end up), dips      [16-18]
  0.06-0.20  open + drop: knife slides onto the axle and hangs down         [18-19]
  0.20-0.27  launch: hand snaps up-right and supinates ~100 deg             [19-20]
  0.22-0.60  spin 1: one CW turn (~1050 deg/s), hand arcs to an apex at 0.40
             and dips into the catch                                        [20-25]
  0.60-0.73  catch: hard stop, ring seats back on the hand (+tiny recoil)   [25-27]
  0.73-1.00  present: fist rises, turns the flat broadside (strong ease-out)[27-31]
  1.00-1.60  settle creep into the display pose                             [31-40]
  1.60-3.33  display hold: blade broadside, ring on top, +-1 deg micro roll [40-66]
  3.33-3.56  release: anticipation sink, grip loosens, knife pivots tip-down[66-69]
  3.56-3.80  flick right to the screen edge and back up (launches spin 2)   [69-73]
  3.56-4.07  spin 2: one CCW turn (~900 deg/s), climbs behind the hand,
             over the top, down on the camera side                          [73-77]
  4.07-4.20  catch 2 + pronate back into the idle reverse grip (upper right)[77-79]
  4.20-4.60  glide diagonally down-left into idle, soft settle              [79-85]

Markers: Sound spin (0.22, 3.56), Sound catch (0.60, 4.08).
Camera: ~0.2-0.3 deg kicks on the launch, catches and flick, back to zero.
"""

import math

from mathutils import Euler, Vector

from .. import poses as PZ
from ... import skeleton as SK
from ..core import Anim
from . import common as C

LENGTH = 4.6
DT = 1.0 / 60.0

# ---------------------------------------------------------------------------
# hand key poses (viewmodel studs / deg).  Solved offline for a straight-ish
# wrist (|flex|, |dev| <= 12 deg): the elbow pole and a shoulder offset bring
# the forearm in from the lower right while the palm faces the camera.
# ---------------------------------------------------------------------------
H = {
    "cock": dict(pos=(1.020, 2.750, -1.300), rot=(53.0, 6.5, 67.2), elbow=(0.500, 0.000, -0.400), shoulder=(0.000, -0.300, 0.250)),
    "drop": dict(pos=(1.070, 2.730, -1.420), rot=(49.1, 17.4, 77.2), elbow=(0.500, 0.000, -0.400), shoulder=(0.000, -0.300, 0.200)),
    "launch": dict(pos=(1.270, 2.550, -0.857), rot=(9.2, 37.0, -22.4), elbow=(-0.020, -0.025, 0.051), shoulder=(0.017, -0.293, 0.259)),
    "apex": dict(pos=(1.715, 2.600, -0.437), rot=(9.2, 37.0, -11.5), elbow=(-0.017, -0.020, 0.032), shoulder=(0.364, -0.199, 0.508)),
    "fall": dict(pos=(1.683, 2.600, -0.546), rot=(9.2, 37.0, -13.7), elbow=(-0.019, -0.022, 0.039), shoulder=(0.323, -0.208, 0.456)),
    "catch": dict(pos=(1.555, 2.550, -0.714), rot=(9.2, 37.0, -17.6), elbow=(-0.020, -0.025, 0.047), shoulder=(0.209, -0.243, 0.365)),
    "present": dict(pos=(1.225, 2.400, -0.336), rot=(26.2, 58.5, -8.4), elbow=(-0.002, -0.011, 0.008), shoulder=(0.155, -0.226, 0.382)),
    "display": dict(pos=(1.170, 2.350, -0.197), rot=(44.7, 81.5, 9.8), elbow=(0.006, -0.015, 0.008), shoulder=(0.134, -0.181, 0.369)),
    "sink": dict(pos=(1.225, 2.400, -0.336), rot=(52.2, 83.9, 13.7), elbow=(0.015, -0.022, 0.014), shoulder=(0.107, -0.189, 0.316)),
    "hang2": dict(pos=(1.780, 2.600, -0.510), rot=(9.2, 37.0, -12.5), elbow=(-0.019, -0.023, 0.040), shoulder=(0.389, -0.199, 0.489)),
    "flick": dict(pos=(2.395, 2.600, -0.401), rot=(9.2, 37.0, -8.1), elbow=(-0.014, -0.021, 0.039), shoulder=(0.911, -0.148, 0.669)),
    "ret": dict(pos=(1.942, 2.600, -0.218), rot=(9.2, 37.0, -6.6), elbow=(-0.023, -0.024, 0.038), shoulder=(0.567, -0.171, 0.681)),
    "drift": dict(pos=(1.780, 2.600, -0.309), rot=(9.2, 37.0, -8.9), elbow=(-0.018, -0.020, 0.030), shoulder=(0.431, -0.186, 0.586)),
    "drift2": dict(pos=(1.651, 2.600, -0.419), rot=(9.2, 37.0, -11.5), elbow=(-0.016, -0.019, 0.028), shoulder=(0.330, -0.202, 0.504)),
    "snap": dict(pos=(2.136, 2.600, -0.401), rot=(9.2, 37.0, -9.1), elbow=(-0.019, -0.023, 0.043), shoulder=(0.681, -0.167, 0.620)),
    "close": dict(pos=(2.136, 2.600, -0.364), rot=(24.6, 34.5, 40.5), elbow=(-0.014, -0.034, 0.046), shoulder=(0.625, -0.151, 0.546)),
    "regrip": dict(pos=(1.913, 2.650, -0.520), rot=(40.0, 32.0, 90.0), elbow=(0.002, -0.031, 0.033), shoulder=(0.325, -0.162, 0.355)),
}
IDLE_H = dict(pos=C.IDLE["R_pos"], rot=C.IDLE["R_rot"], elbow=C.IDLE["R_elbow"], shoulder=C.IDLE["R_shoulder"])

# ---------------------------------------------------------------------------
# knife states (hand semantic frame)
# ---------------------------------------------------------------------------
HANG_RING = (0.45, 0.22, 0.0)          # ring on the invisible index finger
DGRIP = dict(pos=(0.62, -0.02, 0.10), rot=C.grip_rot(0.0, 0.0, 0.0))   # display grip: ring hole + flat to camera


def hang_euler(s, theta):
    """knife on the axle: ring axis = s * distal, handle ulnar at theta = 0;
    theta is a spin about the ring axis (rot X)."""
    e = PZ.axes_euler((0.0, float(s), 0.0), (-1.0, 0.0, 0.0))
    return (e[0] + theta, e[1], e[2])


def _q(e):
    return Euler([math.radians(x) for x in e], "XYZ").to_quaternion()


def _e(q, prev):
    compat = Euler([math.radians(x) for x in prev], "XYZ")
    return tuple(math.degrees(x) for x in q.to_euler("XYZ", compat))


def _lerp(a, b, w):
    return tuple(x + (y - x) * w for x, y in zip(a, b))


def _smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def _out(u, p=3.0):
    u = min(max(u, 0.0), 1.0)
    return 1 - (1 - u) ** p


def _in(u, p=2.0):
    u = min(max(u, 0.0), 1.0)
    return u ** p


def _hermite(t, t0, t1, p0, p1, v0, v1):
    h = t1 - t0
    u = (t - t0) / h
    u2, u3 = u * u, u * u * u
    return ((2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * h * v0
            + (-2 * u3 + 3 * u2) * p1 + (u3 - u2) * h * v1)


# ---------------------------------------------------------------------------
def key_hand(a, t, p, interp="smooth", tangent="auto"):
    a.hand("R", t, pos=p["pos"], rot=p["rot"], elbow=p["elbow"], shoulder=p["shoulder"], interp=interp, tangent=tangent)


def blend(p0, p1, w):
    return {k: _lerp(p0[k], p1[k], w) for k in ("pos", "rot", "elbow", "shoulder")}


def offset(p, dpos=(0, 0, 0), drot=(0, 0, 0)):
    q = dict(p)
    q["pos"] = tuple(x + d for x, d in zip(p["pos"], dpos))
    q["rot"] = tuple(x + d for x, d in zip(p["rot"], drot))
    return q


def build():
    a = Anim("kr_inspect", "karambit", length=LENGTH,
             description="Karambit inspect: CS2 finger-ring spin, broadside display hold, counter spin and catch")
    C.key_idle(a, 0.0)

    # ---------------- right hand ------------------------------------------
    key_hand(a, 0.09, H["cock"])
    key_hand(a, 0.17, H["drop"])
    key_hand(a, 0.267, H["launch"])
    key_hand(a, 0.40, H["apex"], tangent="flat")
    key_hand(a, 0.50, H["fall"])
    key_hand(a, 0.60, H["catch"], tangent="flat")
    key_hand(a, 0.73, offset(H["catch"], dpos=(-0.06, -0.02, 0.03), drot=(2, 4, 4)))
    key_hand(a, 0.87, blend(H["present"], H["display"], 0.35))
    key_hand(a, 1.00, blend(H["present"], H["display"], 0.9))
    key_hand(a, 1.60, H["display"], tangent="flat")
    # display hold: micro roll +-1 deg (period 1.6 s) + breath-level drift
    t = 1.8
    while t < 3.2:
        ph = 2 * math.pi * (t - 1.6) / 1.6
        key_hand(a, t, offset(H["display"], dpos=(0.0, 0.0, 0.006 * math.sin(ph + 1.0)),
                             drot=(0.4 * math.sin(ph + 0.5), 0.0, 1.0 * math.sin(ph))))
        t += 0.2
    key_hand(a, 3.33, H["display"], tangent="flat")
    key_hand(a, 3.40, offset(H["display"], dpos=(0.0, 0.0, -0.025), drot=(2, 0, 0)))
    key_hand(a, 3.48, H["sink"])
    key_hand(a, 3.56, blend(H["sink"], H["hang2"], 0.55))
    key_hand(a, 3.62, H["hang2"])
    key_hand(a, 3.70, H["flick"], tangent="flat")
    key_hand(a, 3.73, offset(H["flick"], dpos=(0.02, 0.0, 0.03)), tangent="flat")
    key_hand(a, 3.80, H["ret"], tangent="flat")
    key_hand(a, 3.93, H["drift"])
    key_hand(a, 4.00, H["drift2"])
    key_hand(a, 4.067, H["snap"])
    key_hand(a, 4.13, H["close"])
    key_hand(a, 4.20, H["regrip"])
    key_hand(a, 4.33, blend(H["regrip"], IDLE_H, 0.78))
    C.key_settle(a, 4.46, LENGTH, dpos=(-0.01, 0.0, -0.025), drot=(-1.5, 0.0, 1.0))
    C.key_left_hidden(a, LENGTH)

    # ---------------- knife track (dense keys, 60 fps) ----------------------
    def hand_R(t):
        W = SK.evaluate(a.controls(t), a.knife_rot_order, "karambit")
        return SK.hand_semantic_frame(W).to_3x3()

    def theta_down(t, s, ref):
        B = SK.euler_matrix(hang_euler(s, 0.0))
        R = hand_R(t) @ B
        y, z = R.col[1], R.col[2]
        th = math.degrees(math.atan2(-z.z, -y.z))
        return th + 360.0 * round((ref - th) / 360.0)

    def down_track(s, t_lo, t_hi):
        """theta (deg, unwrapped) that lets the knife hang straight down from the axle."""
        d, ref = {}, 0.0
        for i in range(int(round(t_lo / DT)) - 1, int(round(t_hi / DT)) + 2):
            ref = theta_down(i * DT, s, ref)
            d[i] = ref
        return d

    def make_theta(d, ta, tb, tc, th_end_fn, stop_tau):
        """knife angle on the axle: hangs (d) until ta, the flick accelerates it
        (uniformly, relative to hanging) until tb, then a constant-rate spin that
        reaches th_end at tc, then a hard stop with a few degrees of recoil."""
        ib = int(round(tb / DT))
        thb, vb = d[ib], (d[ib + 1] - d[ib - 1]) / (2 * DT)
        th_end = th_end_fn(thb)
        w = (thb - th_end) / ((tc - tb) + 0.5 * (tb - ta))
        phib = th_end + w * (tc - tb) - thb
        stop_amp = w * stop_tau / math.e

        def theta(t):
            i = int(round(t / DT))
            if t <= ta:
                return d[i]
            if t <= tb:
                return d[i] + _hermite(t, ta, tb, 0.0, phib, 0.0, -w - vb)
            if t <= tc:
                return th_end + w * (tc - t)
            u = t - tc
            return th_end - stop_amp * (u / stop_tau) * math.exp(1.0 - u / stop_tau)
        return theta, dict(thb=round(thb, 1), vb=round(vb), th_end=round(th_end, 1), w=round(w))

    # spin 1: knife on the axle with ring axis = -distal, theta decreasing = CW on screen;
    # ends a full turn later with the handle ulnar (theta = 0 mod 360) -> straight into the grip
    T_A1, T_B1, T_C1 = 0.21, 0.29, 0.60
    d1 = down_track(-1, 0.05, 0.32)
    theta1, info1 = make_theta(d1, T_A1, T_B1, T_C1, lambda thb: 360.0 * round((thb - 390.0) / 360.0), 0.03)
    # spin 2: ring axis = +distal, theta decreasing = CCW on screen; ends hanging straight down
    T_R0, T_R1 = 3.33, 3.56
    T_A2, T_B2, T_C2 = 3.54, 3.66, 4.067
    d2 = down_track(+1, 3.28, 4.30)
    dC2 = d2[int(round(T_C2 / DT))]
    theta2, info2 = make_theta(d2, T_A2, T_B2, T_C2, lambda thb: dC2 + 360.0 * round((thb - 385.0 - dC2) / 360.0), 0.03)

    GRIP_P, GRIP_R = C.GRIP["pos"], C.GRIP["rot"]
    DG_P, DG_R = DGRIP["pos"], DGRIP["rot"]

    def knife_state(t):
        """-> (pos, quaternion) of the knife link in the hand frame."""
        if t < 0.06:
            return GRIP_P, _q(GRIP_R)
        if t < T_C1:                       # open: grip -> axle, hang, launch, spin 1
            qh = _q(hang_euler(-1, theta1(t)))
            w = _smooth((t - 0.06) / 0.14)
            if w >= 1.0:
                return HANG_RING, qh
            return _lerp(GRIP_P, HANG_RING, w), _q(GRIP_R).slerp(qh, w)
        if t < 3.0:                        # catch 1: ring back on the hand, flat to camera
            qh = _q(hang_euler(-1, theta1(t)))
            w = _out((t - T_C1) / 0.12, 3.0)
            wp = _out((t - T_C1) / 0.14, 2.0)
            return _lerp(HANG_RING, DG_P, wp), qh.slerp(_q(DG_R), w)
        if t < T_R0:
            return DG_P, _q(DG_R)
        if t < T_C2:                       # release onto the axle, flick, spin 2
            qh = _q(hang_euler(+1, theta2(t)))
            w = _in((t - T_R0) / (T_R1 - T_R0), 1.6)
            return _lerp(DG_P, HANG_RING, w), _q(DG_R).slerp(qh, w)
        qh = _q(hang_euler(+1, theta2(t)))  # catch 2 into the idle grip
        w = _out((t - T_C2) / 0.13, 2.5)
        return _lerp(HANG_RING, GRIP_P, w), qh.slerp(_q(GRIP_R), w)

    def emit(t_lo, t_hi, prev, canon_pos, canon_rot):
        """dense keys; the euler stays continuous through the spins (rot X winds
        up by -360 per turn).  At t_hi the knife sits exactly in a grip again, so
        a sub-frame step re-expresses the same orientation with the canonical
        euler (invisible in the 60 fps bake)."""
        n = int(round((t_hi - t_lo) / DT))
        for i in range(n + 1):
            t = t_lo + i * DT
            p, q = knife_state(t)
            e = _e(q, prev)
            prev = e
            a.knife(t, pos=p, rot=e, interp="step" if i == n else "linear")
        a.knife(t_hi + DT, pos=canon_pos, rot=canon_rot, interp="linear")

    emit(0.05, 0.80, GRIP_R, DG_P, DG_R)
    emit(3.30, 4.25, DG_R, GRIP_P, GRIP_R)

    # ---------------- camera: tiny kicks ------------------------------------
    C.key_cam_zero(a, 0.20)
    a.cam(0.26, rot=(0.25, 0.0, -0.20))
    C.key_cam_zero(a, 0.42, interp="out")
    a.cam(0.62, rot=(-0.30, 0.0, 0.15))
    C.key_cam_zero(a, 0.85, interp="out")
    C.key_cam_zero(a, 3.58)
    a.cam(3.68, rot=(0.15, 0.0, -0.30))
    C.key_cam_zero(a, 3.86, interp="out")
    a.cam(4.09, rot=(-0.25, 0.0, 0.20))
    C.key_cam_zero(a, 4.30, interp="out")

    # ---------------- markers ----------------------------------------------
    a.marker(0.22, "Sound", "spin")
    a.marker(0.60, "Sound", "catch")
    a.marker(3.56, "Sound", "spin")
    a.marker(4.08, "Sound", "catch")
    a.debug = dict(spin1=info1, spin2=info2)
    return a
