#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
#  mohaa_view.py  -- reconstruct a MOHAA .skd, export .obj, and build a
#  self-contained animated .html viewer (no internet / no dependencies).
#
#  Usage:
#     python3 mohaa_view.py model.skd [--anim base.skc] [--no-open] [--3dviewer]
# ==============================================================================
import sys, os, struct, glob, json, re, webbrowser, math, subprocess, pathlib

def _cap(b,n,rec,what,path):
    """Clamp a count read out of a model header to what the file can physically hold.

    Every count in an SKD/SKB header is attacker-controlled - a .pk3 is just a zip and
    its .skd payload may declare numBone=2147483647. The loops that consume these counts
    advance by an offset that is ALSO read from the file, so a zero/negative advance
    turns the loop into an unbounded allocator (a 4 KB file is enough to hang the
    process). A record needs at least `rec` bytes on disk, so a file of len(b) bytes can
    never legitimately hold more than len(b)//rec of them - anything above that is
    malformed by construction. Bounding by physical file capacity (rather than by the
    retail TIKI_MAX_* constants, tiki_shared.h:76-79) can never reject a real asset,
    including community models that exceed the shipping caps. Mirrors the header sanity
    parse_skc already does before its frame loop."""
    if n<0: return 0
    hi=max(0,len(b)//max(1,rec))
    if n>hi:
        raise ValueError("%s: bad %s count %d - file holds at most %d (truncated or hostile)"
                         %(path,what,n,hi))
    return n

def _i32(b,o): return struct.unpack_from("<i",b,o)[0]
def _f32(b,o): return struct.unpack_from("<f",b,o)[0]
def _cstr(b,o,n):
    # Fixed-width name fields are USUALLY NUL-padded, but not always: the minor_pain
    # animations (weapon_mp44/minor_pain/mp44_stand_hit_head.skc and its siblings) pad their
    # 32-byte channel names with SPACES. Splitting on NUL alone returned "Bip01 pos" plus 23
    # trailing spaces, so every channel lookup missed and those .skc resolved ZERO channels -
    # reported as driving none of the skeleton. Strip trailing padding of either kind; no
    # MOHAA name carries meaningful trailing whitespace.
    return b[o:o+n].split(b"\x00")[0].decode("latin-1","replace").rstrip()
def _cstr_list(b,o,n):  # consecutive NUL-terminated strings within a block (bone/ref names)
    return [x.decode("latin-1","replace") for x in b[o:o+n].split(b"\x00") if x]

def quat_to_mat(q):
    x,y,z,w=q; x,y,z=-x,-y,-z   # MOHAA stores bone rotations as the inverse (conjugate)
    return [[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
            [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
            [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]]
def mat_mul(A,B): return [[sum(A[i][k]*B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
def mat_vec(A,v): return [A[i][0]*v[0]+A[i][1]*v[1]+A[i][2]*v[2] for i in range(3)]
def v_add(a,b): return [a[0]+b[0],a[1]+b[1],a[2]+b[2]]
def to_yup(p): return [p[0],p[2],p[1]]   # MOHAA Z-up -> viewer Y-up, left/right un-mirrored
def _cross(a,b): return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def _dot3(a,b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def _normalize3(v):
    import math as _m; l=_m.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2])
    return [v[0]/l,v[1]/l,v[2]/l] if l>1e-9 else [1.0,0.0,0.0]
def _transpose3(R): return [[R[0][0],R[1][0],R[2][0]],[R[0][1],R[1][1],R[2][1]],[R[0][2],R[1][2],R[2][2]]]
def _col(R,c): return [R[0][c],R[1][c],R[2][c]]
def mat_to_quat(R):
    # rotation matrix (column convention R[r][c]) -> quaternion (x,y,z,w), robust branches
    import math as _m
    t=R[0][0]+R[1][1]+R[2][2]
    if t>0.0:
        s=_m.sqrt(t+1.0)*2.0
        return [(R[2][1]-R[1][2])/s,(R[0][2]-R[2][0])/s,(R[1][0]-R[0][1])/s,0.25*s]
    if R[0][0]>R[1][1] and R[0][0]>R[2][2]:
        s=_m.sqrt(1.0+R[0][0]-R[1][1]-R[2][2])*2.0
        return [0.25*s,(R[0][1]+R[1][0])/s,(R[0][2]+R[2][0])/s,(R[2][1]-R[1][2])/s]
    if R[1][1]>R[2][2]:
        s=_m.sqrt(1.0+R[1][1]-R[0][0]-R[2][2])*2.0
        return [(R[0][1]+R[1][0])/s,0.25*s,(R[1][2]+R[2][1])/s,(R[0][2]-R[2][0])/s]
    s=_m.sqrt(1.0+R[2][2]-R[0][0]-R[1][1])*2.0
    return [(R[0][2]+R[2][0])/s,(R[1][2]+R[2][1])/s,0.25*s,(R[1][0]-R[0][1])/s]
def mat_to_localquat(R):
    # TRUE inverse of quat_to_mat. quat_to_mat applies MOHAA's inverse-quat convention (it
    # conjugates x,y,z before building the matrix), so quat_to_mat(mat_to_quat(R)) == R^T, not R.
    # Baking a solved world frame back into a "local quat" with the plain mat_to_quat therefore
    # stored the TRANSPOSE of the intended rotation; when the JS viewer recomposed the chain via
    # quat_to_mat it transposed every IK-baked leg bone (the FK/OBJ path uses wR/wT directly and
    # stayed correct, which is why isolated renders looked clean while the viewer twisted/stretched
    # the legs). Conjugating mat_to_quat makes quat_to_mat(mat_to_localquat(R)) == R exactly.
    q=mat_to_quat(R); return [-q[0],-q[1],-q[2],q[3]]
def quat_slerp(a,c,t):
    import math as _m
    d=a[0]*c[0]+a[1]*c[1]+a[2]*c[2]+a[3]*c[3]
    if d<0.0: c=[-c[0],-c[1],-c[2],-c[3]]; d=-d
    if d>0.9995:
        r=[a[k]+t*(c[k]-a[k]) for k in range(4)]
    else:
        th=_m.acos(max(-1.0,min(1.0,d))); st=_m.sin(th)
        r=[(_m.sin((1-t)*th)*a[k]+_m.sin(t*th)*c[k])/st for k in range(4)]
    l=_m.sqrt(sum(x*x for x in r)); return [x/l for x in r] if l>1e-9 else [0.0,0.0,0.0,1.0]
def _hoserot_local(parent_R,target_R,bendRatio,bendMax,spinRatio):
    # Port of skelBone_HoseRot::GetDirtyTransform - bends the parent X-axis toward the
    # target bone's X-axis by angle*bendRatio (clamped to bendMax), then blends toward the
    # target's parent-relative orientation by spinRatio. Returns the LOCAL quaternion
    # (relative to parent); the caller composes it with the parent like any ordinary bone.
    import math as _m
    aim=_normalize3(_col(parent_R,0)); taim=_normalize3(_col(target_R,0))
    rax=_cross(taim,aim)
    if rax[0]*rax[0]+rax[1]*rax[1]+rax[2]*rax[2]<1e-12: rax=[1.0,0.0,0.0]
    else: rax=_normalize3(rax)
    s=max(-1.0,min(1.0,_dot3(aim,taim))); ang=_m.acos(s)
    v=ang*bendRatio
    if v>bendMax: v=bendMax
    pt=_transpose3(parent_R)   # rotaxis into parent-local frame = parent_R^T * rax
    rl=[pt[0][0]*rax[0]+pt[0][1]*rax[1]+pt[0][2]*rax[2],
        pt[1][0]*rax[0]+pt[1][1]*rax[1]+pt[1][2]*rax[2],
        pt[2][0]*rax[0]+pt[2][1]*rax[1]+pt[2][2]*rax[2]]
    c=_m.cos(v*0.5); sn=_m.sqrt(max(0.0,1.0-c*c))
    bend=[rl[0]*sn,rl[1]*sn,rl[2]*sn,c]
    if spinRatio<1.0:
        relR=mat_mul(pt,target_R)   # target orientation relative to parent
        bend=quat_slerp(mat_to_quat(relR),bend,spinRatio)
    return bend
def _avrot_local(parent_R,ref1_R,ref2_R,weight):
    # Port of skelBone_AvRot::GetDirtyTransform - world orientation is the slerp of the two
    # reference bones' world orientations; returned here as a LOCAL quat (parent^-1 * world).
    qw=quat_slerp(mat_to_quat(ref1_R),mat_to_quat(ref2_R),weight)
    return mat_to_quat(mat_mul(_transpose3(parent_R),quat_to_mat(qw)))

# A HoseRot(5)/AvRot(6) helper belongs to a LEG joint (hip/knee/ankle skinning frame) when its
# own name, its parent, or any reference names a leg bone. Only leg helpers are posed by the
# engine-correct _solve_helper_world solver below and kept in skinning; arm helpers (shoulder/
# elbow) stay on the redistribute path that already renders the arms correctly. This is the scope
# gate that lets the perfected-leg solve in from the "almost_fixed" build WITHOUT breaking arms.
_LEG_HELPER_KW=("thigh","calf","foot","toe")
def _classify_leg_helper(bones,bn):
    if bn.get("boneType") not in (5,6): return False
    nms=[bn.get("name","")]
    pi=bn.get("parentIdx",-1)
    if 0<=pi<len(bones): nms.append(bones[pi].get("name",""))
    for r in bn.get("refIdx",[]):
        if 0<=r<len(bones): nms.append(bones[r].get("name",""))
    low=" ".join(nms).lower()
    return any(k in low for k in _LEG_HELPER_KW)

def _solve_helper_world(bones,i,wR,wT):
    # Engine-correct WORLD transform for a solvable HoseRot(5)/AvRot(6) joint-helper bone. These
    # bones carry most of the LEG skin weight, so their orientation must match skelBone_HoseRot/
    # AvRot::GetDirtyTransform exactly or the leg mesh stretches/pinches. Done in standard (non-
    # conjugating) quaternion space with a true m<->q inverse pair, then handed back as a world
    # matrix; the caller writes wR/wT directly (like solve_ik_legs) instead of composing
    # parent*local, and build_payload bakes the result via _world_to_local. Position is parent*basePos.
    import math as _m
    bn=bones[i]; pi=bn["parentIdx"]; bp=bn.get("bindOffset",[0.0,0.0,0.0])
    Tw=v_add(wT[pi],mat_vec(wR[pi],bp))
    def m2q(R):
        tr=R[0][0]+R[1][1]+R[2][2]
        if tr>0:
            s=_m.sqrt(tr+1.0)*2.0; return [(R[2][1]-R[1][2])/s,(R[0][2]-R[2][0])/s,(R[1][0]-R[0][1])/s,0.25*s]
        if R[0][0]>R[1][1] and R[0][0]>R[2][2]:
            s=_m.sqrt(1.0+R[0][0]-R[1][1]-R[2][2])*2.0; return [0.25*s,(R[0][1]+R[1][0])/s,(R[0][2]+R[2][0])/s,(R[2][1]-R[1][2])/s]
        if R[1][1]>R[2][2]:
            s=_m.sqrt(1.0+R[1][1]-R[0][0]-R[2][2])*2.0; return [(R[0][1]+R[1][0])/s,0.25*s,(R[1][2]+R[2][1])/s,(R[0][2]-R[2][0])/s]
        s=_m.sqrt(1.0+R[2][2]-R[0][0]-R[1][1])*2.0; return [(R[0][2]+R[2][0])/s,(R[1][2]+R[2][1])/s,0.25*s,(R[1][0]-R[0][1])/s]
    def q2m(q):
        x,y,z,w=q
        return [[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]
    def slerp(a,c,t):
        d=sum(a[k]*c[k] for k in range(4))
        if d<0: c=[-v for v in c]; d=-d
        if d>0.9995: r=[a[k]+t*(c[k]-a[k]) for k in range(4)]
        else:
            th=_m.acos(d); s=_m.sin(th); r=[(_m.sin((1-t)*th)*a[k]+_m.sin(t*th)*c[k])/s for k in range(4)]
        nrm=_m.sqrt(sum(v*v for v in r)) or 1.0; return [v/nrm for v in r]
    refs=bn["refIdx"]
    if bn["boneType"]==6:                         # AvRot (knee): world slerp of the two refs
        R=q2m(slerp(m2q(wR[refs[0]]),m2q(wR[refs[1]]),bn.get("avWeight",0.5)))
    else:                                         # HoseRot (hip/ankle): track the target bone
        # The pelvis aims up the spine and the thigh aims down the leg - a near-antiparallel pair,
        # so the engine's bend-axis (cross of the two aims) is numerically degenerate and ANY bend
        # solve here is hypersensitive: the world-space port bunches the waist and the literal
        # engine port flips a hip helper sideways and flares it. For a standalone viewer the stable,
        # correct-looking choice is to align the helper with its TARGET bone (hip->Thigh, ankle->Calf),
        # which is co-located with the joint and tracks the limb. Validated by rendering the real
        # resistance.skd: this gives a clean waist hem and leaves the boots unchanged (the remaining
        # boot lining artifact is in the cull* surfaces, independent of this helper - see notes).
        if "wrist" in bn.get("name","").lower():
            # WRIST hose helper. The verts weighted here are the hand mesh's forearm CUFF/STUMP: in
            # LightRay3D's "Correct wrist/ankle bones" import (and the authored bind pose) that stump
            # runs DOWN THE ARM toward the forearm, so it tucks behind the wrist. A MOHAA Biped forearm
            # bone's own aim axis (SkelMat4[0]) points back toward the HAND, so aiming the helper at
            # that axis (or copying the forearm frame) sends the cuff the wrong way - toward the
            # fingers - where it overlaps the back of the hand as a flat slab (the reported artifact,
            # ~11 units of stump laid over the knuckles). Instead aim the helper at the target forearm
            # bone's POSITION (helper -> forearm = down the arm toward the elbow) and take the roll
            # from the hand's Y axis, so the cuff's back-of-hand normal stays aligned with the hand.
            # This places the stump as a clean tube along the arm, matching LightRay3D. Ref:
            # skelBone_HoseRot::GetDirtyTransform (skeletor/skeletorbones.cpp:973-1069) aims the parent
            # at m_target (here Bip01 * Forearm); we resolve that aim geometrically to sidestep the
            # Biped forearm's reversed local axis. Gated to "wrist" so hip/ankle stay on their paths.
            _tgt=refs[0]
            _nx=_v_norm([wT[_tgt][k]-Tw[k] for k in range(3)])           # aim: helper -> forearm bone
            _uy=[wR[pi][k][1] for k in range(3)]                         # hand Y = roll reference
            _uy=[_uy[k]-_v_dot(_uy,_nx)*_nx[k] for k in range(3)]
            if _v_dot(_uy,_uy)<1e-6: _uy=[wR[pi][k][2] for k in range(3)] # degenerate: fall back to hand Z
            _uy=_v_norm(_uy)
            _nz=[_nx[1]*_uy[2]-_nx[2]*_uy[1],_nx[2]*_uy[0]-_nx[0]*_uy[2],_nx[0]*_uy[1]-_nx[1]*_uy[0]]
            R=[[_nx[0],_uy[0],_nz[0]],[_nx[1],_uy[1],_nz[1]],[_nx[2],_uy[2],_nz[2]]]
        elif "ankle" in bn.get("name","").lower():
            # ANKLE exception: the ankle helper is a "hose" from the foot UP to the calf, so its
            # skinning axis must point up the limb (toward the target). But the target(calf) bone's
            # own local-X points DOWN at its child(foot) - skelBone_HoseRot aims myParentTM[0] toward
            # targetTM[0] (skeletorbones.cpp L986-987), both down-limb. The ankle-weighted garment
            # verts are authored with offsets running up the shin (ox up to a full shin-length), so
            # copying the calf frame drives them downward and collapses the lower leg into a ring
            # below the boot (the pinch/overshoot/"missing rows"). Flip 180 deg about the target's
            # local Y: local-X now points up the shin while the lateral Y (winding) is preserved.
            Rt=wR[refs[0]]
            R=[[-Rt[r][0],Rt[r][1],-Rt[r][2]] for r in range(3)]
        else:
            R=q2m(m2q(wR[refs[0]]))               # HIP: track target bone's world orientation (unchanged)
    return R,Tw

# Canonical Bip01 human/player REST pose - frame 0 of models/human/allied_pilot/allied_pilot.skc,
# the exact template LightRay3D's MOH plugin uses for "Use Template > Third Person". MOHAA character
# .skd files store NO usable upright bind pose: the identity rest lays the Bip01 skeleton out
# horizontally along +X and the IK leg chains (thigh->calf->foot) collapse into a straight ~92u line.
# A real animation frame is required to stand the model. The shared "idle" .skc the launcher pulls
# (e.g. salute_idle) are POSED action frames - they drop arms into salutes/slivers and stretch limbs
# the FK viewer can't reproduce. allied_pilot.skc is a neutral A-pose that bakes rotFK for every IK
# bone, so pure FK reproduces it cleanly, and it covers the full player rig incl. both hands' fingers,
# head/neck and the weapon tags. Channel names follow the stock Bip01 rig, so it poses ANY human/player
# skeleton; non-matching skeletons (vehicles, weapons, statics, emitters) ignore it (no regression).
ALLIED_PILOT_POSE = {
    'Bip01 Footsteps pos': [0.0, 0.0, -103.19012, 0.0],
    'Bip01 Footsteps rot': [0.0, 0.0, -0.70711, 0.70711],
    'Bip01 Head rot': [-0.0, -0.0, 0.1136, 0.99353],
    'Bip01 L Calf rotFK': [0.0, 0.0, 0.04613, 0.99894],
    'Bip01 L Clavicle rot': [0.7253, -0.08927, 0.67594, 0.09522],
    'Bip01 L Finger0 rot': [-0.7507, -0.39427, 0.09594, 0.52135],
    'Bip01 L Finger01 rot': [-0.0, -0.0, 0.00436, 0.99999],
    'Bip01 L Finger02 rot': [-0.0, -0.0, 0.01745, 0.99985],
    'Bip01 L Finger1 rot': [-0.01183, -0.11326, -0.06877, 0.99111],
    'Bip01 L Finger11 rot': [-0.0, -0.0, -0.46947, 0.88295],
    'Bip01 L Finger12 rot': [0.0, -0.0, -0.34612, 0.93819],
    'Bip01 L Finger2 rot': [0.00534, 0.01733, -0.06962, 0.99741],
    'Bip01 L Finger21 rot': [-0.0, 0.0, -0.46947, 0.88295],
    'Bip01 L Finger22 rot': [0.0, 0.0, -0.30071, 0.95372],
    'Bip01 L Finger3 rot': [0.0077, -0.02163, -0.11299, 0.99333],
    'Bip01 L Finger31 rot': [0.0, 0.0, -0.43837, 0.89879],
    'Bip01 L Finger32 rot': [-0.0, -0.0, -0.42262, 0.90631],
    'Bip01 L Finger4 rot': [0.06623, -0.02113, -0.08618, 0.99385],
    'Bip01 L Finger41 rot': [-0.0, -0.0, -0.22495, 0.97437],
    'Bip01 L Finger42 rot': [0.0, 0.0, -0.38671, 0.9222],
    'Bip01 L Foot pos': [-3.14467, 9.69147, 10.98246, 0.0],
    'Bip01 L Foot rot': [-0.50218, -0.49781, 0.49781, 0.50218],
    'Bip01 L Foot rotFK': [9e-05, 0.00276, -0.04838, 0.99883],
    'Bip01 L Forearm rot': [0.0, -0.0, 0.06266, 0.99803],
    'Bip01 L Hand rot': [0.69385, -0.07177, -0.07444, 0.71265],
    'Bip01 L Thigh rotFK': [0.00211, 0.99999, -0.00021, 0.00275],
    'Bip01 L Toe0 rot': [0.0, -0.0, -0.70711, 0.70711],
    'Bip01 L UpperArm rot': [-0.03684, -0.27071, 0.0803, 0.9586],
    'Bip01 Neck rot': [0.0, 0.0, -0.20791, 0.97815],
    'Bip01 Pelvis pos': [0.70846, 0.0, 0.0, 0.0],
    'Bip01 Pelvis rot': [0.5, 0.5, 0.5, 0.5],
    'Bip01 R Calf rotFK': [-0.0, -0.0, 0.04613, 0.99894],
    'Bip01 R Clavicle rot': [0.7253, -0.08927, -0.67594, -0.09522],
    'Bip01 R Finger0 rot': [0.7507, 0.39427, 0.09594, 0.52135],
    'Bip01 R Finger01 rot': [0.0, -0.0, 0.00436, 0.99999],
    'Bip01 R Finger02 rot': [0.0, 0.0, 0.01745, 0.99985],
    'Bip01 R Finger1 rot': [0.01183, 0.11326, -0.06877, 0.99111],
    'Bip01 R Finger11 rot': [-0.0, 0.0, -0.46947, 0.88295],
    'Bip01 R Finger12 rot': [-0.0, 0.0, -0.34612, 0.93819],
    'Bip01 R Finger2 rot': [-0.00534, -0.01733, -0.06962, 0.99741],
    'Bip01 R Finger21 rot': [0.0, 0.0, -0.46947, 0.88295],
    'Bip01 R Finger22 rot': [-0.0, -0.0, -0.30071, 0.95372],
    'Bip01 R Finger3 rot': [-0.0077, 0.02163, -0.11299, 0.99333],
    'Bip01 R Finger31 rot': [-0.0, -0.0, -0.43837, 0.89879],
    'Bip01 R Finger32 rot': [0.0, -0.0, -0.42262, 0.90631],
    'Bip01 R Finger4 rot': [-0.06623, 0.02113, -0.08618, 0.99385],
    'Bip01 R Finger41 rot': [-0.0, 0.0, -0.22495, 0.97437],
    'Bip01 R Finger42 rot': [-0.0, 0.0, -0.38671, 0.9222],
    'Bip01 R Foot pos': [-3.14464, -9.69148, 10.98246, 0.0],
    'Bip01 R Foot rot': [-0.50218, -0.49781, 0.49781, 0.50218],
    'Bip01 R Foot rotFK': [-9e-05, -0.00276, -0.04838, 0.99883],
    'Bip01 R Forearm rot': [-0.0, -0.0, 0.06266, 0.99803],
    'Bip01 R Hand rot': [-0.69385, 0.07177, -0.07444, 0.71265],
    'Bip01 R Thigh rotFK': [0.00211, 0.99999, 0.00021, -0.00275],
    'Bip01 R Toe0 rot': [0.0, -0.0, -0.70711, 0.70711],
    'Bip01 R UpperArm rot': [0.03684, 0.27071, 0.0803, 0.9586],
    'Bip01 Spine rot': [0.0, 0.0, -0.07451, 0.99722],
    'Bip01 Spine1 rot': [-0.0, -0.0, 0.10019, 0.99497],
    'Bip01 Spine2 rot': [0.0, 0.0, -0.01745, 0.99985],
    'Bip01 pos': [-0.0, 0.0, 103.19012, 0.0],
    'Bip01 rot': [0.0, 0.0, -0.0, 1.0],
    'Box02 pos': [-103.19278, -0.18353, -0.0001, 0.0],
    'Box02 rot': [0.5, 0.5, 0.5, 0.5],
    'ORIGIN pos': [0.0, -0.0, 0.0, 0.0],
    'ORIGIN rot': [0.0, 0.0, 0.70711, 0.70711],
    'eyes bone pos': [10.49891, 2.97134, 1e-05, 0.0],
    'eyes bone rot': [-0.54167, -0.45452, -0.45452, 0.54167],
    'tag_weapon_left pos': [10.48681, 2.75094, -1.56709, 0.0],
    'tag_weapon_left rot': [-0.02023, -0.15335, -0.12723, 0.97974],
    'tag_weapon_right pos': [10.52091, 2.61471, 1.57944, 0.0],
    'tag_weapon_right rot': [0.97927, 0.12735, 0.15459, -0.03032],
}
# Back-compat alias: older fallback/gap-fill paths reference DEFAULT_BIP01_POSE.
DEFAULT_BIP01_POSE = ALLIED_PILOT_POSE

def _parse_skb(b,path):
    # SKB skelmodel (ident "SKL ", versions 3/4 - openmohaa tiki_shared.h:61-63). The older
    # skeleton format still used by many static items (beef.tik, battery.tik, canteen.tik,
    # bratwurst.tik, detpack.tik ...). It shares the skelHeader_t layout with SKD
    # (tiki_shared.h:198-214: ident@0 version@4 name[64]@8 numSurfaces@0x48 numBones@0x4C
    # ofsBones@0x50 ofsSurfaces@0x54) but differs in BONE and VERTEX encoding, so it gets
    # its own path. TIKI_LoadSKB (tiki_skel.cpp:554-728) walks surfaces by ofsSurfaces then
    # ofsEnd chaining and converts each old skelVertex_t to the runtime skeletorVertex_t.
    version=_i32(b,0x04)
    numSurf=_cap(b,_i32(b,0x48),0x60,"SKB surface",path); numBone=_cap(b,_i32(b,0x4C),72,"SKB bone",path)
    ofsBone=_i32(b,0x50); ofsSurf=_i32(b,0x54)
    # BONES: skelBoneName_t (tiki_shared.h:216-221) - parent(short)@0, boxIndex(short)@2,
    # flags(int)@4, name[64]@8 = 72 bytes each. Unlike SKD there is NO per-bone base/offset
    # block in the file: TIKI_CacheFileSkel (tiki_skel.cpp:422-435) turns every SKB bone into
    # a POSROT bone via CreatePosRotBoneData, so position comes from the "<bone> pos" channel
    # and rotation from "<bone> rot" (the idle .skc supplies both; with none, the bone rests
    # at identity and the mesh sits at its authored bind pose via the vertex weight offsets).
    raw=[]; off=ofsBone
    for _ in range(numBone):
        parent=struct.unpack_from("<h",b,off)[0]
        name=_cstr(b,off+8,64)
        raw.append((name,parent)); off+=72
    bones=[]
    for name,parent in raw:
        pname = raw[parent][0] if 0<=parent<len(raw) else "worldbone"
        bones.append({"name":name,"parent":pname,"boneType":1,"bindOffset":[0.0,0.0,0.0]})
    name2idx={bn["name"]:i for i,bn in enumerate(bones)}
    for bn in bones:
        bn["parentIdx"]=name2idx.get(bn["parent"],-1)
        bn["solvable"]=False; bn["legHelper"]=False   # SKB has no HoseRot/AvRot helper bones
    # SURFACES: skelSurface_t chain from ofsSurfaces (tiki_skel.cpp:603-643). Header layout is
    # the same as SKD's surface (numTri@0x44 numVrt@0x48 ofsTri@0x50 ofsVrt@0x54 ofsEnd@0x5C);
    # triangles are 3x int32 (tiki_skel.cpp:335-339). The vertex block is the ONLY real
    # difference: skelVertex_t (tiki_shared.h:333-338) = normal(12)+texCoords(8)+numWeights(4)
    # = a 24-byte header with NO numMorphs field, immediately followed by numWeights
    # skelWeight_t (boneIndex,i32 + boneWeight,f32 + offset,3xf32 = 20 bytes). (SKD instead
    # carries a 28-byte header + a morph block; converted away here by not reading morphs.)
    surfaces=[]; so=ofsSurf
    for _s in range(numSurf):
        sname=_cstr(b,so+4,64)
        numTri=_cap(b,_i32(b,so+0x44),12,"SKB triangle",path); numVrt=_cap(b,_i32(b,so+0x48),24,"SKB vertex",path)
        ofsTri=_i32(b,so+0x50); ofsVrt=_i32(b,so+0x54); ofsEnd=_i32(b,so+0x5C)
        tris=[]; to=so+ofsTri
        for _t in range(numTri):
            tris.append((_i32(b,to),_i32(b,to+4),_i32(b,to+8))); to+=12
        verts=[]; uvs=[]; vo=so+ofsVrt
        for _ in range(numVrt):
            uvs.append((_f32(b,vo+12),_f32(b,vo+16)))   # texCoords (s,t)
            nw=_cap(b,_i32(b,vo+20),20,"SKB weight",path)  # numWeights (no morph count in SKB)
            wo=vo+24                                     # weights follow the 24-byte header
            weights=[]
            for _w in range(nw):
                bi=_i32(b,wo); wt=_f32(b,wo+4)
                ofx=(_f32(b,wo+8),_f32(b,wo+12),_f32(b,wo+16))
                weights.append((bi,wt,ofx)); wo+=20
            verts.append(weights); vo=wo
        surfaces.append({"name":sname,"tris":tris,"verts":verts,"uvs":uvs})
        if ofsEnd<=0: break                          # non-advancing ofsEnd = infinite loop
        so+=ofsEnd
    return {"bones":bones,"name2idx":name2idx,"surfaces":surfaces,"numBone":numBone,
            "morphNames":[]}      # SKB has no morph block (24-byte vertex header)

def parse_skd(path):
    # Dispatch on the file ident. Both SKD (ident "SKMD", versions 5/6) and SKB (ident
    # "SKL ", versions 3/4) are valid TIKI skelmodels (openmohaa tiki_shared.h:61-68); a
    # .tik's `skelmodel` may point at either. Static items commonly still ship the older SKB.
    b=open(path,"rb").read()
    ident=b[0:4]
    if ident==b"SKL ": return _parse_skb(b,path)
    if ident!=b"SKMD": raise ValueError(f"{path}: not an SKD/SKB (ident {ident!r})")
    return _parse_skmd(b,path)

def _skd_morph_names(b):
    """Morph-target (blend-shape) names from an SKD, or [].

    skelHeader_t puts numMorphTargets at 0x8C and ofsMorphTargets at 0x90 - after
    name[64] at 0x08 and lodIndex[TIKI_SKEL_LOD_INDEXES=10] at 0x5C
    (openmohaa tiki_shared.h:198-213). The table itself is numMorphTargets packed
    NUL-terminated VARIABLE-length strings; the loader walks it with strlen()+1
    (tiki_skel.cpp:209-215).

    The declared count is NOT trustworthy: retail models/human/heads/manon.skd says
    numMorphTargets=10 but ships exactly 3 names and ends at EOF, so a reader that
    believes the header walks off the buffer. Stop at whatever is actually there."""
    if len(b)<0x94: return []
    n=_i32(b,0x8C); ofs=_i32(b,0x90)
    if not (0<n<=4096 and 0<ofs<len(b)): return []
    names=[]; p=ofs
    for _ in range(n):
        z=b.find(b"\0",p)
        if z<0 or z-p>128: break                 # truncated/garbage table - keep what parsed
        names.append(b[p:z].decode("latin-1","replace")); p=z+1
    return names

def _parse_skmd(b,path):
    morph_names=_skd_morph_names(b)
    numBone=_cap(b,_i32(b,0x4C),0x54,"SKD bone",path); ofsBone=_i32(b,0x50)
    bones=[]; off=ofsBone
    for _ in range(numBone):
        name=_cstr(b,off,32); parent=_cstr(b,off+0x20,32)
        bType=_i32(b,off+0x40); ofsBase=_i32(b,off+0x44); ofsChan=_i32(b,off+0x48)
        ofsBoneNames=_i32(b,off+0x4C); ofsEnd=_i32(b,off+0x50)
        baseLen=ofsChan-ofsBase
        def _bf(k,_o=off+ofsBase): return _f32(b,_o+k*4)
        # bind-pose local offset, located per bone type:
        #  0 ROTATION         offset(3)+scale(3)
        #  1 POSROT/root       scale only - position comes from a "pos" channel
        #  2 IKSHOULDER        quat(4)+offset(3)+scale(3)   (thigh/upperarm)
        #  3 IKELBOW           offset(3)+scale(3)            (calf/forearm)
        #  4 IKWRIST           offset(3)+scale(3)            (foot/hand)
        #  5 HOSEROT  bendRatio,bendMax,spinRatio,basePos(3),scale(3),type - bends parent toward 1 target
        #  6 AVROT    rotRatio,basePos(3),scale(3)          - averages 2 reference bones
        bone={"name":name,"parent":parent,"boneType":bType}
        if bType==0 and baseLen>=24:
            bindOffset=[_bf(0),_bf(1),_bf(2)]
        elif bType in (3,4) and baseLen>=24:
            bindOffset=[_bf(0),_bf(1),_bf(2)]
        elif bType==2 and baseLen>=28:
            bone["baseQuat"]=[_bf(0),_bf(1),_bf(2),_bf(3)]   # bind orientation (needed for IK leg solve)
            bindOffset=[_bf(4),_bf(5),_bf(6)]
        elif bType==5 and baseLen>=24:   # HoseRot (ankle/shoulder/hip skinning-frame helper)
            bone["bendRatio"]=_bf(0); bone["bendMax"]=_bf(1); bone["spinRatio"]=_bf(2)
            bindOffset=[_bf(3),_bf(4),_bf(5)]
        elif bType==6 and baseLen>=16:   # AvRot (knee/elbow averaging helper)
            bone["avWeight"]=_bf(0); bindOffset=[_bf(1),_bf(2),_bf(3)]
        else:
            bindOffset=[0.0,0.0,0.0]
        bone["bindOffset"]=bindOffset
        if bType in (5,6):               # reference/target bone NAMES live in the boneNames block
            bone["refNames"]=[s for s in _cstr_list(b,off+ofsBoneNames,ofsEnd-ofsBoneNames)]
        bones.append(bone)
        if ofsEnd<=0: break                          # non-advancing ofsEnd = infinite loop
        off+=ofsEnd
    name2idx={bn["name"]:i for i,bn in enumerate(bones)}
    for bn in bones: bn["parentIdx"]=name2idx.get(bn["parent"],-1)
    # resolve HoseRot/AvRot reference bone names to indices; a helper is "solvable" when its
    # parent and all references resolve (type 5 needs 1 target, type 6 needs 2 references).
    for bn in bones:
        if bn["boneType"] in (5,6):
            bn["refIdx"]=[name2idx.get(r,-1) for r in bn.get("refNames",[])]
            need=1 if bn["boneType"]==5 else 2
            bn["solvable"]=(bn["parentIdx"]>=0 and len([r for r in bn["refIdx"] if r>=0])>=need)
            bn["legHelper"]=_classify_leg_helper(bones,bn)
        else:
            bn["solvable"]=False; bn["legHelper"]=False
    surfaces=[]
    for m in re.finditer(b"SKL ",b):
        s0=m.start(); sname=_cstr(b,s0+4,64)
        numTri=_cap(b,_i32(b,s0+0x44),12,"SKD triangle",path); numVrt=_cap(b,_i32(b,s0+0x48),28,"SKD vertex",path)
        ofsTri=_i32(b,s0+0x50); ofsVrt=_i32(b,s0+0x54)
        tris=[]; to=s0+ofsTri
        for _t in range(numTri):
            tris.append((_i32(b,to),_i32(b,to+4),_i32(b,to+8))); to+=12
        verts=[]; uvs=[]; morphs=[]; vo=s0+ofsVrt
        for _ in range(numVrt):
            uvs.append((_f32(b,vo+12),_f32(b,vo+16)))   # texture coords (s,t)
            nw=_cap(b,_i32(b,vo+20),20,"SKD weight",path); nm=_cap(b,_i32(b,vo+24),16,"SKD morph",path)
            # skeletorMorph_t { int morphIndex; vec3_t offset; } = 16 bytes, sitting
            # immediately after the 28-byte skeletorVertex_t and BEFORE the weights
            # (openmohaa tiki_shared.h:361-364, tiki_skel.cpp:366-368). These used to be
            # skipped; they are the facial blend-shape deltas, in the same bone space as
            # the weight offsets below (on retail heads 422 of 424 morphed vertices are
            # single-weighted to Bip01 Head), so they simply add to that offset.
            mo=vo+28; vmorphs=[]
            for _k in range(nm):
                vmorphs.append((_i32(b,mo),(_f32(b,mo+4),_f32(b,mo+8),_f32(b,mo+12))))
                mo+=16
            morphs.append(vmorphs)
            wo=mo
            weights=[]
            for _w in range(nw):
                bi=_i32(b,wo); wt=_f32(b,wo+4)
                ofx=(_f32(b,wo+8),_f32(b,wo+12),_f32(b,wo+16))
                weights.append((bi,wt,ofx)); wo+=20
            verts.append(weights); vo=wo
        surfaces.append({"name":sname,"tris":tris,"verts":verts,"uvs":uvs,
                         "morphs":morphs if any(morphs) else None})
    # (Removed: the ankle-ring Z-negate hack. It masked a wrong ankle-helper skinning frame by
    # mirroring vertex offsets; the frame is now corrected up-limb in _solve_helper_world, so the
    # negate is unnecessary and, applied on top of the fix, would re-flip the ring and bowtie it.)
    # Helper bones (HoseRot/AvRot) drive skinning frames for ankles/knees/shoulders/hips and carry
    # MOST of the leg-garment skin weight. Solvable LEG helpers (hip/knee/ankle) are now posed by
    # the engine-correct _solve_helper_world solver, so their weights are KEPT and skinned in their
    # own joint frame - this is what un-stretches the upper legs. ARM helpers (shoulder/elbow) and
    # any unsolvable helper are still redistributed onto the nearest real ancestor, which is what
    # already renders the arms correctly; keeping that path untouched is why the arms don't break.
    is_helper=[bn["boneType"]>=5 for bn in bones]
    redist=[bn["boneType"]>=5 and not bn.get("solvable") for bn in bones]   # keep ALL solvable helpers (leg + arm); only unsolvable redistribute
    def _real_anc(i):
        seen=0
        while 0<=i<len(bones) and is_helper[i] and seen<128:
            i=bones[i]["parentIdx"]; seen+=1
        return i if 0<=i<len(bones) else 0
    if any(redist):
        for s in surfaces:
            for vi,weights in enumerate(s["verts"]):
                if not any(redist[w[0]] for w in weights): continue
                kept=[w for w in weights if not redist[w[0]]]   # keep real + solvable leg-helper weights
                if not kept:   # vertex only on redistributed helper(s) -> nearest real ancestor
                    bi,wt,ofx=weights[0]; kept=[(_real_anc(bi),1.0,ofx)]
                tot=sum(w[1] for w in kept) or 1.0
                s["verts"][vi]=[(w[0],w[1]/tot,w[2]) for w in kept]
    return {"bones":bones,"name2idx":name2idx,"surfaces":surfaces,"numBone":numBone,
            "morphNames":morph_names}

def merge_skds(skds):
    """Assemble several part .skd models (body first, then head/hands/etc.) into ONE model that
    shares a single skeleton, the way a .tik combines them in-game. The union skeleton starts from
    the body (keeping its bone indices), then each subsequent part contributes any bones whose NAME
    is new (e.g. the hand model's finger bones, which parent onto the body's shared Bip01 *Hand).
    Every part's surface vertex weights are remapped from that part's local bone indices to the
    union indices by bone name, so all surfaces deform under the same pose."""
    if len(skds)==1: return skds[0]
    bones=[dict(b) for b in skds[0]["bones"]]
    name2idx={b["name"]:i for i,b in enumerate(bones)}
    surfaces=list(skds[0]["surfaces"])
    # Morph targets union the same way bones do. The engine builds ONE morph list for the
    # whole tiki, calling LoadMorphTargetNames once per mesh (openmohaa skeletor.cpp:246-252),
    # so a body+head model shares a single weight vector. Matching is case-insensitive:
    # retail head6.skd spells a target "VISEME_though" where the .skc channel says
    # "VISEME_Though", and MOHAA compares asset names case-insensitively throughout.
    morph_names=list(skds[0].get("morphNames") or [])
    mkey={n.lower():i for i,n in enumerate(morph_names)}
    for skd in skds[1:]:
        for b in skd["bones"]:
            if b["name"] not in name2idx:
                name2idx[b["name"]]=len(bones); bones.append(dict(b))
        remap=[name2idx[b["name"]] for b in skd["bones"]]   # local part idx -> union idx
        mremap=[]
        for n in (skd.get("morphNames") or []):
            k=n.lower()
            if k not in mkey:
                mkey[k]=len(morph_names); morph_names.append(n)
            mremap.append(mkey[k])
        for s in skd["surfaces"]:
            sm=s.get("morphs")
            surfaces.append({"name":s["name"],"uvs":s["uvs"],"tris":s["tris"],
                "verts":[[(remap[bi],wt,ofx) for (bi,wt,ofx) in v] for v in s["verts"]],
                "morphs":([[(mremap[mi] if 0<=mi<len(mremap) else mi,off) for (mi,off) in vm]
                           for vm in sm] if sm else None)})
    for b in bones:
        b["parentIdx"]=name2idx.get(b["parent"],-1)
        if b.get("boneType") in (5,6):   # re-resolve HoseRot/AvRot refs against the union skeleton
            b["refIdx"]=[name2idx.get(r,-1) for r in b.get("refNames",[])]
            need=1 if b["boneType"]==5 else 2
            b["solvable"]=(b["parentIdx"]>=0 and len([r for r in b["refIdx"] if r>=0])>=need)
            b["legHelper"]=_classify_leg_helper(bones,b)
    return {"bones":bones,"name2idx":name2idx,"surfaces":surfaces,"numBone":len(bones),
            "morphNames":morph_names}

def parse_skc(path):
    b=open(path,"rb").read()
    if b[0:4]!=b"SKAN": raise ValueError(f"{path}: not an SKC (ident {b[0:4]!r})")
    version=_i32(b,0x04)
    frameTime=_f32(b,0x10)
    numChan=_i32(b,0x24); ofsChan=_i32(b,0x28); numFrames=_i32(b,0x2C)
    n=len(b)
    # Header sanity BEFORE looping. The shipping SKC format (what every working model uses) keeps
    # numChannels/ofsChannelNames/numFrames at 0x24/0x28/0x2C, frames at 0x30 (stride 48). Older
    # prototype variants - e.g. the v11 files in models/human/wehrmact_test ("ProtoAnimations") -
    # embed a name[64] after the version, shifting the whole header by 0x40, so these reads land in
    # the embedded path string -> absurd counts (numFrames ~1.9 billion) -> the frame loop never
    # returns: that is the viewer "hang". OpenMOHAA's loader rejects SKC versions it doesn't
    # recognise; do the same - raise so the caller (pick_base_anim / the anims loop, both wrapped
    # in try/except) skips this anim and the model still renders from its bind pose.
    if not (0<=numChan<=8192 and 0<numFrames<=200000 and 0<=ofsChan and
            ofsChan+numChan*32<=n and 0x30+numFrames*48<=n):
        raise ValueError(f"{path}: unsupported/old SKC layout (v{version}; numChan={numChan} "
                         f"numFrames={numFrames} ofsChan={ofsChan} size={n}) - skipping animation")
    names=[_cstr(b,ofsChan+i*32,32) for i in range(numChan)]
    frames=[]
    for f in range(numFrames):
        meta=0x30+f*48; ofsVals=_i32(b,meta+0x2C); vals={}
        if ofsVals<0 or ofsVals+numChan*16>n:        # each frame's channel block must be in range
            raise ValueError(f"{path}: SKC frame {f} channel offset {ofsVals} out of range "
                             f"(size {n}) - old/unsupported variant, skipping animation")
        for ci in range(numChan):
            o=ofsVals+ci*16
            vals[names[ci]]=[_f32(b,o),_f32(b,o+4),_f32(b,o+8),_f32(b,o+12)]
        frames.append(vals)
    return {"frameTime":frameTime,"numChan":numChan,"numFrames":numFrames,
            "names":names,"frames":frames}

def morph_track(skc, morph_names):
    """Per-frame blend-shape weights for a facial (MORPH) .skc, or None if not one.

    A facial .skc - models/human/animation/scripted/smoking/inhaleMORPH.skc and friends -
    has channels named after the model's MORPH TARGETS (BROW_frown, EYE_blink, JAW_open-open,
    VISEME_Ox) with NO " pos"/" rot" suffix, so bone_local() can never match them and the
    animation legitimately "drives none of this skeleton's bones". They are blend-shape
    weight curves, played on the head mesh alongside a normal body animation.

    Component[0] of each channel is the weight; the engine accumulates it as an integer,
    data[ch] += (int)(channelData * blendWeight)  (openmohaa skeletor.cpp:1096-1146), and the
    .skd deltas are stored pre-divided by 100, so the value is used raw. Retail range is
    0..100, which puts the largest head1.skd delta (0.0305) at ~3 units of displacement on a
    ~25-unit head - a believable full jaw drop.

    Matching is CASE-INSENSITIVE: head6.skd spells a target "VISEME_though" where the .skc
    channel says "VISEME_Though", and MOHAA compares asset names case-insensitively.
    Trailing-underscore drift is deliberately NOT normalised - head1 ships "EYES_Excited__"
    and head2 ships "BROW_worry_", which no channel name matches. Inventing a match would
    animate expressions the engine itself never drives; those stay at zero and are reported
    instead, so the difference is visible rather than silently invented."""
    if not morph_names: return None
    # .get, not []: the .tik path substitutes a 1-frame static hold
    # ({"frameTime":..,"frames":[{}],"numChan":0}) for any alias whose .skc is missing or
    # drives no bone here, so that its frame COMMANDS still fire. That stub carries no
    # channel table, and indexing it blind crashed the whole build.
    names=skc.get("names") or []
    if not names: return None
    key={n.lower():i for i,n in enumerate(morph_names)}
    hit=[(ci,key[n.lower()]) for ci,n in enumerate(names) if n.lower() in key]
    if not hit: return None
    nm=len(morph_names)
    frames=[]
    for fr in skc["frames"]:
        w=[0.0]*nm
        for ci,mi in hit:
            v=fr.get(skc["names"][ci])
            if v: w[mi]=round(v[0],3)
        frames.append(w)
    unmatched=[n for n in skc["names"] if n.lower() not in key]
    return {"frames":frames,"matched":len(hit),"unmatched":unmatched,
            "frameTime":skc.get("frameTime",0.1)}

def morph_sibling_path(skc_path):
    """The facial .skc that belongs with a body .skc, or None.

    MOHAA splits some actions across two files - models/human/animation/scripted/smoking
    ships lightup.skc (body) beside lightupMORPH.skc (face) - and the engine plays them in
    separate blend slots at once (skeletor.cpp:409-503 fills movement AND action slots;
    GetMorphWeightFrame then accumulates morph weights across BOTH, :1105-1146). Other
    folders instead put both channel sets in ONE file - models/human/animation/misc
    ATTACKidle01.skc is 8 bone + 35 morph channels - which needs no pairing at all."""
    if not skc_path: return None
    d,b=os.path.split(skc_path)
    stem,ext=os.path.splitext(b)
    if stem.upper().endswith("MORPH"): return None      # already the facial half
    for cand in (stem+"MORPH"+ext, stem+"morph"+ext, stem+"Morph"+ext):
        p=os.path.join(d,cand)
        if os.path.isfile(p): return p
    return None

def resample_mw(frames, n_out):
    """Stretch a facial weight track onto n_out frames.

    A split pair is NOT frame-locked: lightup.skc is 34 frames at 0.1s while
    lightupMORPH.skc is 31 at 0.2s, and the ratio differs per pair (buttout is 47 vs 31).
    The two halves describe one action, so the face is mapped proportionally across the
    body's timeline. Combined single-file animations skip this entirely - there both
    channel sets already share a frame index, which is exact."""
    if not frames: return None
    if n_out<=0 or len(frames)==n_out: return frames
    last=len(frames)-1
    if last<=0: return [frames[0] for _ in range(n_out)]
    out=[]
    for i in range(n_out):
        t=(i/(n_out-1)) if n_out>1 else 0.0
        out.append(frames[min(last,int(round(t*last)))])
    return out

def bone_local(bn,channels):
    # rotation: prefer the forward-kinematics channel (IK chains store "<bone> rotFK"),
    # fall back to the plain rot channel for ordinary bones, else identity.
    q=channels.get(bn["name"]+" rotFK")
    if q is None: q=channels.get(bn["name"]+" rot",[0,0,0,1])
    # position: only POSROT/root bones get their offset from a "pos" channel;
    # every other bone uses its fixed bind-pose offset (rigid bone length).
    if bn.get("boneType")==1:
        p=channels.get(bn["name"]+" pos")
        if p is None: p=bn.get("bindOffset",[0,0,0])
    else:
        p=bn.get("bindOffset",[0,0,0])
    return p[:3],q

def _solved_local(bones,i,channels,wR,wT):
    # Local (p,q) for bone i. Ordinary bones come from their animation channels; solvable
    # HoseRot/AvRot helpers are posed by the engine-ported solver using their parent/reference
    # WORLD transforms (which the caller must have resolved first).
    bn=bones[i]; bt=bn.get("boneType")
    if bt in (5,6) and bn.get("solvable"):
        pi=bn["parentIdx"]; refs=bn["refIdx"]
        if bt==5:
            q=_hoserot_local(wR[pi],wR[refs[0]],bn.get("bendRatio",1.0),bn.get("bendMax",180.0),bn.get("spinRatio",1.0))
        else:
            q=_avrot_local(wR[pi],wR[refs[0]],wR[refs[1]],bn.get("avWeight",0.5))
        return bn.get("bindOffset",[0,0,0])[:3],q
    return bone_local(bn,channels)

def _v_sub(a,b): return [a[0]-b[0],a[1]-b[1],a[2]-b[2]]
def _v_dot(a,b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def _v_len(a): return math.sqrt(_v_dot(a,a))
def _v_norm(a):
    l=_v_len(a) or 1.0; return [a[0]/l,a[1]/l,a[2]/l]
def _v_cross(a,b): return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def _v_scale(a,s): return [a[0]*s,a[1]*s,a[2]*s]
def _axis_angle_mat(axis,ang):
    x,y,z=_v_norm(axis); c=math.cos(ang); s=math.sin(ang); t=1-c
    return [[t*x*x+c,t*x*y-s*z,t*x*z+s*y],
            [t*x*y+s*z,t*y*y+c,t*y*z-s*x],
            [t*x*z-s*y,t*y*z+s*x,t*z*z+c]]
def _swing_mat(a,b):
    """Shortest-arc rotation matrix taking unit-ish vector a onto b."""
    a=_v_norm(a); b=_v_norm(b); d=max(-1.0,min(1.0,_v_dot(a,b)))
    if d>0.99999: return [[1.0,0,0],[0,1.0,0],[0,0,1.0]]
    if d<-0.99999:
        ax=_v_cross(a,[1.0,0,0])
        if _v_len(ax)<1e-4: ax=_v_cross(a,[0,1.0,0])
        return _axis_angle_mat(ax,math.pi)
    return _axis_angle_mat(_v_cross(a,b),math.acos(d))

def _leg_ik_chains(bones):
    """Find thigh(type2)->calf(type3)->foot(type4) IK chains (both legs)."""
    out=[]
    for fo,bn in enumerate(bones):
        if bn.get("boneType")!=4: continue
        ca=bn["parentIdx"]
        if ca<0 or bones[ca].get("boneType")!=3: continue
        th=bones[ca]["parentIdx"]
        if th<0 or bones[th].get("boneType")!=2: continue
        out.append((th,ca,fo))
    return out

def _to_eng(R,T):   # engine SkelMat4 rows = world axes (= columns of my column-vector R); row3 = translation
    return [[R[0][0],R[1][0],R[2][0]],[R[0][1],R[1][1],R[2][1]],[R[0][2],R[1][2],R[2][2]],[T[0],T[1],T[2]]]
def _from_eng(M):   # back to my convention: myR[i][j] = engineM[j][i]
    return ([[M[0][0],M[1][0],M[2][0]],[M[0][1],M[1][1],M[2][1]],[M[0][2],M[1][2],M[2][2]]],[M[3][0],M[3][1],M[3][2]])

def solve_ik_legs(bones,channels,wR,wT):
    """Engine-accurate 2-bone IK: a direct port of skelBone_IKshoulder / IKelbow / IKwrist
    ::GetDirtyTransform (openmohaa/code/skeletor/skeletorbones.cpp). MOHAA poses the legs by
    IK from the foot target ("<foot> pos", an ABSOLUTE model-space position) and the foot
    orientation ("<foot> rot"), NOT by the rotFK channels. The thigh and calf are built from a
    SINGLE shared bend-plane frame: the thigh's frame is bent in-plane by the law-of-cosines
    thigh angle, and the calf is that same frame bent further by the knee angle. Because both
    bones share the bend-plane normal (Z axis), the shin's roll is fixed exactly as in-engine -
    this is what eliminates the shin twist/pinch the old shortest-arc swing produced. The foot
    takes its orientation straight from the wrist quat channel ("<foot> rot"), not the calf frame.

    Convention map: the engine's SkelMat4 stores axes as ROWS and composes world=local*parent;
    the viewer stores axes as COLUMNS and composes world=parent*local. Those are transposes, and
    quat_to_mat here is the transpose of the engine QuatToMat, so engine axis i == viewer column i.
    Hence parent/foot axes are read as columns and the solved frame is built column-wise.

    Overrides wR/wT for the thigh, calf and foot in place. Arms are type-0 FK and never touched."""
    I3=[[1.0,0.0,0.0],[0.0,1.0,0.0],[0.0,0.0,1.0]]
    locked=set()
    for th,ca,fo in _leg_ik_chains(bones):
        tgt=channels.get(bones[fo]["name"]+" pos")
        if not tgt: continue                       # FK-only frame: leave the FK result alone
        upper=_v_len(bones[ca]["bindOffset"])       # hip->knee  (m_upperLength = |elbow offset|)
        lower=_v_len(bones[fo]["bindOffset"])       # knee->foot (m_lowerLength = |wrist offset|)
        if upper<1e-3 or lower<1e-3: continue
        pi=bones[th]["parentIdx"]                   # thigh parent (pelvis), already FK-resolved
        Rp=wR[pi] if pi>=0 else I3
        H=list(wT[pi]) if pi>=0 else [0.0,0.0,0.0]
        H=v_add(H,mat_vec(Rp,bones[th].get("bindOffset",[0.0,0.0,0.0])))   # hip world pos (baseMatrix[3])
        poleParent=_v_scale(_col(Rp,2),-1.0)        # -parentZ  (engine InvertAxis(0)+(2); only Z is used)
        fq=channels.get(bones[fo]["name"]+" rot",[0.0,0.0,0.0,1.0])
        Rfoot=quat_to_mat(fq); footZ=_col(Rfoot,2)  # targetMatrix Z axis, for the bend-plane blend
        F=[tgt[0],tgt[1],tgt[2]]
        X=_v_sub(F,H); d=_v_len(X)                  # hip->foot direction + distance (sinUpperAngle)
        if d<1e-4: continue
        X=_v_norm(X)
        maxreach=upper+lower-0.001
        if d>maxreach:                              # foot beyond reach: clamp onto the leg line
            d=maxreach; F=v_add(H,_v_scale(X,maxreach))
        # bend-plane Y = blend of (parentZ x dir) and (footZ x dir); Z completes the orthonormal frame
        Yv=v_add(_v_cross(poleParent,X),_v_cross(footZ,X))
        if _v_len(Yv)<1e-6: Yv=[0.0,1.0,0.0]
        Yv=_v_norm(Yv); Zv=_v_cross(X,Yv)
        # law of cosines: cos(thigh angle) and -cos(interior knee angle)
        maxLength=(d*d+upper*upper-lower*lower)/(2.0*d*upper)
        maxLength=max(-1.0,min(1.0,maxLength))
        cosElbow=-((lower*lower+upper*upper-d*d)/(2.0*upper*lower))
        cosElbow=max(-1.0,min(1.0,cosElbow))
        sLen=-math.sqrt(max(0.0,1.0-maxLength*maxLength))   # -sin(thigh angle)
        # thigh: rotate (X,Y) within the bend plane by the thigh angle; columns are the axes
        Xt=[X[k]*maxLength-Yv[k]*sLen for k in range(3)]
        Yt=[X[k]*sLen+Yv[k]*maxLength for k in range(3)]
        R_th=[[Xt[r],Yt[r],Zv[r]] for r in range(3)]
        # calf: knee = hip + thighX*upper, then rotate the same frame by the knee angle
        K=v_add(H,_v_scale(Xt,upper))
        fLen=math.sqrt(max(0.0,1.0-cosElbow*cosElbow))      # sin(knee angle)
        Xc=[Xt[k]*cosElbow-Yt[k]*fLen for k in range(3)]
        Yc=[Xt[k]*fLen+Yt[k]*cosElbow for k in range(3)]
        R_ca=[[Xc[r],Yc[r],Zv[r]] for r in range(3)]
        wR[th]=R_th; wT[th]=list(H)
        wR[ca]=R_ca; wT[ca]=list(K)
        wR[fo]=[row[:] for row in Rfoot]; wT[fo]=list(F)    # foot orientation = wrist quat channel
        locked.update((th,ca,fo))
    return locked

def _world_to_local(bones,i,wR,wT):
    """Local (p,q) that reproduces this bone's world transform via parent*local FK - used to bake
    IK-solved leg bones into the same base/anim arrays the JS composes."""
    pi=bones[i]["parentIdx"]
    # bake to the SAME quat convention the JS viewer decodes with (quat_to_mat conjugates), else
    # every IK-baked leg bone is stored transposed -> shin twist/stretch in the viewer.
    if pi<0: return list(wT[i]), mat_to_localquat(wR[i])
    PR=_transpose3(wR[pi])
    lR=mat_mul(PR,wR[i]); lp=mat_vec(PR,_v_sub(wT[i],wT[pi]))
    return lp, mat_to_localquat(lR)


def compute_world(bones,channels):
    """World (R,T) per bone, resolved ON DEMAND the way the engine resolves it.

    MOHAA never does an "FK everything, then override with IK" pass. skelBone_Base::GetTransform
    returns the cached matrix or calls GetDirtyTransform (skeletorbones.cpp:474-481), and every
    GetDirtyTransform pulls what it needs recursively: m_parent->GetTransform for ordinary bones
    (:508/537/587/639), m_reference1/2 + m_parent for AvRot (:916-925), m_parent + m_target for
    HoseRot (:1100-1102, :1125-1127). skelBone_IKwrist::GetDirtyTransform forces the shoulder's
    IK solve before answering (:813-822), so a helper hanging off the foot ALWAYS reads the
    IK-SOLVED foot, never an FK stand-in.

    Solving the IK after the FK+helper walk left every ankle/knee helper (and the toe) posed
    against a STALE FK parent, and _world_to_local then baked that inconsistency into the
    sidecar. When an animation supplies both the rotFK chain and the matching foot target the
    two agree and the error is invisible - which is why scripted/smoking lightup.skc,
    firstinhale.skc and buttout.skc render correctly. But inhale.skc and throwaway.skc carry NO
    leg channels at all: their legs come from the MOVEMENT-SLOT donor while the ACTION still
    owns "Bip01 Pelvis rot", so the FK legs swing with the action pelvis while the foot targets
    stay pinned to the donor's ABSOLUTE model-space positions (skelBone_IKshoulder reads
    m_wristPos in the same space as baseMatrix[3], :682-700). The two then disagree by tens of
    units, helper offsets baked ~20u away from their bindOffset, and the leg garment - which
    carries most of its skin weight on those helpers - stretched into the reported spikes."""
    n=len(bones); wR=[None]*n; wT=[None]*n
    _ikbones=set()                        # thigh/calf/foot of every chain the IK owns this frame
    for _ch in _leg_ik_chains(bones):
        if channels.get(bones[_ch[2]]["name"]+" pos"): _ikbones.update(_ch)
    _iksolved=[False]
    def resolve(i):
        if wR[i] is not None: return
        bn=bones[i]; pi=bn["parentIdx"]
        if pi>=0: resolve(pi)
        if i in _ikbones and not _iksolved[0]:
            # First demand for ANY IK leg bone: pose the chains NOW, so children (Toe0) and
            # HoseRot/AvRot helpers resolved below always compose against the IK frame.
            # solve_ik_legs reads only each chain's thigh-PARENT world, so resolving those
            # parents first is all it needs - no FK stand-in for the leg bones themselves.
            _iksolved[0]=True
            for _th,_ca,_fo in _leg_ik_chains(bones):
                _pp=bones[_th]["parentIdx"]
                if _pp>=0: resolve(_pp)
            solve_ik_legs(bones,channels,wR,wT)   # 2-bone IK for the leg chains
            if wR[i] is not None: return
        if bn.get("boneType") in (5,6) and bn.get("solvable"):
            for r in bn["refIdx"]:           # references must be posed before the helper
                if r>=0: resolve(r)
            wR[i],wT[i]=_solve_helper_world(bones,i,wR,wT)  # engine-correct frame: leg AND arm helpers
            return
        p,q=_solved_local(bones,i,channels,wR,wT)
        lR=quat_to_mat(q); lT=list(p)
        if pi<0: wR[i]=lR; wT[i]=lT
        else: wR[i]=mat_mul(wR[pi],lR); wT[i]=v_add(mat_vec(wR[pi],lT),wT[pi])
    for i in range(n): resolve(i)
    return wR,wT

def skd_bind_dims(skd, channels=None):
    """The three bind-pose bounding-box extents (model units), sorted descending.
    Used to size .tik sub-model particles by true geometry and to derive their aspect
    ratio (longest/middle) so a spark sliver renders thin, not as a square blob."""
    bones=skd["bones"]
    wR,wT=compute_world(bones, channels or {})
    mn=[1e9,1e9,1e9]; mx=[-1e9,-1e9,-1e9]; any_v=False
    for s in skd["surfaces"]:
        for weights in s["verts"]:
            P=[0.0,0.0,0.0]
            for w in weights:
                bi,wv,off=w[0],w[1],w[2]
                wp=v_add(mat_vec(wR[bi],off),wT[bi])
                P=[P[k]+wv*wp[k] for k in range(3)]
            any_v=True
            for k in range(3):
                if P[k]<mn[k]: mn[k]=P[k]
                if P[k]>mx[k]: mx[k]=P[k]
    if not any_v: return (0.0,0.0,0.0)
    return tuple(sorted((mx[k]-mn[k] for k in range(3)), reverse=True))

def skd_bind_extent(skd, channels=None):
    """Longest bounding-box axis of a parsed .skd at its bind pose, in model units."""
    return skd_bind_dims(skd, channels)[0]

TAG_KEYWORDS=("tag","barrel","muzzle","turret","eject","gun","spew","emit",
              "eye","seat","flash","smoke","exhaust")
def find_tag_bones(skd_path,bone_names):
    folder=os.path.dirname(os.path.abspath(skd_path)); blob=""
    for tik in glob.glob(os.path.join(glob.escape(folder),"*.tik")):
        try: blob+=open(tik,"r",encoding="latin-1",errors="replace").read()+"\n"   # match the VFS codec
        except OSError: pass
    referenced=set()
    for nm in bone_names:
        if nm and re.search(r"(?<![\w])"+re.escape(nm)+r"(?![\w])",blob):
            referenced.add(nm)
    convention={nm for nm in bone_names if any(k in nm.lower() for k in TAG_KEYWORDS)}
    return referenced,convention

# ---------------------------------------------------------------------------
# .tik client emitter parsing (particle effects: fire, smoke, sparks, etc.)
# ---------------------------------------------------------------------------
def _strip_tik_comments(text):
    """Remove TikiScript comments. LINE comments (// ...) MUST be stripped FIRST,
    then block comments (/* ... */). Order matters: retail effect tiks decorate
    sections with banner lines like `//**********************`, and the `/*` inside
    such a `//` line is NOT a real block-comment opener. Stripping /* */ first (with
    DOTALL) made that stray `/*` pair with the file's trailing `*/QUAKED` close,
    swallowing everything in between - which ate the entire animations{} block of
    fx_oceanspray / fx_leaves_blowing, so their idle/start aliases vanished and the
    viewer fell back to the sibling .skc names (dummy2/dummy3). Killing // lines first
    removes the decoy `/*` before the block pass runs."""
    text="\n".join(line.split("//",1)[0] for line in text.splitlines())
    return re.sub(r'/\*.*?\*/','',text,flags=re.S)

_EM_SCALAR={"spawnrate":1,"count":1,"scale":1,"scalerate":1,"velocity":1,
            "alpha":1,"friction":1,"bouncefactor":1,"radius":1,"alignstretch":1,"fadedelay":1,
            "scalemin":1,"scalemax":1,"fadein":1,"spawnrange":1}
# accel & smokeparms share the engine's accel vector (cg_commands.cpp:1265 routes
# EV_Client_SetSmokeParms to ClientGameCommandManager::SetAccel, which stores GetFloat(1..3)
# into cgd.accel - :2866-2879 - so [typeinfo,fademult,scalemult] and world accel are ONE slot,
# last command wins). radialvelocity stores [scale,minAdd,maxAdd-minAdd] per SetRadialVelocity
# (:2739-2754: velocity[2] -= velocity[1]); the raw tik triple is kept here and the
# minAdd..maxAdd uniform draw is done at spawn in JS.
_EM_TRIPLE={"color","radialvelocity"}
# All of these route through SetBaseAndAmplitude (cg_commands.cpp:1462-1487), which accepts
# crandom/random/range per component - INCLUDING avelocity (SetAngularVelocity :2772-2795) and
# angles (SetAngles :2797-2820). avelocity was previously a plain triple, so every
# `avelocity crandom ...` (aircraft/barracks debris tumble, conflagration fire spin,
# oceanspray/leaves) silently failed to parse and the particles never rotated.
_EM_RANDTRIPLE={"offset","offsetalongaxis","randvel","randvelaxis","randaxis","angles","avelocity"}
# cone takes (height radius) per EV_Client_SetCone (SetCone, cg_commands.cpp:2326-2334:
# coneHeight=GetFloat(1), sphereRadius=GetFloat(2)); keep it flagged so the cone branch fires.
_EM_2ARG={"cone"}
_EM_FLAGS={"fade","collision","sphere","circle","randomroll",
           "align","alignonce","spin","tracer","inwardsphere","volumetric",
           # render/spawn hints that the engine accepts but the viewer treats as no-ops or handles
           # elsewhere - registered so they are never silently swallowed as stray tokens:
           "varycolor","alwaysdraw","spritegridlighting","startoff","parallel","scaleupdown",
           # flickeralpha (SetFlickerAlpha, cg_commands.cpp:2288-2297, T_FLICKERALPHA):
           # per-frame random alpha modulation, applied in the JS draw step.
           "flickeralpha"}
def _em_num(t):
    try: return float(t)
    except (TypeError,ValueError): return None
def _em_components(toks,i,n=3):
    comps=[]
    for _ in range(n):
        if i>=len(toks): break
        t=toks[i].lower()
        if t in ("crandom","random") and i+1<len(toks) and _em_num(toks[i+1]) is not None:
            comps.append([t,_em_num(toks[i+1])]); i+=2
        elif t=="range" and i+2<len(toks) and _em_num(toks[i+1]) is not None and _em_num(toks[i+2]) is not None:
            comps.append(["range",_em_num(toks[i+1]),_em_num(toks[i+2])]); i+=3   # amplitude, base
        elif _em_num(toks[i]) is not None:
            comps.append(["const",_em_num(toks[i])]); i+=1
        else:
            comps.append(["const",0.0]); i+=1
    return comps,i
def _em_body(body):
    toks=body.replace("("," ").replace(")"," ").split(); e={"flags":[]}; i=0
    while i<len(toks):
        k=toks[i].lower(); i+=1
        if k=="scale":
            # SetScale (cg_commands.cpp): `scale <base> [amplitude]` - optional 2nd float is a
            # random spawn amount added to base (T_RANDSCALE), same shape as `life <b> [a]`.
            # e.g. explosion_mine central cloud `scale 1.5 2.5`.
            if i<len(toks) and _em_num(toks[i]) is not None:
                e["scale"]=_em_num(toks[i]); i+=1
                if i<len(toks) and _em_num(toks[i]) is not None:
                    e["scalerand"]=_em_num(toks[i]); i+=1
        elif k in _EM_SCALAR:
            if i<len(toks) and _em_num(toks[i]) is not None: e[k]=_em_num(toks[i]); i+=1
        elif k=="life":
            # SetLife (cg_commands.cpp:2935-2952): `life <base> [amplitude]` - the optional
            # second float is life_random; per particle life = base + random()*amplitude
            # (SpawnTempModel, cg_tempmodels.cpp:1412-1414). Widely used: `life 3 1`,
            # `life 2.5 1` (higgins ring, gren_exp cloud, mortar dust, bombdirt cloud).
            if i<len(toks) and _em_num(toks[i]) is not None:
                e["life"]=_em_num(toks[i]); i+=1
                if i<len(toks) and _em_num(toks[i]) is not None:
                    e["liferand"]=_em_num(toks[i]); i+=1
        elif k=="color":
            # SetColor (cg_commands.cpp SetColor): 3 floats, plus an optional 4th that ALSO
            # sets cgd.alpha (`color .8 .8 .8 .5` in mortar_dirt's lingering mist).
            vals=[]
            while len(vals)<4 and i<len(toks) and _em_num(toks[i]) is not None: vals.append(_em_num(toks[i])); i+=1
            if len(vals)>=3: e["color"]=vals[:3]
            if len(vals)==4: e["alpha"]=vals[3]
        elif k in _EM_TRIPLE:
            vals=[]
            while len(vals)<3 and i<len(toks) and _em_num(toks[i]) is not None: vals.append(_em_num(toks[i])); i+=1
            if len(vals)==3: e[k]=vals
        elif k in ("accel","smokeparms"):
            # both events call SetAccel and share cgd.accel (cg_commands.cpp:1261+1265,
            # SetAccel :2866-2879) - last one wins, exactly like the engine. For volumetric
            # smoke the slot means [typeInfo, fadeMult, scaleMult] (SpawnVSSSource,
            # cg_volumetricsmoke.cpp:707-729); for tempmodels it is world acceleration.
            vals=[]
            while len(vals)<3 and i<len(toks) and _em_num(toks[i]) is not None: vals.append(_em_num(toks[i])); i+=1
            if len(vals)==3: e["accel"]=vals
        elif k=="swarm":
            # SetSwarm (cg_commands.cpp:2159-2170): `swarm <freq:int> <maxspeed> <delta>`;
            # sim per UpdateSwarm (cg_tempmodels.cpp:307-338). Also suppresses T2_ACCEL
            # (SetAccel :2874-2876 skips the flag when T_SWARM is set).
            vals=[]
            while len(vals)<3 and i<len(toks) and _em_num(toks[i]) is not None: vals.append(_em_num(toks[i])); i+=1
            if len(vals)==3: e["swarm"]=vals
            e["flags"].append("swarm")
        elif k=="clampvel":
            # SetClampVel (cg_commands.cpp:1763-1784): 6 floats minX maxX minY maxY minZ maxZ,
            # applied to velocity every physics tick (TempModelPhysics, cg_tempmodels.cpp:656-660).
            vals=[]
            while len(vals)<6 and i<len(toks) and _em_num(toks[i]) is not None: vals.append(_em_num(toks[i])); i+=1
            if len(vals)==6: e["clampvel"]=vals
        elif k in _EM_2ARG:
            vals=[]
            while len(vals)<2 and i<len(toks) and _em_num(toks[i]) is not None: vals.append(_em_num(toks[i])); i+=1
            e[k]=vals; e["flags"].append(k)
        elif k in _EM_RANDTRIPLE:
            e[k],i=_em_components(toks,i,3)
        elif k in ("model","emittermodel"):
            # tik authors sometimes quote the ref (`model "fire"` in hexsmoke01); the engine's
            # GetString strips quotes, so strip here too or the VSS-type / spritemap lookups miss.
            if i<len(toks): e["model"]=toks[i].strip('"'); i+=1
        elif k in _EM_FLAGS:
            e["flags"].append(k)
    return e
def parse_tik_emitters(text):
    """Extract *emitter ( ... ) particle blocks from a .tik file.

    Grammar per the cg_commands emitter events: `originemitter <name> (...)` and
    `tagemitter <tagname> <name> (...)` where the tag name may be a QUOTED string with
    spaces (EV_Client_TagEmitter takes tag + emitter name - breath_emitter's
    `tagemitter "smoke emitter" heavysmoke`). The old regex required the single token
    before '(' to directly follow the command word, so every tagemitter with a tag
    argument was silently skipped (breath_emitter / breath_steam_emitter showed nothing).

    Comments are stripped first (TikiScript skips // and /* */) so commented-out emitter
    blocks (e.g. breath_emitter's older heavysmoke variant) are not parsed as duplicates.

    The parameter block is scanned to the matching ')' but a '{' / '}' hard-terminates it:
    emitter blocks never contain braces, and retail data has typos where the closing ')'
    was typed as '(' (barracks_explosion's `test` mushroom-ring emitter ends
    `scalerate .25` + a stray '(') - without the brace stop, the block swallowed the rest
    of the file and the ring parsed as garbage. The engine survives the typo because its
    token-event parser is bounded by the init section's '}'."""
    out=[]
    t=_strip_tik_comments(text)
    for m in re.finditer(r'(?:commanddelay\s+([\d.]+)\s+)?(\w*emitter)'
                         r'((?:[ \t]+(?:"[^"\n]*"|[A-Za-z0-9_.]+)){1,2})\s*\(', t):
        kind=m.group(2).lower()
        args=re.findall(r'"[^"\n]*"|[A-Za-z0-9_.]+', m.group(3))
        name=args[-1].strip('"')
        start=m.end()-1; depth=0; j=start
        while j<len(t):
            c=t[j]
            if c=='(': depth+=1
            elif c==')':
                depth-=1
                if depth==0: break
            elif c=='{' or c=='}':          # typo guard: a block can never contain braces
                break
            j+=1
        e=_em_body(t[start+1:j]); e["name"]=name; e["kind"]=kind
        # tagemitter/tagspawn-style emitters anchor at the named tag; the tag is the first
        # argument when two are present.
        if len(args)>=2 and kind.startswith("tag"):
            e["tag"]=args[0].strip('"')
        # commanddelay <t> originemitter <name> (CommandDelay, cg_commands.cpp:1573-1607:
        # PostEventForEntity at +t) just delays this emitter's start by t seconds.
        if m.group(1) is not None:
            try: e["startdelay"]=float(m.group(1))
            except ValueError: pass
        out.append(e)
    return out
def parse_tik_init_sfx(text):
    """One-shot `sfx <spawncmd> ( ... )` / `delayedsfx <sec> <spawncmd> ( ... )`
    blocks (grenexp_water's four `sfx originspawn` water plumes). Per openmohaa,
    `sfx`/`delayedsfx` register the inner command into a special effect with
    fCommandTime=delay (EV_Client_SFXStart/SFXStartDelayed, cg_commands.cpp:
    1200-1215; StartSFXCommand :1623-1678 - block commands get their own
    spawnthing and the ( ... ) parameter block is processed into it); the whole
    command list then executes when the compiled effect is spawned. The viewer's
    equivalent of "effect spawned" is page load / Reset, so these are exported as
    fire-at-load one-shots. Comments are stripped first. Returns
    [{"delay":sec,"cmd":spawncmd,"tag":str|None,"prm":{...}}, ...]."""
    out=[]
    if not text: return out
    t=_strip_tik_comments(text)
    for m in re.finditer(r'(?im)^\s*(?:sfx|delayedsfx\s+([\d.]+))\s+'
                         r'(originspawn|tagspawn|tagspawnlinked)\b([^\n(]*)', t):
        delay=float(m.group(1)) if m.group(1) else 0.0
        cmd=m.group(2).lower()
        tag=None
        if cmd.startswith("tagspawn"):
            tt=(m.group(3) or "").split()
            if tt: tag=tt[0].strip('"')
        k=t.find("(",m.end())
        if k<0: continue
        depth=0; j=k
        while j<len(t):
            c=t[j]
            if c=="(": depth+=1
            elif c==")":
                depth-=1
                if depth==0: break
            j+=1
        out.append({"delay":delay,"cmd":cmd,"tag":tag,"prm":_em_body(t[k+1:j])})
    return out
def parse_tik_setup_head(text):
    """Return (path, skelmodel) for the BODY model from a .tik setup block, or (None,None).
    Comments are stripped first so a comment like '// Set path to set skelmodel from' is not
    mistaken for a real `skelmodel from` directive (that bug made every player/scientist .tik
    fail with "skelmodel 'from' not found"). Also tolerates the `$path`/`$skelmodel` macro
    spelling used by the player models, and matches only real directive lines (anchored at
    line start), taking the first body path + first body skelmodel."""
    t=_strip_tik_comments(text)   # // line comments first, then /* block */ (order matters)
    p=re.search(r'(?im)^\s*\$?path\s+(\S+)',t)
    s=re.search(r'(?im)^\s*\$?skelmodel\s+(\S+)',t)
    return (p.group(1) if p else None, s.group(1) if s else None)

def parse_tik_setsize(text):
    """Return (mins, maxs) as two [x,y,z] float triples from a .tik `setsize` command, else None.
    `setsize` is Entity's EV_SetSize server/client init event, whose spec is "vv" (two vectors,
    mins & maxs):  openmohaa code/fgame/entity.cpp:646-654 (EV_SetSize) and :3428-3435
    (Entity::SetSize -> min=GetVector(1), max=GetVector(2), setSize(min,max)). Each vector is a
    single token holding three floats (TikiScript::GetVector reads 3 floats,
    code/corepp/tiki_script.cpp:1099-1104), authored either quoted ("x y z") or bare; we pull the
    first 6 signed floats after the directive regardless of quoting."""
    if not text: return None
    t=_strip_tik_comments(text)
    m=re.search(r'(?i)\bsetsize\b([^\n]*)',t)
    if not m: return None
    nums=re.findall(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?',m.group(1))
    if len(nums)<6: return None
    v=[float(x) for x in nums[:6]]
    fmt=lambda x:int(x) if float(x).is_integer() else round(x,2)
    return [[fmt(v[0]),fmt(v[1]),fmt(v[2])],[fmt(v[3]),fmt(v[4]),fmt(v[5])]]

def parse_tik_scale(text):
    """The tik setup `scale <f>` -> load_scale (default 1.0). openmohaa TIKI_LoadSetup parses it at
    code/tiki/tiki_parse.cpp:1024-1026 and defaults it to 1.0 at :971; the renderer multiplies the
    model's verts and its mins/maxs by load_scale (code/renderergl2/tr_staticmodels.cpp:450-451,
    vMins[k]=mins[k]*load_scale*scale). setsize/.map values are already in that scaled world space,
    so the viewer divides them by load_scale to place the wireframe in the unscaled model space it
    renders in."""
    if not text: return 1.0
    t=_strip_tik_comments(text)
    m=re.search(r'(?im)^\s*scale\s+([-+]?\d*\.?\d+)',t)
    return float(m.group(1)) if m else 1.0

def parse_tik_classname(text):
    """The classname set in the tik's init/server block (`classname <Name>`), case-sensitive, or None.
    In TIKI this becomes the entity's classname via EV_Classname (spec "s", a single string) - openmohaa
    code/fgame/entity.cpp:67-77 - which selects the game class; the class-registry lookup is
    case-sensitive, so the value's case is preserved exactly. Comments and the /*QUAKED*/ block are
    stripped first so their text can't be mistaken for the command (the keyword may be any case, the
    value is returned verbatim)."""
    if not text: return None
    t=_strip_tik_comments(text)
    m=re.search(r'(?i)\bclassname\s+"?([^"\s]+)"?',t)
    return m.group(1) if m else None

def parse_tik_server_hidden(text):
    """True if the tik's init/server block hides the anchor model, so the viewer must not draw it.

    Three server commands make the mesh invisible in-engine, and effect-anchor tiks use them instead
    of (or alongside) `rendereffects +dontdraw`:
      - `hide`  -> Entity::hideModel() sets RF_DONTDRAW (entity.h:763) - the model is not drawn, exactly
                   like +dontdraw. (fx_cannonsmoke / fx_lowsmoke: a dummy3.skd anchor under a smoke
                   originemitter; the drawn dummy was the stray "yellow gem" at origin.)
      - `surface all +nodraw` -> flags nodraw on EVERY surface, so nothing of the mesh renders
                   (fx_nebelwerfer: the shell_bazooka rocket is hidden, only its smoke trail shows).
                   A per-surface `surface <name> +nodraw` hides just that one surface, NOT the model,
                   so only the `all` form counts as a whole-model hide here.
      - `ghost`  -> Entity::Ghost() only clears SOLID (entity.cpp:3180); it does NOT hide, so it is
                   intentionally ignored - hide is what does the hiding when the two are paired.
    Only the server{} sub-block is scanned so a `hide`/`nodraw` mentioned elsewhere can't false-trigger.
    Comments are stripped first (the commented-out `//classname Animate` etc. must not register)."""
    if not text: return False
    t=_strip_tik_comments(text)
    m=re.search(r'(?is)\binit\b.*?\bserver\b\s*\{(.*?)\}', t)
    srv=m.group(1) if m else t
    # `hide` as a standalone command (token-bounded, not a substring of e.g. hideme.skd), and
    # `surface all +nodraw` in any spacing/case. Works whether the tik writes them on their own
    # line or inline.
    if re.search(r'(?i)(?:^|[\s{;])hide(?=[\s;}]|$)', srv): return True
    if re.search(r'(?i)surface\s+all\s+\+?nodraw\b', srv): return True
    return False

_TIK_QTOKRE=re.compile(r'"([^"]*)"|(\S+)')
def _tik_qtokens(line):
    """Split one TikiScript line the way the engine's tokeniser does: whitespace-separated,
    except a double-quoted run is one token with the quotes removed (TikiScript::GetToken ->
    Script::GetToken, corepp/scriptvariable/script parser). `sethelmet "models/.../x.tik" 150
    0.1 "us_helmet"` is 5 tokens, not 5-plus-fragments, and a surface name with a space in it
    survives as one name."""
    return [(m.group(1) if m.group(1) is not None else m.group(2))
            for m in _TIK_QTOKRE.finditer(line)]

def _tik_blocks(text,kw):
    """Every `<kw> { ... }` body in a (comment-stripped, $include-expanded) tik, in file order.

    An expanded character tik carries several of each: dday_ranger_private.tik pulls in
    new_generic_human.tik and generic_dialogue_US.tik, and any of them may open its own
    setup{} / init{}. The engine executes them ALL (TikiScript splices the include inline and
    keeps parsing - tiki_script.cpp ProcessCommand), so a single re.search() would silently
    see only the first block and miss whatever a later include declares. Brace-matched via
    _brace_block, so nested `case weapon "..." { }` / `server { }` bodies come along whole."""
    out=[]; i=0
    pat=re.compile(r'(?i)(?<![A-Za-z0-9_])\$?'+re.escape(kw)+r'\s*\{')
    while True:
        m=pat.search(text,i)
        if not m: break
        oi=m.end()-1                       # the '{' the pattern ended on
        body,end=_brace_block(text,oi)
        out.append(body); i=max(end+1,m.end())
    return out

def parse_tik_static_nodraw(text):
    """Ordered surface +/-nodraw ops the .tik applies at LOAD, before any animation runs.

    Two different grammars raise the nodraw bit at spawn and both are honoured here:

      init{ server{ surface <name> +nodraw } }
          EV_SurfaceModelEvent is the ordinary entity command "surface", spec "sSSSSSS" -
          one surface name plus up to SIX flag tokens (fgame/entity.cpp:739-751) - so an
          init-server line runs once as the entity spawns. Entity::SurfaceCommand
          (entity.cpp:4158-4243) reads a leading '+' as FLAG_ADD and '-' as FLAG_CLEAR, and a
          bare token warns and is treated as '+' (:4181-4195); `nodraw` maps to
          MDL_SURFACE_NODRAW (:4204) which is then OR'd / AND-NOT'd into
          edict->s.surfaces[n] (:4230-4237). SurfaceModelEvent (:4249-4260) replays the
          command once per token. dday_ranger_private.tik uses exactly this form to keep the
          twelve bangalore surfaces off until the assembly animation asks for them.

      setup{ surface <name> flags nodraw }
          A DIFFERENT grammar: TIKI_ParseSetup (tiki/tiki_parse.cpp:1060-1082) requires the
          literal `flags` keyword, and TIKI_ParseSurfaceFlag (:513-537) has no +/- form - it
          only ever SETS a bit (TIKI_SURF_NODRAW). Collected as an unconditional hide.

    Name matching is the engine's, and it is NOT a glob: a trailing '*' is a case-insensitive
    PREFIX test over everything before the star. SurfaceCommand strncmps strlen(name)-1
    characters (:4222-4227) and TIKI_InitTiki does the same against strchr(name,'*')
    (tiki/tiki_files.cpp:390-406). The raw pattern is therefore forwarded verbatim and
    resolved on the JS side by surfIdxByName(), which already implements that exact rule -
    and which is the only place the fully assembled, multi-.skd surface list exists.

    `surface all +nodraw` is deliberately NOT returned. parse_tik_server_hidden() already
    turns that form into a whole-model hide (dontdraw), so emitting it here as well would
    strike out every row in the surface list while un-hiding any one of them still drew
    nothing - two controls disagreeing about the same state.

    Returns [{"name": pattern, "nodraw": bool}, ...] in file order; later ops win, which is
    what lets a `-nodraw` further down the file clear an earlier `+nodraw`."""
    if not text: return []
    t=_strip_tik_comments(text)
    ops=[]
    # ---- setup{ ... surface <name> [flags nodraw] ... } ------------------------------
    # `case` sub-blocks are inside the setup body and come along with it. A case whose
    # skelmodel the viewer never loads simply resolves to no surface indices in JS, so
    # scanning them costs nothing and keeps the parse faithful to the file.
    _SETUP_KW={"flags","damage","shader","skin1","skin2","skin3"}
    for body in _tik_blocks(t,"setup"):
        for line in body.splitlines():
            tok=_tik_qtokens(line)
            if len(tok)<2 or tok[0].lower().lstrip("$")!="surface": continue
            low=[x.lower() for x in tok]
            # the name runs from arg 1 up to the first sub-keyword (surface names may
            # contain spaces, which is why mohaa_textures.parse_tik_setup joins them too)
            kw=next((k for k in range(2,len(tok)) if low[k] in _SETUP_KW),len(tok))
            name=" ".join(tok[1:kw]).strip()
            if not name or name.lower()=="all": continue
            # TIKI_InitTiki's wildcard test is `strptr && strptr != loadsurf->name`
            # (tiki_files.cpp:403): a name whose FIRST character is '*' never matches
            # through the wildcard path, it falls through to the exact-name compare and
            # warns. (The init-server grammar differs - SurfaceCommand only treats a
            # TRAILING '*' as a wildcard - and surfIdxByName already mirrors that.)
            if name.startswith("*"): continue
            if any(low[k]=="flags" and k+1<len(low) and low[k+1]=="nodraw"
                   for k in range(2,len(tok))):
                ops.append({"name":name,"nodraw":True})
    # ---- init{ server{ surface <name> +nodraw ... } } --------------------------------
    for ib in _tik_blocks(t,"init"):
        for srv in _tik_blocks(ib,"server"):
            for line in srv.splitlines():
                tok=_tik_qtokens(line)
                if len(tok)<3 or tok[0].lower()!="surface": continue
                name=tok[1].strip()
                if not name or name.lower()=="all": continue
                for a in tok[2:]:
                    if a.lstrip("+-").lower()!="nodraw": continue
                    # no sign at all = FLAG_ADD (the engine warns, then adds) - :4191-4194
                    ops.append({"name":name,"nodraw":not a.startswith("-")})
    return ops

def parse_map_bounds(path):
    """World-space (game-unit) AABB [mins,maxs] of a model .map's clip brushes, or None.

    A model .map (e.g. models/static/indycrate.map) is an id/Quake brush file: worldspawn holds
    brushes, each a set of faces written as three plane points `( x y z ) ( x y z ) ( x y z ) <shader>
    <texinfo...>`. The three points only DEFINE the face's infinite plane - they are NOT the brush's
    corners. Taking the AABB of the raw points therefore over-reports badly on angled brushes (a
    plane point can sit far outside the solid, e.g. hedgehog / higginsxtrahull). We reproduce what the
    compiler does: build each brush's real volume from its planes and bound the resulting vertices -
    openmohaa CreateBrushWindings (code/tools/ommap/brush.c:249) clips a base winding by every other
    face plane, then BoundBrush (:216) accumulates mins/maxs from the winding points. Equivalently we
    take every triple-plane intersection that lies inside all of that brush's half-spaces (its true
    vertices) and union across brushes. Plane convention is MapPlaneFromPoints (code/tools/ommap/
    map.c:261): normal = norm(cross(p0-p1, p2-p1)); dist = dot(p0, normal); interior = dot(n,x) <= dist.
    setsize is scale-independent (it's the raw collision hull), so no load_scale is applied here.
    Returned as setsize does: [[minx,miny,minz],[maxx,maxy,maxz]]."""
    try: txt=open(path,encoding="latin-1",errors="replace").read()
    except OSError: return None
    # parse brushes by brace depth: entity = depth 1, each brush = depth 2
    brushes=[]; depth=0; cur=None
    for line in txt.splitlines():
        s=line.strip()
        if not s or s.startswith("//"): continue
        if s=="{":
            depth+=1
            if depth==2: cur=[]
            continue
        if s=="}":
            if depth==2 and cur is not None: brushes.append(cur); cur=None
            if depth>0: depth-=1
            continue
        if cur is not None:
            m=re.findall(r'\(\s*(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s*\)',s)
            if len(m)>=3: cur.append([tuple(float(v) for v in t) for t in m[:3]])
    if not brushes: return None
    def _sub(a,b): return (a[0]-b[0],a[1]-b[1],a[2]-b[2])
    def _dot(a,b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
    def _cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    def _plane(f):   # MapPlaneFromPoints (ommap/map.c:261)
        n=_cross(_sub(f[0],f[1]),_sub(f[2],f[1])); L=(n[0]*n[0]+n[1]*n[1]+n[2]*n[2])**0.5
        if L<1e-9: return None
        return ((n[0]/L,n[1]/L,n[2]/L), _dot(f[0],n)/L)
    def _solve3(pa,pb,pc):   # intersection of three planes via Cramer's rule
        (a,b,c),d1=pa; (e,f,g),d2=pb; (h,i,j),d3=pc
        det=a*(f*j-g*i)-b*(e*j-g*h)+c*(e*i-f*h)
        if abs(det)<1e-6: return None
        x=(d1*(f*j-g*i)-b*(d2*j-g*d3)+c*(d2*i-f*d3))/det
        y=(a*(d2*j-g*d3)-d1*(e*j-g*h)+c*(e*d3-d2*h))/det
        z=(a*(f*d3-d2*i)-b*(e*d3-d2*h)+d1*(e*i-f*h))/det
        return (x,y,z)
    EPS=0.1; lo=[1e18]*3; hi=[-1e18]*3; found=False
    for b in brushes:
        pls=[p for p in (_plane(f) for f in b) if p]
        n=len(pls)
        for ia in range(n):
            for ib in range(ia+1,n):
                for ic in range(ib+1,n):
                    x=_solve3(pls[ia],pls[ib],pls[ic])
                    if x is None: continue
                    if all(_dot(nrm,x)<=d+EPS for (nrm,d) in pls):
                        found=True
                        for k in range(3):
                            if x[k]<lo[k]: lo[k]=x[k]
                            if x[k]>hi[k]: hi[k]=x[k]
    if not found: return None
    def fmt(v):
        r=round(v,2)
        return int(r) if r==int(r) else r
    return [[fmt(lo[0]),fmt(lo[1]),fmt(lo[2])],[fmt(hi[0]),fmt(hi[1]),fmt(hi[2])]]

# ---- case-aware skelmodel extraction ----
# Engine ref: TIKI_ParseCase / TIKI_LoadSetupCaseHeader / TIKI_LoadSetupCase (tiki_parse.cpp)
# A `case <key> <val...> { ... }` block is a switch—TIKI_LoadSetupCaseHeader matches
# keyValues[key] against the listed values and sets skip=true on every non-matching branch.
# The old flat regex collected ALL skelmodels from ALL branches, so head .tik files (which
# are entirely case blocks) rendered every head mesh stacked at the origin.

def _tik_strip(text):
    return _strip_tik_comments(text)

def _tik_tokens(text):
    return re.findall(r'\{|\}|\S+', text)

def _tik_skip_braces(tokens, i):
    """Skip the { ... } block whose '{' was already consumed; i points to first inner token.
    depth starts at 1. Returns ([], next_i_after_closing_})."""
    depth=1; n=len(tokens)
    while i<n and depth:
        if tokens[i]=='{': depth+=1
        elif tokens[i]=='}': depth-=1
        i+=1
    return [], i

def _tik_case_header(tokens, i):
    """Read `<key> <val...> [case <key> <val...>...] {`.
    Multiple `case key val` lines chained before `{` are OR'd (engine: goto __newcase).
    Returns (key_str, [val_strs], next_i_after_{)."""
    n=len(tokens); key=None; vals=[]; want_key=True
    while i<n:
        t=tokens[i]; tl=t.lower()
        if t=='{': return key,vals,i+1
        if tl=='case': want_key=True; i+=1; continue     # chained 'case' – re-read key
        if want_key: key=tl if key is None else key; want_key=False; i+=1
        else: vals.append(tl); i+=1
    return key,vals,i

def _tik_eval_block(tokens, i, cur_path, kv):
    """Evaluate tokens inside (or at top of) a block, collecting (path,skelmodel) pairs.
    Stops at the matching '}' or end of tokens. kv: resolved {case_key: chosen_value} dict.
    Engine: TIKI_LoadSetupCase applies skelmodel only when skip=False (branch matched)."""
    parts=[]; n=len(tokens); decided={}   # decided: which case-keys are already resolved here
    while i<n:
        t=tokens[i]; tl=t.lower()
        if t=='}': return parts,i+1
        if tl in('path','$path') and i+1<n:
            cur_path=tokens[i+1]; i+=2; continue
        if tl in('skelmodel','$skelmodel') and i+1<n:
            parts.append((cur_path,tokens[i+1])); i+=2; continue
        if tl=='case':
            ckey,cvals,i=_tik_case_header(tokens,i+1)
            if ckey is None: continue
            kv_val=kv.get(ckey)
            if ckey in decided:                                   # later branch for same key → skip
                _,i=_tik_skip_braces(tokens,i)
            elif kv_val is not None and kv_val in cvals:          # explicit match
                decided[ckey]='match'
                sub,i=_tik_eval_block(tokens,i,cur_path,kv); parts.extend(sub)
            elif kv_val is None:                                   # key absent → first branch wins
                decided[ckey]='default'
                sub,i=_tik_eval_block(tokens,i,cur_path,kv); parts.extend(sub)
            else:                                                   # key present, no match → skip
                _,i=_tik_skip_braces(tokens,i)
            continue
        i+=1
    return parts,i

def parse_tik_skelmodels(text, key_values=None):
    """Ordered (path, skelmodel) list for a .tik, evaluating case blocks correctly.
    key_values: dict e.g. {"headskin":"bignose","headmodel":"head4"}. When a case key has
    no entry in key_values the FIRST branch is taken (viewer default – one head, not all).
    Engine ref: tiki_parse.cpp TIKI_ParseCase + TIKI_LoadSetupCaseHeader – only the branch
    whose values match keyValues[key] is loaded; unmatched branches are fully skipped."""
    t=_tik_strip(text)
    ms=re.search(r'(?im)^\s*setup\b',t)
    if ms:
        bo=t.find('{',ms.end())
        if bo>=0: t,_=_brace_block(t,bo)
    toks=_tik_tokens(t)
    kv={k.lower():v.lower() for k,v in (key_values or {}).items()}
    parts,_=_tik_eval_block(toks,0,None,kv)
    return parts

def _brace_block(text,open_idx):
    """Given the index of a '{' in text, return (inner_text, end_idx_of_close)."""
    depth=0
    for j in range(open_idx,len(text)):
        c=text[j]
        if c=='{': depth+=1
        elif c=='}':
            depth-=1
            if depth==0: return text[open_idx+1:j], j
    return text[open_idx+1:], len(text)

# the schedule loops back-to-back at its own length (no dead tail): the in-game effect
# re-triggers continuously, so the lingering smoke (life ~1s, emitted up to sched end)
# overlaps into the next cycle and stays present instead of clearing to an empty gap.
FX_LOOP_TAIL=0.0
def parse_tik_anim_commands(text):
    """Parse the *start* animation's client emitter commands into a per-emitter on/off
    schedule, so the viewer can fire a timed burst sequence instead of running every
    emitter continuously. Returns {"period":sec,"sched":{name:[[on,off],...]}} or None.

    Scoped STRICTLY to the `start` anim block: effects like electric_arc/welding turn
    their emitters on in `start` and off only in a separate `stop` anim, so within `start`
    they are on-with-no-off -> omitted here -> the viewer keeps emitting them continuously
    (no regression). Only emitters with a matching emitteroff inside `start` become timed.
    `enter` commands fire at t=0; an optional `commanddelay <sec>` sets the offset."""
    ma=re.search(r'\banimations\b\s*\{',text)
    if not ma: return None
    anim_body,_=_brace_block(text, ma.end()-1)
    # find the `start` anim block within the animations body
    ms=re.search(r'\bstart\b\s+\S+\.skc\s*\{', anim_body, re.I)
    if not ms:
        # fall back: first anim entry that actually carries a body with client commands
        for mm in re.finditer(r'\b\w+\b\s+\S+\.skc\s*\{', anim_body):
            blk,_=_brace_block(anim_body, mm.end()-1)
            if re.search(r'emitter(on|off)', blk, re.I): ms=mm; break
        if not ms: return None
    start_body,_=_brace_block(anim_body, ms.end()-1)
    # gather all client { } blocks inside the start anim
    cmds=""
    for mc in re.finditer(r'\bclient\b\s*\{', start_body):
        cb,_=_brace_block(start_body, mc.end()-1); cmds+=cb+"\n"
    if not cmds.strip(): return None
    events={}   # name -> list of (time, on?)
    sched_end=0.0
    for raw in cmds.splitlines():
        line=raw.split("//",1)[0]
        toks=line.split()
        if not toks: continue
        low=[t.lower() for t in toks]
        if "emitteron" not in low and "emitteroff" not in low: continue
        # time offset: commanddelay <sec>, else 0 (enter)
        t=0.0
        if "commanddelay" in low:
            k=low.index("commanddelay")
            if k+1<len(toks):
                try: t=float(toks[k+1])
                except ValueError: t=0.0
        on=("emitteron" in low); key="emitteron" if on else "emitteroff"
        k=low.index(key)
        if k+1>=len(toks): continue
        name=toks[k+1]
        events.setdefault(name,[]).append((t,on))
        if t>sched_end: sched_end=t
    sched={}
    for name,evs in events.items():
        evs.sort(key=lambda x:x[0])
        ivals=[]; pending=None
        for (t,on) in evs:
            if on: pending=t
            else:
                if pending is not None: ivals.append([pending,t]); pending=None
        if pending is not None and ivals:
            # a trailing on with no off, but it had earlier closed windows: leave it on to end
            ivals.append([pending, sched_end])
        # pending-with-no-closed-interval => on-with-no-off => continuous => omit (not added)
        if ivals: sched[name]=ivals
    if not sched: return None
    sched_end=round(sched_end,3)
    if sched_end<=0: return None
    # The level re-triggers a one-shot fx repeatedly; the cadence the player sees is that
    # re-fire rate, NOT one play-through of the schedule. The last emitteron (here name2/smoke
    # @1.0) marks when the effect's buildup completes and a fresh instance can start while the
    # lingering elements overlap, so use the latest on-time as the re-fire interval and run each
    # instance for the full schedule length. Pure one-shots (everything on @0) just loop end-to-end.
    max_on=0.0
    for evs in events.values():
        for (t,on) in evs:
            if on and t>max_on: max_on=t
    refire=round(max_on,3) if max_on>0.05 else sched_end
    return {"period":refire,"refire":refire,"schedlen":sched_end,"sched":sched}

# ---------------------------------------------------------------------------
# TIKI animations{} parsing: per-animation aliases, .skc refs and frame commands
# ---------------------------------------------------------------------------
# Frame keyword map per TIKI_ParseFrameCommands (openmohaa code/tiki/tiki_parse.cpp:
# 112-124): "start"/"first" -> TIKI_FRAME_FIRST, "end" -> TIKI_FRAME_END, "last" ->
# TIKI_FRAME_LAST, "every" -> TIKI_FRAME_EVERY, "exit" -> TIKI_FRAME_EXIT,
# "entry"/"enter" -> TIKI_FRAME_ENTRY, anything else -> atoi(frame number).
_FRAME_KEYS={"entry":"entry","enter":"entry","first":"first","start":"first",
             "last":"last","end":"end","every":"every","exit":"exit"}

def _tik_argv(line):
    """Split a frame-command line into tokens, keeping "quoted names" whole.

    MOHAA bone names contain spaces - new_generic_human.tik smoking04 has
    `21 tagspawn "Bip01 L Finger11"` - and a plain .split() turned that into three
    tokens, so rest[0] was "Bip01": the flicked cigarette spawned at the PELVIS ROOT
    instead of the left hand. TikiScript's lexer treats a double-quoted run as one
    token (tiki_script.cpp TikiScript::GetToken, the '"' branch), so do the same."""
    # finditer, not findall: findall yields '' (not None) for the group that did not
    # participate, so an "is not None" test silently turns every bare token into ''.
    return [m.group(1) if m.group(1) is not None else m.group(2)
            for m in re.finditer(r'"([^"]*)"|(\S+)', line)]

def _parse_frame_cmds(sect):
    """Parse one client{}/server{} frame-command section body into a list of
    {"at": keyword-or-int, "argv":[tokens], "prm": dict|None}. A command is one
    line: <frame> <cmd> [args...]; a following ( ... ) parameter block belongs to
    that command (tiki_parse.cpp:125-133 sets usecurrentframe inside parens) and
    is decoded with the same _em_body used for setup emitters. The paren block
    may open on the command line or on the next line (both occur in retail
    tiks - jeep.tik opens on the next line)."""
    out=[]; i=0; n=len(sect); cur=None
    def _paren_block(k):
        depth=0; m=k
        while m<n:
            c=sect[m]
            if c=="(": depth+=1
            elif c==")":
                depth-=1
                if depth==0: return sect[k+1:m], m
            m+=1
        return sect[k+1:], n-1
    while i<n:
        j=sect.find("\n",i); j=n if j<0 else j
        stripped=sect[i:j].strip()
        if stripped.startswith("("):
            k=sect.find("(",i)
            inner,m=_paren_block(k)
            if cur is not None: cur["prm"]=_em_body(inner)
            i=m+1; continue
        toks=_tik_argv(stripped)
        if toks:
            t0=toks[0].lower()
            at=_FRAME_KEYS.get(t0)
            if at is None and re.fullmatch(r"-?\d+",t0): at=int(t0)
            if at is not None and len(toks)>1:
                if "(" in stripped:                    # inline '(' on the command line
                    argv=[]
                    for t in toks[1:]:
                        if t.startswith("("): break
                        argv.append(t)
                    cur={"at":at,"argv":argv,"prm":None}
                    k=sect.find("(",i)
                    inner,m=_paren_block(k)
                    cur["prm"]=_em_body(inner)
                    out.append(cur); i=m+1; continue
                cur={"at":at,"argv":toks[1:],"prm":None}
                out.append(cur)
        i=j+1
    return out

def parse_tik_animations(text):
    """Parse the .tik `animations{}` section into a list of
    {"name":alias, "file":<skc ref>, "flags":[...], "client":[cmd], "server":[cmd]}.
    Grammar per TIKI_ParseAnimations (openmohaa code/tiki/tiki_parse.cpp:397-):
    each entry is `alias filename [flags...]` - flags per TIKI_ParseAnimationFlags
    (:230-268: weight/crossblend take a value, deltadriven/default_angles/
    notimecheck/dontrepeate/random/autosteps_* are bare) - optionally followed by
    a `{ client{...} server{...} }` block (TIKI_ParseAnimationCommands :192-226).
    $mapspec sub-sections are skipped. Comments are stripped first."""
    if not text: return []
    t=_strip_tik_comments(text)
    ma=re.search(r'\banimations\b\s*\{', t)
    if not ma: return []
    body,_=_brace_block(t, ma.end()-1)
    out=[]; i=0; n=len(body)
    while i<n:
        while i<n and body[i] in " \t\r\n": i+=1
        if i>=n: break
        if body[i]=="{":                       # stray block: skip balanced
            _,end=_brace_block(body,i); i=end+1; continue
        j=body.find("\n",i); j=n if j<0 else j
        toks=body[i:j].split()
        if not toks: i=j+1; continue
        if toks[0].lower()=="$mapspec":        # skip a mapspec sub-section entirely
            k=body.find("{",i)
            if k<0: break
            _,end=_brace_block(body,k); i=end+1; continue
        if toks[0].startswith("$"):
            # a TikiScript directive ($path / $include / $define), consumed by the
            # script layer before TIKI_ParseAnimations runs (tiki_script.cpp:383-425).
            # Registering it as an alias is what produced the "$path (1f)" entry.
            i=j+1; continue
        if len(toks)>=2:
            entry={"name":toks[0],"file":toks[1],"flags":toks[2:],"client":[],"server":[]}
            i=j+1
            k=i                                 # optional command block follows?
            while k<n and body[k] in " \t\r\n": k+=1
            if k<n and body[k]=="{":
                blk,end=_brace_block(body,k)
                for ms in re.finditer(r'\b(client|server)\b\s*\{', blk):
                    sb,_=_brace_block(blk, ms.end()-1)
                    entry[ms.group(1).lower()]+=_parse_frame_cmds(sb)
                i=end+1
            out.append(entry)
        else:
            i=j+1
    return out

def _surf_nodraw_ops(cmds):
    """Every `surface <name> <+/-nodraw ...>` frame command in a parsed client/server
    command list, as [{"at":..,"name":..,"nodraw":bool}, ...] in FILE ORDER.

    Shared by the baked-in animations{} path and the on-demand sidecar path so the two can
    never drift. Semantics are Entity::SurfaceCommand's (fgame/entity.cpp:4158-4243):
    a leading '+' sets MDL_SURFACE_NODRAW, '-' clears it, and a bare token is treated as
    '+' after a warning (:4181-4195). SurfaceModelEvent (:4249-4260) replays the command
    once per token, so ONE line may carry several flags - the event spec is "sSSSSSS", a
    surface name plus up to six of them (:739-751). Scanning only argv[2] therefore
    dropped every flag after the first; the loop below matches the engine.

    Names are forwarded verbatim: the trailing-'*' prefix rule is resolved viewer-side by
    surfIdxByName(), which is where the assembled surface list lives."""
    out=[]
    for c in cmds:
        argv=c.get("argv") or []
        if len(argv)<3 or argv[0].lower()!="surface": continue
        nm=argv[1].strip('"')
        for tok in argv[2:]:
            if tok.lstrip("+-").lower()!="nodraw": continue
            out.append({"at":c["at"],"name":nm,"nodraw": not tok.startswith("-")})
    return out

def anim_sidecar_fx(server_txt):
    """Frame-command fx for an ON-DEMAND animation, rebuilt from the catalogue's raw
    server{} text.

    build_anim_catalog already keeps each animation's client{}/server{} block verbatim
    (mohaa_textures _cat_animations -> _cat_add_anim, fields "c" and "v"), because the
    catalogue is walked before the $include splice and is the only place those blocks
    survive for an animation the primary .tik never lists inline. The sidecar builder read
    only "n" and "s" out of that record, so every frame command of every on-demand
    animation was silently discarded - which is why bangalore_assembly played its 117
    frames of pose data while its 32 surface toggles did nothing at all.

    ONLY the surface toggles are rebuilt here. The other frame commands cannot be honoured
    from a sidecar: client tagspawn/originspawn blocks need new DATA.emitters entries with
    resolved sprites, and those are baked into the page at build time; `emitteron/off`
    names emitters this model does not have. Both are page-level, not per-animation."""
    if not server_txt: return None
    ops=_surf_nodraw_ops(_parse_frame_cmds(server_txt))
    if not ops: return None
    return {"spawn":[],"emit":[],"surf":ops}

_SPAWN_CMDS=("tagspawn","originspawn","tagspawnlinked")
# `explosioneffect <type>` (server command, Explosion::MakeExplosionEffect,
# fgame/weaputils.cpp:1664-1689) sends a CGM to the client; CG_MakeExplosionEffect
# (cgame/cg_parsemsg.cpp:1011-1068) maps the type to a base explosion .tik via the SFX
# manager (cg_specialfx.cpp:231-346). tankshellexplosion.tik's `first explosioneffect
# bazooka` therefore just plays models/fx/bazookaexp_base.tik. Surface variants (dirt/
# stone/snow) exist but the viewer has no world surface under the effect, so - exactly like
# the engine's air/no-trace path (cg_parsemsg.cpp:1068, MakeEffect_Normal(iBaseEffect)) - we
# always use the _base tik. Unknown types fall back to grenade, matching the engine default.
_EXPLOSIONEFFECT_TIK={
    "grenade":"models/fx/grenexp_base.tik",
    "bazooka":"models/fx/bazookaexp_base.tik",
    "heavyshell":"models/fx/heavyshellexp_base.tik",
    "tank":"models/fx/tankexp_base.tik",
}
def _strip_cmd_prefix(argv):
    """Strip command-wrapper prefixes off a frame-command token list, returning
    (core_cmd_lower, remaining_args, accumulated_delay_seconds). Wrappers per
    openmohaa cg_commands.cpp:
      commanddelay <sec> <cmd> [args...] - re-posts <cmd> at +sec
        (CommandDelay: ev1=new Event(GetString(2)); PostEventForEntity(ev1,fWait),
         cg_commands.cpp:1573-1607)
      sfx <cmd> [args...] / delayedsfx <sec> <cmd> [args...] - special-effect
        wrappers registering the inner command with fCommandTime=delay
        (EV_Client_SFXStart/SFXStartDelayed :1200-1215; StartSFXCommand :1623-1678)
    Wrappers can chain (e.g. `enter commanddelay 60 emitteroff smoke`); every
    numeric delay along the way accumulates. Returns (None,[],delay) when no
    core command follows the wrappers."""
    delay=0.0; i=0
    while i<len(argv):
        t=argv[i].lower()
        if t in ("commanddelay","delayedsfx"):
            if i+1<len(argv):
                try: delay+=float(argv[i+1])
                except ValueError: pass
            i+=2; continue
        if t=="sfx":
            i+=1; continue
        break
    if i>=len(argv): return None,[],delay
    return argv[i].lower(), argv[i+1:], delay

def tik_anim_fx(ta, emitters):
    """Convert one parsed tik animation's frame commands into the viewer's per-anim
    fx dict, appending each client tagspawn/originspawn parameter block onto the
    shared `emitters` list as a one-shot (animfx) entry.

    Engine semantics: tagspawn/originspawn spawn `count` tempmodels ONCE per command
    execution at the tag's / entity's current orientation - not a stream
    (cg_commands.cpp BeginTagSpawn:3534 -> EndTagSpawn:3561 -> SpawnEffect(count) ->
    SpawnTempModel; count defaults to 1, InitializeSpawnthing :3058). Commands may be
    wrapped by `commanddelay <sec>` (fx_bike_explosion `entry commanddelay 0.100
    originspawn`) - the wrapper only delays execution (CommandDelay,
    cg_commands.cpp:1573-1607), so the block fires `delay` seconds after its frame
    trigger. Client `emitteron <n>` / `emitteroff <n>` toggle the named init-block
    emitter's active state (EmitterOn/Off, cg_commands.cpp:3789-3835), again with an
    optional commanddelay (fx_explosion_tank `enter commanddelay 60 emitteroff
    smoke`). Server `surface <name> +/-nodraw` toggles MDL_SURFACE_NODRAW on the
    named surface, with `all` and trailing-* prefix wildcards (fgame/entity.cpp
    SurfaceCommand:4158-4212, SurfaceModelEvent:4248).
    Returns {"spawn":[{"em":[idx...],"at":..,"delay":sec?}],
             "emit":[{"at","name","on","delay"}],
             "surf":[{"at","name","nodraw"}]} or None."""
    spawn=[]; surf=[]; emit=[]
    for c in ta.get("client",[]):
        argv=c.get("argv") or []
        if not argv: continue
        cmd,rest,delay=_strip_cmd_prefix(argv)
        if cmd in _SPAWN_CMDS and c.get("prm"):
            prm=dict(c["prm"])
            prm["name"]="animfx_%s_%d"%(ta["name"],len(emitters))
            prm["kind"]=cmd
            prm["animfx"]=True
            if cmd.startswith("tagspawn") and rest:
                prm["tag"]=rest[0].strip('"')
            emitters.append(prm)
            ent={"em":[len(emitters)-1],"at":c["at"]}
            if delay>0: ent["delay"]=round(delay,4)
            spawn.append(ent)
        elif cmd in ("emitteron","emitteroff") and rest:
            emit.append({"at":c["at"],"name":rest[0].strip('"'),
                         "on":(cmd=="emitteron"),"delay":round(delay,4)})
    attach=[]; detach=[]
    for c in ta.get("server",[]):
        argv=c.get("argv") or []
        if not argv: continue
        _c0=argv[0].lower()
        # attachmodel <model> <tag> [scale] ...      (docs: attachmodel(modelname, tagname,
        # [scale], [targetname], ...)). Recorded per frame so the viewer can hang the model
        # on at the right moment AND take it off when the animation ends. The .tik cannot be
        # trusted to clean up: smoking02 and smoking03 both attach breath_emitter.tik to
        # "Bip01 Head" with no removeattachedmodel and no removetime, which per the docs
        # means never removed - exactly what piles models up over repeated playback.
        if _c0=="attachmodel" and len(argv)>=3:
            _sc=1.0
            if len(argv)>=4:
                try: _sc=float(argv[3])
                except Exception: _sc=1.0
            attach.append({"at":c["at"],"model":argv[1].strip('"'),
                           "tag":argv[2].strip('"'),"scale":_sc})
            continue
        if _c0=="removeattachedmodel" and len(argv)>=2:
            detach.append({"at":c["at"],"tag":argv[1].strip('"')})
            continue
        if len(argv)>=3 and argv[0].lower()=="surface":
            surf+=_surf_nodraw_ops([c])      # one line may carry up to six flag tokens
            continue
        # explosioneffect <type> -> play the mapped base explosion .tik once at this frame.
        # Emitted as a normal one-shot originspawn whose `model` is the base tik; the launcher's
        # sub-tik resolver + expand_subfx flatten that tik's own emitters (crate chunks, fire
        # ring, smoke, ...) into drawable entries, exactly as for any other .tik model ref.
        ecmd,erest,edelay=_strip_cmd_prefix(argv)
        if ecmd=="explosioneffect":
            etype=(erest[0].strip('"').lower() if erest else "grenade")
            tik=_EXPLOSIONEFFECT_TIK.get(etype,_EXPLOSIONEFFECT_TIK["grenade"])
            prm={"name":"animfx_%s_%d"%(ta["name"],len(emitters)),
                 "kind":"originspawn","animfx":True,"model":tik,"count":1,
                 "color":[1.0,1.0,1.0]}
            emitters.append(prm)
            ent={"em":[len(emitters)-1],"at":c["at"]}
            if edelay>0: ent["delay"]=round(edelay,4)
            spawn.append(ent)
    if not spawn and not surf and not emit and not attach and not detach: return None
    out={"spawn":spawn,"surf":surf,"emit":emit}
    if attach: out["attach"]=attach
    if detach: out["detach"]=detach
    return out

def expand_subfx(emitters, anims_data, spritemap):
    """Flatten one level of spawned dummy-.tik tempmodels. A tagspawn/originspawn
    whose model is a skelmodel-only fx tik (snipesmoke, gas_mushroom_cloud) draws
    nothing itself - its look is its OWN idle-anim `enter originspawn` one-shots
    plus init-client emitters running on the spawned tempmodel. The launcher exports
    those inner blocks as spritemap[ref]["subfx"]; here each parent spawn EM entry
    is replaced by its sub entries, inheriting the parent's tag anchor, one-shot
    trigger, and scale multiplier (the tempmodel's scale scales its children).
    Inner init emitters become timed streams (`subdur` = the parent tempmodel's
    life) carried along a vertical ballistic approximation of the tempmodel's own
    velocity/accel, so e.g. the mushroom column climbs while it puffs."""
    if not spritemap or not anims_data: return 0
    added=0
    for a in anims_data:
        fx=a.get("fx")
        if not fx: continue
        for sp in fx.get("spawn",[]):
            newem=[]
            for ei in sp["em"]:
                e=emitters[ei]
                sub=e.pop("_subfx",None)
                if not sub:
                    newem.append(ei); continue
                pscale=float(e.get("scale",1.0) or 1.0)
                pcount=int(e.get("count",1) or 1)
                plife=float(e.get("life",1.0) or 1.0)
                pvel=float(e.get("velocity",0.0) or 0.0)
                pacc=e.get("accel") or [0,0,0]
                for sprm in sub:
                    q=dict(sprm); q["animfx"]=True
                    q["name"]="%s_sub%d"%(e.get("name","animfx"),len(emitters))
                    if e.get("tag"): q["tag"]=e["tag"]
                    for k in ("scale","scalemin","scalemax"):
                        if q.get(k) is not None: q[k]=round(q[k]*pscale,4)
                    if q.get("scale") is None and q.get("scalemin") is None and pscale!=1.0:
                        q["scale"]=pscale
                    if pcount>1: q["count"]=int(q.get("count",1) or 1)*pcount
                    if q.pop("stream",False):
                        q["subdur"]=plife
                        q["carrier"]=[0.0,0.0,pvel]
                        q["carrieracc"]=[float(pacc[0] or 0),float(pacc[1] or 0),float(pacc[2] or 0)]
                    ref=(q.get("model") or "").lower()
                    ent=spritemap.get(ref)
                    if ent is not None and not (isinstance(ent,dict) and ent.get("subfx")):
                        q["sprite"]=ent
                        if isinstance(ent,dict):
                            for kk in ("basesize","baseaspect","mesh","texw","texh","alphatest","bundle","erode_sprite"):
                                if ent.get(kk): q[kk]=ent[kk]
                            if "additive" in ent: q["additive"]=ent["additive"]
                            if ent.get("volumetric"): q["volumetric"]=True
                            if ent.get("spritescale"): q["spritescale"]=ent["spritescale"]
                            if ent.get("sprite_type"): q["sprite_type"]=ent["sprite_type"]
                            if ent.get("lightglow"): q["lightglow"]=True
                    emitters.append(q); newem.append(len(emitters)-1); added+=1
            sp["em"]=newem
    return added

def write_obj(path,bones,surfaces,wR,wT,tagset):
    lines=["# exported by mohaa_view.py","# Y-up, units = model space"]; vbase=1
    for s in surfaces:
        lines.append("g "+s["name"]); nlocal=0
        for weights in s["verts"]:
            p=[0.0,0.0,0.0]
            for bi,wt,ofx in weights:
                wp=v_add(mat_vec(wR[bi],ofx),wT[bi]); p=[p[k]+wt*wp[k] for k in range(3)]
            yp=to_yup(p); lines.append("v %.4f %.4f %.4f"%(yp[0],yp[1],yp[2])); nlocal+=1
        for (a,bb,c) in s["tris"]:
            lines.append("f %d %d %d"%(vbase+a,vbase+bb,vbase+c))
        vbase+=nlocal
    R=4.0
    faces=[(0,2,4),(2,1,4),(1,3,4),(3,0,4),(2,0,5),(1,2,5),(3,1,5),(0,3,5)]
    for bi,bn in enumerate(bones):
        if bn["name"] not in tagset: continue
        c=to_yup(wT[bi])
        pts=[[c[0]+R,c[1],c[2]],[c[0]-R,c[1],c[2]],[c[0],c[1]+R,c[2]],
             [c[0],c[1]-R,c[2]],[c[0],c[1],c[2]+R],[c[0],c[1],c[2]-R]]
        lines.append("g TAG_"+bn["name"].replace(" ","_"))
        for p in pts: lines.append("v %.4f %.4f %.4f"%(p[0],p[1],p[2]))
        for (a,bb,c2) in faces: lines.append("f %d %d %d"%(vbase+a,vbase+bb,vbase+c2))
        vbase+=6
    # encoding pinned: bone/surface names come out of the .skd as latin-1 and a bare
    # open(...,"w") would encode them with the LOCALE codec, raising UnicodeEncodeError
    # on a CJK Windows the moment a name carries a non-ASCII byte.
    with open(path,"w",encoding="utf-8",errors="replace") as f:
        f.write("\n".join(lines)+"\n")

# ---------------------------------------------------------------------------
# Per-animation pose solving, shared by the full-page build and the on-demand
# (single animation) build the launcher fires when the viewer asks for one that
# was not baked into the page. Kept as one function so both paths produce byte-
# identical frame data - the IK/helper baking below is the only correct source.
# ---------------------------------------------------------------------------
def anim_solver_ctx(bones):
    """(helper bone indices, leg IK chains) for this skeleton - computed once and
    reused for every animation solved against it."""
    helper_idx=[bi for bi,bn in enumerate(bones) if bn.get("boneType") in (5,6) and bn.get("solvable")]   # leg + arm helpers
    return helper_idx,_leg_ik_chains(bones)

def _driven_helpers(bones,helper_idx,leg_chains,chan):
    """Subset of `helper_idx` whose HoseRot/AvRot solve is actually DRIVEN by this animation.

    A helper's frame is computed from its reference/target bones' WORLD transforms
    (_solve_helper_world), so it is only meaningful when the animation supplies those bones'
    pose. MOHAA torso animations are upper-body-only - skeletor_loadanimation.cpp:325-331 sets
    bHasUpper from "Bip01 Spine rot"+"Bip01 Spine1 rot" alone - and carry NO leg channels:
    weapon_mp44/mp44_reload.skc and weapon_rifle/prone/rifle_prone_shoot.skc hold only Bip01/
    Pelvis/Spine/Neck/Head, both arms' rot chains and the weapon tags. In-engine they are ACTION
    animations blended over a separate MOVEMENT/legs animation (rifle_prone_legs.skc,
    pistol_prone_legs.skc), and skelAnimStoreFrameList_c::GetSlerpValue / GetLerpValue3
    (skeletorbones.cpp:264-435) take any channel the action lacks from the movement frames -
    GetLocalFromGlobal returns -1 and that frame contributes nothing.

    Solving such a frame against its own channels alone leaves thigh->calf->foot at identity,
    collapsing the IK leg into a straight ~92u line (see the ALLIED_PILOT_POSE note). Baking the
    LEG helpers off that collapsed chain drags the leg garment - which carries most of the leg
    skin weight - into elongated, hip-pinched spikes, while the real leg bones correctly fall back
    to the base pose. Dropping the undriven helpers from the frame lets them fall back to base
    too, so the entire leg rides the ANIMATED pelvis in its base-relative pose: the standalone
    viewer's equivalent of the engine's movement slot. Gating is by refIdx, not by bone name, so
    it needs no keyword list and cannot mis-scope."""
    ik_leg={}
    for (th,ca,fo) in leg_chains:
        has=(bones[fo]["name"]+" pos") in chan
        for bi in (th,ca,fo): ik_leg[bi]=has
    def driven(bi):
        if ik_leg.get(bi): return True          # IK leg bone posed from the foot target
        nm=bones[bi]["name"]
        return (nm+" rotFK") in chan or (nm+" rot") in chan or (nm+" pos") in chan
    out=[]
    for hi in helper_idx:
        refs=[r for r in bones[hi].get("refIdx",[]) if r>=0]
        if refs and all(driven(r) for r in refs): out.append(hi)
    return out

def solve_anim(bones,a,helper_idx=None,leg_chains=None,movement=None):
    """One anims_data entry ({"name","data",["fx"]}) -> the viewer's per-anim record
    {"name","frameTime","frames":[{boneIdx:[px,py,pz,qx,qy,qz,qw]}],["fx"]}.

    `movement` is an optional MOVEMENT-SLOT channel dict (frame 0 of a full-body .skc). MOHAA
    never plays a torso animation alone: skelAnimStoreFrameList_c holds movement frames AND
    action frames, and GetSlerpValue / GetLerpValue3 (skeletorbones.cpp:264-435) take any
    channel the action lacks from the movement frames - GetLocalFromGlobal returns -1 and that
    slot contributes nothing. Overlaying `movement` beneath each action frame IS that blend:
    the action's own channels always win, the movement slot fills only the gaps (the legs and
    "Bip01 pos"). Passing None keeps the previous single-slot behaviour byte-for-byte."""
    if helper_idx is None or leg_chains is None:
        helper_idx,leg_chains=anim_solver_ctx(bones)
    mv=movement or {}
    # every frame of a .skc shares one channel list, so resolve the driven set once per anim
    fr_helpers=_driven_helpers(bones,helper_idx,leg_chains,
                               set(a["data"].get("names") or [])|set(mv))
    frames=[]
    for _raw in a["data"]["frames"]:
        fr={**mv,**_raw} if mv else _raw
        d={}
        for bi,bn in enumerate(bones):
            nm=bn["name"]
            if nm+" rotFK" in fr or nm+" rot" in fr or nm+" pos" in fr:
                p,q=bone_local(bn,fr)
                if bn.get("boneType")==1 and (nm+" pos") not in fr:
                    # POSROT bone whose TRANSLATION this animation does not supply. bone_local
                    # falls back to bindOffset, but the SKD stores no offset for a POSROT bone -
                    # position is a channel (TIKI_CacheFileSkel -> CreatePosRotBoneData,
                    # tiki_skel.cpp:422-435) - so bindOffset is [0,0,0]. Emitting that zero
                    # OVERRODE the base pose: on every upper-body-only .skc (which carry
                    # "Bip01 rot" but no "Bip01 pos") it dropped Bip01 from its +103.19 root
                    # height to the model origin and sank the whole model ~104u through the grid.
                    # Emit a 4-element ROTATION-ONLY entry instead, so worldFromPose takes the
                    # translation from DATA.base[i].p. That is the engine's movement-slot
                    # behaviour: GetLerpValue3 (skeletorbones.cpp:366-435) contributes nothing
                    # for an absent channel and the blended movement animation supplies it.
                    # Old cached sidecars are all 7-element and still decode on the other branch.
                    d[bi]=[round(q[0],5),round(q[1],5),round(q[2],5),round(q[3],5)]
                else:
                    d[bi]=[round(p[0],3),round(p[1],3),round(p[2],3),
                           round(q[0],5),round(q[1],5),round(q[2],5),round(q[3],5)]
        fr_ik=[(th,ca,fo) for (th,ca,fo) in leg_chains if (bones[fo]["name"]+" pos") in fr]
        if fr_helpers or fr_ik:  # re-pose DRIVEN helpers + IK legs for this frame
            fwR,fwT=compute_world(bones,fr)
            for bi in fr_helpers:             # bake the engine-solved helper world frame
                p,q=_world_to_local(bones,bi,fwR,fwT)
                d[bi]=[round(p[0],3),round(p[1],3),round(p[2],3),
                       round(q[0],5),round(q[1],5),round(q[2],5),round(q[3],5)]
            for (th,ca,fo) in fr_ik:           # override FK rotFK with the IK-solved leg
                for bi in (th,ca,fo):
                    p,q=_world_to_local(bones,bi,fwR,fwT)
                    d[bi]=[round(p[0],3),round(p[1],3),round(p[2],3),
                           round(q[0],5),round(q[1],5),round(q[2],5),round(q[3],5)]
        frames.append(d)
    out={"name":a["name"],"frameTime":round(a["data"]["frameTime"],5),"frames":frames}
    if a.get("fx"): out["fx"]=a["fx"]     # per-anim TIKI client/server fx (spawn bursts, surface nodraw)
    return out

def build_payload(skd,anims_data,base_channels,referenced,convention,wT_payload,textures=None,emitters=None,dontdraw=False,fxcmds=None,setsize=None,scale=1.0,classname=None,animskind=None,initfx=None,animcat=None,animdir=None,animfx=None,tiknodraw=None):
    bones=skd["bones"]
    out_bones=[{"name":bn["name"],"parent":bn["parentIdx"]} for bn in bones]
    base=[]
    _bwR,_bwT=compute_world(bones,base_channels)   # resolves solvable HoseRot/AvRot helper frames + IK legs
    _ik_set=set()                                  # leg bones the IK solver drove this pose
    for _th,_ca,_fo in _leg_ik_chains(bones):
        if (bones[_fo]["name"]+" pos") in base_channels: _ik_set.update((_th,_ca,_fo))
    for bi,bn in enumerate(bones):                 # solvable leg helpers carry a SOLVED world too
        if bn.get("boneType") in (5,6) and bn.get("solvable"): _ik_set.add(bi)   # bake solved world for leg + arm helpers
    for bi,bn in enumerate(bones):
        if bi in _ik_set:                          # bake the IK-solved world, not the FK rotFK
            p,q=_world_to_local(bones,bi,_bwR,_bwT)
        else:
            p,q=_solved_local(bones,bi,base_channels,_bwR,_bwT)
        base.append({"p":[round(x,4) for x in p],"q":[round(x,5) for x in q]})
    verts=[]; uvs=[]; tris=[]; surf_ranges=[]; vbase=0
    morphmap={}
    for s in skd["surfaces"]:
        start=len(tris); vstart=vbase
        _sm=s.get("morphs")
        for _vi,weights in enumerate(s["verts"]):
            verts.append([[w[0],round(w[1],4),round(w[2][0],3),round(w[2][1],3),round(w[2][2],3)] for w in weights])
            if _sm and _vi<len(_sm) and _sm[_vi]:
                # Sparse on purpose: on a body+head model only ~400 of ~2900 vertices carry
                # deltas, so a dense parallel array would be mostly nulls. 6 decimals - the
                # deltas run 0.0007..0.03 and are multiplied by weights up to 100.
                morphmap[str(len(verts)-1)]=[c for (mi,off) in _sm[_vi]
                                             for c in (mi,round(off[0],6),round(off[1],6),round(off[2],6))]
        for st in s.get("uvs",[]):
            uvs.append(round(st[0],4)); uvs.append(round(st[1],4))
        for (a,b,c) in s["tris"]: tris.append([vbase+a,vbase+b,vbase+c])
        vbase+=len(s["verts"])
        sr={"name":s["name"],"start":start,"end":len(tris),"vstart":vstart,"vend":vbase}
        # MOHAA cull_* garment shaders disable backface culling (cull none/twosided). The
        # cullpants/cullshirt ankle + inner-leg panels are thin two-sided shells; the backface
        # cull in draw() shatters them into slivers (the "pinched ankle"/shards). Flag them so
        # both faces draw. Driven by the shader's real `cull` keyword when textures supplies it
        # (twosided), with the cull* surface-name convention as a self-contained fallback.
        if s["name"].lower().startswith("cull"): sr["twosided"]=True
        if textures is not None:
            ent=textures.get(s["name"].lower())   # data URL string, or {tex,additive,autosprite,frames,fps}
            if isinstance(ent,dict):
                sr["tex"]=ent.get("tex")
                if ent.get("additive"): sr["additive"]=True
                if ent.get("autosprite"): sr["autosprite"]=True
                if ent.get("autosprite2"): sr["autosprite2"]=True
                if ent.get("lightglow"): sr["lightglow"]=True
                if ent.get("twosided") or str(ent.get("cull","")).lower() in ("none","disable","twosided","two-sided"): sr["twosided"]=True
                if ent.get("frames"): sr["frames"]=ent["frames"]
                if ent.get("fps"): sr["fps"]=ent["fps"]
                if ent.get("pulse"): sr["pulse"]=ent["pulse"]
                # base-stage `tcmod rotate <deg/sec>` (RB_CalcRotateTexMatrix,
                # tr_shade_calc.c:809-826): the whole texture spins about its centre - the
                # aircraft propeller discs (prop / c47prop). clamp keeps the clampmap border
                # clean as the spinning texcoords sweep past [0,1].
                if ent.get("texrotate"): sr["texrotate"]=ent["texrotate"]
                if ent.get("clamp"): sr["clamp"]=True
                # alphaGen distFade / oneMinusDistFade LOD window (tr_shader.c :1168-1194).
                # {near,range,inv} - the camera-distance ramp that swaps a tree's real leaf
                # cards for its flat billboard stand-in.
                if ent.get("distfade"): sr["distfade"]=ent["distfade"]
                if ent.get("atest"): sr["atest"]=ent["atest"]
                if ent.get("flap"): sr["flap"]=ent["flap"]
            elif ent:
                sr["tex"]=ent
        surf_ranges.append(sr)
    anims=[]
    helper_idx,leg_chains=anim_solver_ctx(bones)
    _mnames=skd.get("morphNames") or []
    for a in anims_data:
        if a.get("morph"):
            _t=morph_track(a["data"],_mnames)
            if _t:
                anims.append({"name":a["name"],"frames":[{} for _ in _t["frames"]],
                              "mw":_t["frames"]})
                continue
        _rec=solve_anim(bones,a,helper_idx,leg_chains)
        if _mnames:
            # Face layer: the animation's OWN morph channels when the .skc carries both
            # (models/human/animation/misc), otherwise a MORPH sibling beside it
            # (models/human/animation/scripted/smoking). Either way one record, one clock.
            _t=morph_track(a["data"],_mnames)
            if _t: _rec["mw"]=_t["frames"]
            else:
                _sib=morph_sibling_path(a.get("src"))
                if _sib:
                    try:
                        _st=morph_track(parse_skc(_sib),_mnames)
                        if _st: _rec["mw"]=resample_mw(_st["frames"],len(_rec["frames"]))
                    except Exception: pass
        anims.append(_rec)
    tags=[]
    for bi,bn in enumerate(bones):
        nm=bn["name"]; nml=nm.lower()
        # origin markers: named Box*/Object*/*origin*, OR positioned at/near (0,0,0).
        t=wT_payload[bi]; at_origin=(abs(t[0])<0.5 and abs(t[1])<0.5 and abs(t[2])<0.5)
        origin=(nml.startswith("box") or nml.startswith("object") or "origin" in nml or at_origin)
        kind="tag" if (nm in referenced or nm in convention) else "bone"
        tags.append({"name":nm,"idx":bi,"kind":kind,"origin":origin,
                     "pos":[round(t[0],1),round(t[1],1),round(t[2],1)]})
    return {"bones":out_bones,"base":base,"verts":verts,"uvs":uvs,"tris":tris,
            "morphNames":(skd.get("morphNames") or []),"morphs":morphmap,
            "animfx":(animfx or {}),
            "surfRanges":surf_ranges,"anims":anims,"tags":tags,"emitters":emitters or [],
            "dontdraw":bool(dontdraw),"fxcmds":fxcmds,"setsize":setsize,"setsizeScale":scale,"classname":classname,
            "animsKind":(animskind or "skc"),"initfx":initfx,
            # surface +/-nodraw ops the .tik applies at spawn, in file order. Patterns, not
            # indices: surfIdxByName() in the page resolves them against the ASSEMBLED
            # multi-.skd surface list using the engine's own `all` + trailing-* prefix rule.
            "tikNodraw":(tiknodraw or []),
            "animCat":animcat,"animDir":animdir}

def _html_esc(s):
    return (str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            .replace('"',"&quot;").replace("'","&#39;"))

def _js_lit(s):
    """A JS string literal safe to paste into an INLINE <script>.

    json.dumps quotes and backslash-escapes correctly but leaves '<' and '>' alone, so a
    value holding the literal '</script>' still closes the block the literal sits in.
    U+2028/U+2029 are line terminators in JS but not in JSON, so they are escaped too."""
    return (json.dumps(str(s)).replace("<","\\u003c").replace(">","\\u003e")
            .replace("&","\\u0026").replace("\u2028","\\u2028").replace("\u2029","\\u2029"))

def write_html(path,title,payload,theme=None):
    # Model data is UNTRUSTED: surface names, shader names, fx strings and the tik
    # classname all come out of whatever .pk3 the user loaded. json.dumps does not escape
    # '<', so a string carrying '</script>' would terminate the inline block early and
    # turn the remainder of the payload into HTML. Escaping the three sequences that can
    # break out keeps the JSON semantically identical (\uXXXX is just a JSON string escape)
    # while making it inert to the HTML tokeniser.
    data_json=(json.dumps(payload,separators=(",",":"))
               .replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026"))
    repl={"__TITLE__":_html_esc(title), "__TITLE_JS__":_js_lit(title),
          "__DATA__":data_json, "__REV__":str(VIEWER_REV),
          # --theme launch flag: bake the initial theme; empty string = auto (saved choice)
          "__THEME__":(theme if theme in ("light","dark") else "")}
    # ONE pass, so a substituted value can never be re-scanned as another token - a model
    # named "__DATA__" must not splice the whole payload into the <title>.
    html=re.sub(r"__(?:TITLE_JS|TITLE|DATA|REV|THEME)__",lambda m:repl[m.group(0)],_HTML_TEMPLATE)
    open(path,"w",encoding="utf-8").write(html)

# Bumped whenever the generated page gains features that a cached HTML must pick
# up (the launcher rebuilds any saved HTML whose baked rev is older than the rev
# it requires). rev 2: backdrop colour picker. rev 3: dead-GL-canvas backdrop fix.
# rev 4: GL `tcmod rotate` propeller spin. rev 5: same spin in the 2D fallback path.
# rev 6: 2D prop clamp (no corner tiling) + no flat-shade (transparent disc, not a square).
# rev 4: embed-hash boot (in-launcher layout + theme applied before first paint).
# rev 7: DEFORM_LIGHTGLOW coronas -> camera-facing billboard (autosprite) + opt-in
#        toward-eye push / synthetic placement orbit ('Corona orbit' toggle, view.tilt).
# rev 8: LightGlow toward-eye push is now always-on (pins glow ~4u in front -> grows/fills the
#        screen as the camera nears, never vanishes); size cap lifted for lightglow. 'Corona
# orbit' toggle now gates ONLY the synthetic placement swing.
# rev 9: LightGlow pin divided by tik load_scale (DATA.setsizeScale) - the viewer renders in
#        unscaled skd space, so a scale>1 corona (e.g. scale 16) no longer freezes on zoom; the
#        glow now grows to fill the screen as the camera nears, matching in-game.
# rev 10: corona-orbit reworked - distance-gated (game units), zero beyond ~50u, logarithmic
#         growth, capped near origin; orbit is now a pure perpendicular swing that no longer
#         changes glow size. Tuning knobs ORBIT_START/ORBIT_CAP/ORBIT_MAX in lightGlowCenter.
# rev 11: corona scaling reverted to real-object perspective (no toward-eye pull) - the glow now
#         grows continuously by radius*focal/dist and reaches max size only at closest approach,
#         instead of over-inflating and freezing early. Orbit unchanged.
# How many catalogued animations may be baked straight into the page. At or under
# this count the whole set is solved up front (effects, vehicles, weapons - their
# per-anim fx must be present the moment the page loads); above it the page ships
# the menu only and each animation is built on first click into the cache folder
# beside the HTML. Overridable per run with --animpreload=<n>.
ANIM_PRELOAD_MAX=150

# rev 37: security hardening - the page is now built with the model payload and title
#         escaped for inline-<script> embedding (a .pk3 string containing '</script>'
#         used to break out of the block) and carries a CSP that pins every source to
#         self/file/data/blob with connect-src 'none'. Pages baked before rev 37 lack
#         both, so they must be rebuilt rather than served from the output-folder cache.
# rev 62: two editors that used to be read-only or absent. (a) A model whose .tik declares
#         no `setsize` (and has no sibling .map to borrow a box from) now shows a dimmed
#         placeholder `setsize ( 0 0 0 ) ( 0 0 0 )` whose pencil MATERIALISES the box and
#         un-greys the Display > Setsizes toggle. (b) The placement-angle dial gained a
#         pencil of its own, so pitch/yaw/roll take ANY value instead of only the four
#         quarter-turn detents, and the slider thumb parks between tick marks to show it.
#         Pages baked before rev 62 have neither, so they must be rebuilt.
# rev 63: an ATTACHED model is now textured like the model it hangs off. Two halves: the
#         launcher resolves its surfaces against the attachment's own .tik (it was handing
#         the texture pass a .tik path where a .skd path was wanted, so muzflash.tik picked
#         up an unrelated sibling's `material1`), and the at<key>.js sidecar now carries the
#         shader's render hints - additive, cull none, autosprite, animmap frames, alphaFunc
#         - instead of flattening them to a bare image. A muzzle flash therefore draws as an
#         additive two-sided sprite rather than an opaque card. Sidecars written before rev
#         63 hold the wrong texture and no hints, so they must be rebuilt (the .rev stamp in
#         the sidecar folder clears them).
# rev 64: the attach-to-bone OFFSET is now in engine world units - the number a .tik or
#         script `attachmodel` line actually carries - instead of the viewer's own unscaled
#         model units. Calibrated in-game against 15cmcannon and 20mmflak; see ATT_OFS.
VIEWER_REV=64

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<!--mohaa-viewer-rev:__REV__-->
<html lang="en"><head><meta charset="utf-8">
<!-- The page is built from an untrusted .pk3. The viewer is 100% offline, so pinning
     every fetchable source to self/file/data/blob and connect-src to 'none' costs it
     nothing and removes the only thing injected script could usefully do here: phone
     home. WebView2's ExecuteScriptAsync runs outside page CSP, so the launcher's
     MOHAA_ANIM_LOAD / MOHAA_ANIM_FAIL calls are unaffected. -->
<meta http-equiv="Content-Security-Policy" content="default-src 'self' 'unsafe-inline' data: blob: file:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ - MOHAA viewer</title>
<style>
 :root{--bg:#0e1116;--panel:#161b22;--line:#2b333d;--txt:#d6dde6;--dim:#8b97a6;
       --tag:#f2f5f8;--origin:#c084fc;--sel:#7ee787;--hidden:#3a4654;--accent:#7ee787;
       --btn:#21272f;--onbg:#2d3a2d;--btnhover:#3d4754;--grid:#1b212a;--labelbg:8,11,16;
       --err:#f85149;}
 :root.light{--bg:#f5f7fa;--panel:#ffffff;--line:#d0d7de;--txt:#1f2328;--dim:#57606a;
       --tag:#7c6408;--origin:#8250df;--sel:#0969da;--hidden:#c0c7cf;--accent:#0969da;
       --btn:#eef1f4;--onbg:#ddebff;--btnhover:#c2ccd6;--grid:#cdd5dd;--labelbg:255,255,255;
       --err:#cf222e;}
 /* ---- cascading animation menu ------------------------------------------
    One panel per open level. The whole cascade grows LEFTWARD from the button
    (the panel that holds it is pinned to the right edge of the window), so a
    submenu never runs off-screen behind the model view. */
 #animMenu{position:fixed;left:0;top:0;width:100%;height:100%;z-index:60;display:none}
 #animMenu.on{display:block}
 .amPanel{position:absolute;display:flex;flex-direction:column;background:var(--panel);
   border:1px solid var(--line);border-radius:6px;box-shadow:0 8px 26px rgba(0,0,0,.45);
   width:300px;max-height:78vh;padding:4px 0}
 .amBody{overflow-y:auto;overflow-x:hidden;min-height:0}
 .amItem{display:flex;align-items:center;gap:6px;padding:3px 8px;cursor:pointer;
   white-space:nowrap;overflow:hidden}
 .amItem.hot{background:var(--btnhover)}   /* the ONLY highlight source: :hover is
    deliberately not styled, or a stationary pointer would keep a second row lit
    while the arrow keys move the real one. amRow's mousemove drives .hot instead. */
 .amItem .lbl{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis}
 .amItem .cnt{color:var(--dim);font-size:11px}
 .amItem .arw{color:var(--dim);font-size:11px}
 .amItem.grp .lbl{color:var(--accent)}
 .amItem.sel{background:var(--onbg)}
 .amItem.have .lbl::after{content:' \2022';color:var(--accent)}
 /* Same bullet as .have, but red. A build that failed once will fail again -
    the _face entries are facial MORPH tracks (BROW_*, EYES_*, VISEME_*) that
    drive no bones on this skeleton - so the row has to stay marked. */
 .amItem.failed .lbl::after{content:' \2022';color:var(--err)}
 .amItem.failed .cnt{color:var(--err)}
 /* A surface that is currently +nodraw. This is a real element in our own popup, not an
    <option> in a native <select>, so ONE ordinary rule does the whole job - the old
    three-signal hack (text-decoration + U+0336 combining overlay + a leading glyph) only
    existed because <option> styling is honoured by Chromium and dropped by other engines. */
 .amItem.nod .lbl{color:var(--err);text-decoration:line-through;text-decoration-thickness:2px}
 .amItem.nod .cnt,.amItem.nod .arw{color:var(--err)}
 .attBox{border-left:2px solid var(--btn);margin:3px 0 5px 0}
 #surfRow{margin-top:10px}
 #attRow{margin-top:4px}
 .amHead{display:flex;align-items:center;gap:6px;padding:3px 6px 5px 6px;color:var(--dim);
   font-size:11px;border-bottom:1px solid var(--line);margin-bottom:4px}
 .amHead .amPathTxt{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .amHead .amCnt{color:var(--dim)}
 .amUp{padding:2px 7px;font-size:11px;background:var(--btn);color:var(--txt);
   border:1px solid var(--line);border-radius:4px;cursor:pointer;white-space:nowrap;
   font-family:inherit}
 .amUp:hover:enabled{background:var(--btnhover);color:var(--accent)}
 .amUp:disabled{opacity:.35;cursor:default}
 .amSearch{width:calc(100% - 12px);margin:2px 6px 5px 6px;padding:3px 6px;
   background:var(--btn);color:var(--txt);border:1px solid var(--line);border-radius:4px;
   font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
 .amNote{padding:4px 8px;color:var(--dim);font-size:11px;white-space:normal}
 #animBtn,#surfBtn,#attBoneBtn{display:flex;align-items:center;gap:6px}
 #animBtn .albl,#surfBtn .albl,#attBoneBtn .albl{flex:1;min-width:0;overflow:hidden;
   text-overflow:ellipsis;white-space:nowrap;text-align:left}
 #animBtn .acar,#surfBtn .acar,#attBoneBtn .acar{color:var(--dim);font-size:10px}
 .attMdl{display:inline-flex;align-items:center;gap:5px;max-width:152px}
 .attMdl .albl{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left}
 .attMdl .acar{color:var(--dim);font-size:10px;flex:none}
 *{box-sizing:border-box} html,body{margin:0;height:100%;background:var(--bg);
   color:var(--txt);font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
 #wrap{display:flex;height:100vh}
 #stage{flex:1;position:relative;min-width:0}
 /* two stacked canvases fill the stage: #gl (WebGL, model + grid) underneath,
    #c (Canvas 2D overlay: billboards, particles, nodes, labels, setsize) on top.
    DOM order does the stacking - no z-index, so #hint/#sideTab stay above. */
 #stage canvas{position:absolute;left:0;top:0;display:block;width:100%;height:100%;cursor:grab}
 #stage canvas:active{cursor:grabbing}
 #side{width:328px;background:var(--panel);border-left:1px solid var(--line);
   display:flex;flex-direction:column;overflow-y:auto;overflow-x:hidden}
 .sect{padding:10px 12px;border-bottom:1px solid var(--line)}
 /* embedded in the launcher (URL hash #embed): the launcher's own top bar already
    hosts Theme / Shortcuts, so the viewer's duplicate MODEL row is hidden up-front
    via this rule (set by the head boot script before first paint) - no post-load
    JS reflow, no "webpage layout flashes then swaps to in-launcher layout". */
 :root.embed #modelSect{display:none}
 .sect h2{margin:0 0 8px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}
 h1{margin:0;font-size:14px;color:var(--accent)} .sub{color:var(--dim);font-size:11px}
 .row{display:flex;align-items:center;gap:8px;margin:5px 0;flex-wrap:wrap}
 button,select{background:var(--btn);color:var(--txt);border:1px solid var(--line);
   border-radius:6px;padding:5px 9px;font:inherit;cursor:pointer;
   transition:background .12s,border-color .12s,box-shadow .12s,transform .05s}
 button:hover:not(:disabled),select:hover{border-color:var(--accent);box-shadow:0 1px 4px rgba(0,0,0,.28)}
 button:active:not(:disabled){transform:translateY(1px);background:var(--onbg)}
 button:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
 button:disabled{cursor:not-allowed;opacity:.45}
 button.on{background:var(--onbg);border-color:var(--accent);color:var(--accent)}
 input[type=range]{flex:1;accent-color:var(--accent)}
 /* Left to the browser default these render white-on-black in dark mode, which is the
    one bright rectangle on the whole panel. --btn/--txt already flip per theme, so in
    light mode this is very close to the default anyway. */
 /* :not(.amSearch) - an attribute selector outranks a class, so without this the two
    search boxes would lose their own larger font and padding to this rule. */
 input[type=text]:not(.amSearch),input[type=number]{background:var(--btn);color:var(--txt);
   border:1px solid var(--line);border-radius:3px;padding:1px 3px;
   font:11px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
 input[type=text]:not(.amSearch):focus,input[type=number]:focus{outline:1px solid var(--accent);
   outline-offset:0}
 /* PLACEMENT-ANGLE slider: four hard detents (0 / 90 / 180 / 270) with real tick marks.
    The TRACK, though, is a full turn: it runs 0..4 quarter turns, so the last quarter - from
    the 270 mark to the right edge - is where a fourth-quadrant angle lives (a typed -7
    normalises to 353, which sits at 3.922). There is deliberately no mark at the right edge:
    that point is 360, which IS 0, and the control wraps there rather than resting on it, so
    marking it would just be the 0 tick drawn twice. rev 62.
    The native <datalist> tickmarks Chromium draws are a couple of near-invisible grey
    pixels against this panel, so #angsl is custom-styled instead - which also PINS the
    thumb at 12px, and that pin is what makes the ticks line up. A range thumb's centre
    travels from thumbWidth/2 to width-thumbWidth/2, never the full width, so the tick
    strip is inset by exactly 6px at each end; the four marks are then placed by plain
    background-position percentages (0 / 25 / 50 / 75), which resolve against
    (strip width - 1px) and therefore land dead on the thumb centre for values 0..3 of 4.
    Scoped to .angwrap so the frame/speed sliders keep their stock accent-color look. */
 .angwrap{position:relative;flex:1;min-width:0;display:flex;align-items:center;padding-bottom:8px}
 .angwrap input[type=range]{width:100%;height:14px;margin:0;background:transparent;
   -webkit-appearance:none;appearance:none;cursor:pointer}
 .angwrap input[type=range]::-webkit-slider-runnable-track{height:4px;border-radius:2px;background:var(--line)}
 .angwrap input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;
   width:12px;height:12px;margin-top:-4px;border-radius:50%;border:none;background:var(--accent)}
 .angwrap input[type=range]::-moz-range-track{height:4px;border-radius:2px;background:var(--line)}
 .angwrap input[type=range]::-moz-range-thumb{width:12px;height:12px;border-radius:50%;
   border:none;background:var(--accent)}
 .angwrap input[type=range]:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
 .angwrap::after{content:"";position:absolute;left:6px;right:6px;bottom:2px;height:6px;
   pointer-events:none;
   background:linear-gradient(var(--dim),var(--dim)) no-repeat 0 0/1px 100%,
              linear-gradient(var(--dim),var(--dim)) no-repeat 25% 0/1px 100%,
              linear-gradient(var(--dim),var(--dim)) no-repeat 50% 0/1px 100%,
              linear-gradient(var(--dim),var(--dim)) no-repeat 75% 0/1px 100%}
 #taglist{flex:none;overflow:visible;padding:6px 8px}   /* full list; the PANEL scrolls */
 .tag{display:flex;justify-content:space-between;gap:8px;padding:4px 7px;border-radius:5px;cursor:pointer;white-space:nowrap}
 .tag:hover,.tag.sel{background:var(--btn)}
 .tag .nm{overflow:hidden;text-overflow:ellipsis;display:flex;gap:7px}
 .dot{width:8px;height:8px;border-radius:50%;flex:0 0 8px;margin-top:5px}
 .co{color:var(--dim);font-size:11px}
 .legend span{display:inline-flex;align-items:center;gap:5px;margin-right:12px}
 .legend i{width:9px;height:9px;border-radius:50%;display:inline-block}
 kbd{background:var(--btn);border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-size:11px}
 #hint{position:absolute;left:10px;bottom:8px;color:var(--dim);font-size:11px;
   background:rgba(var(--labelbg),.55);padding:2px 8px;border-radius:6px;pointer-events:none}
 #sideTab{position:absolute;right:0;top:50%;transform:translateY(-50%);z-index:15;
   background:var(--panel);color:var(--dim);border:1px solid var(--line);border-right:none;
   border-radius:8px 0 0 8px;padding:14px 5px;cursor:pointer;font-size:12px;line-height:1;
   user-select:none;transition:color .12s,border-color .12s}
 #sideTab:hover{color:var(--accent);border-color:var(--accent)}
 #helpOv{position:absolute;inset:0;background:rgba(0,0,0,.45);display:flex;
   align-items:center;justify-content:center;z-index:20}
 #helpCard{background:var(--panel);border:1px solid var(--line);border-radius:10px;
   padding:16px 20px 14px;max-height:86%;max-width:92%;overflow:auto;box-shadow:0 12px 40px rgba(0,0,0,.5)}
 #helpCard h3{margin:0 0 10px;color:var(--accent);font-size:13px}
 #helpCard table{border-collapse:collapse;font-size:12px}
 #helpCard td{padding:2px 12px 2px 0;vertical-align:top}
 #helpCard td:first-child{color:var(--accent);white-space:nowrap}
 #helpCard .grp td{color:var(--dim);text-transform:uppercase;font-size:10px;letter-spacing:.1em;padding-top:9px}
 #helpClose{margin-top:12px}
 ::-webkit-scrollbar{width:10px;height:10px}
 ::-webkit-scrollbar-thumb{background:var(--line);border-radius:5px}
 ::-webkit-scrollbar-thumb:hover{background:var(--btnhover)}
 ::-webkit-scrollbar-track{background:transparent}
</style>
<script>
/* Host boot flags, read from the URL hash the launcher loads us with
   (e.g. file:///.../jeep_tik_view.html#embed&theme=dark). Applied here, during
   <head> parse, BEFORE the body is built and painted, so the embedded pane shows
   the final in-launcher layout + theme immediately instead of rendering the full
   standalone "webpage" layout first and then swapping via delayed JS.
   Opened in a plain browser there is no hash -> full standalone layout, as before. */
(function(){try{
  var raw=(location.hash||"").replace(/^#/,""),p={};
  raw.split("&").forEach(function(kv){if(!kv)return;var i=kv.indexOf("=");
    if(i<0)p[decodeURIComponent(kv)]=true;
    else p[decodeURIComponent(kv.slice(0,i))]=decodeURIComponent(kv.slice(i+1));});
  window.__HOSTEMBED__=!!p.embed;
  var t=(""+(p.theme||"")).toLowerCase();
  window.__HOSTTHEME__=(t==="light"||t==="dark")?t:"";
  /* #ang=<pitch>,<yaw>,<roll>: the entity placement angles the launcher remembered in
     mohaa_viewer_config.json. Handed over on the boot hash so the first pose is already
     built rotated, rather than snapping to it a frame after load. */
  var an=(""+(p.ang||"")).split(",").map(Number);
  window.__HOSTANG__=(an.length===3&&an.every(function(v){return isFinite(v);}))?an:null;
  var el=document.documentElement;
  if(window.__HOSTEMBED__)el.classList.add("embed");
  if(window.__HOSTTHEME__)el.classList.toggle("light",window.__HOSTTHEME__==="light");
}catch(_e){}})();
</script></head>
<body><div id="animMenu"></div><div id="wrap">
 <div id="stage"><canvas id="gl"></canvas><canvas id="c"></canvas>
  <div id="hint"><kbd>H</kbd> hotkeys</div>
  <div id="sideTab" title="Collapse the control panel (\)">&#10095;</div>
  <div id="helpOv" style="display:none">
   <div id="helpCard">
    <h3>Viewer Keyboard shortcuts</h3>
    <table>
     <tr class="grp"><td colspan="2">Camera (free-look)</td></tr>
     <tr><td>drag / wheel</td><td>look around / zoom</td></tr>
     <tr><td>W / S</td><td>move forward / back</td></tr>
     <tr><td>A / D</td><td>strafe left / right</td></tr>
     <tr><td>Q / E</td><td>tilt (roll) left / right</td></tr>
     <tr><td>Space / C</td><td>move up / down</td></tr>
     <tr><td>Up / Down</td><td>move forward / back</td></tr>
     <tr><td>Left / Right</td><td>turn (yaw) left / right</td></tr>
     <tr><td>R</td><td>reset camera</td></tr>
     <tr><td>V</td><td>toggle Free-look / Tag-lock camera</td></tr>
     <tr class="grp"><td colspan="2">Playback</td></tr>
     <tr><td>P</td><td>play / pause the model &amp; animation</td></tr>
     <tr><td>F</td><td>freeze / resume everything (same as Play / Pause)</td></tr>
     <tr><td>[ / ]</td><td>step one frame back / forward</td></tr>
     <tr><td>Backspace</td><td>reset model &amp; effects to time 0</td></tr>
     <tr class="grp"><td colspan="2">Display toggles</td></tr>
     <tr><td>1&ndash;7</td><td>Texture &middot; Mesh &middot; Wire &middot; Setsizes &middot; Nodes &middot; Labels &middot; Face Anims</td></tr>
     <tr><td>L</td><td>toggle Light / Dark theme</td></tr>
     <tr><td>\</td><td>collapse / expand the control panel</td></tr>
     <tr class="grp"><td colspan="2">Pop-up lists (animations &middot; surfaces &middot; attach)</td></tr>
     <tr><td>type</td><td>filter the list</td></tr>
     <tr><td>Up / Down</td><td>move the highlight</td></tr>
     <tr><td>Enter</td><td>open the highlighted row (or take the top match)</td></tr>
     <tr><td>Right</td><td>open the highlighted category</td></tr>
     <tr><td>Left / Backspace</td><td>go back one level</td></tr>
     <tr><td>Home / End</td><td>jump to the first / last row</td></tr>
     <tr><td>Esc</td><td>close the list</td></tr>
     <tr class="grp"><td colspan="2">Window</td></tr>
     <tr><td>H or ?</td><td>show / hide this panel</td></tr>
     <tr><td>Esc</td><td>close the viewer window</td></tr>
    </table>
    <button id="helpClose" title="Close this panel (Esc)">Close</button>
   </div>
  </div>
 </div>
 <div id="side">
   <div class="sect"><h1 id="ttl">model</h1><div class="sub" id="stats"></div><div class="sub" id="setsizeLine"></div></div>
   <div class="sect" id="modelSect">
     <h2>Model</h2>
     <div class="row">
       <button id="bTheme" style="flex:1" title="Toggle Light / Dark theme (L). Your choice is remembered.">&#9728; Light mode</button>
       <button id="bHelp" title="Show the viewer's keyboard shortcuts (H). The launcher's own '? Shortcuts' button lists these AND the launcher/pak-tree keys.">? Shortcuts</button>
     </div>
   </div>
   <div class="sect">
     <h2>Animation</h2>
     <div class="row"><button id="animBtn" style="flex:1;min-width:0;text-align:left" title="Browse every animation this model can reach. Categories follow the model's own $include / includes{} structure. Up/Down to move, Enter to open, Left or Backspace to go back.">&mdash; bind pose (rest) &mdash;</button><span class="co" id="animKind" title="Anim names come from the opened .tik's animations{} list (resolved through its $include chain), or from sibling .skc files for a bare model"></span></div>
     <div class="row co" id="animPath" style="display:none;word-break:break-all"></div>
     <div class="row co">&nbsp;</div>
     <div class="row">
       <button id="play" style="flex:1" title="Play / pause the whole model - the selected animation AND every emitter/effect (P, or F)">&#9654; Play</button>
       <button id="bLoop" style="overflow:auto" title="Loop the animation at its last frame. Off = play once and stop (one-shot fx): press Play again to re-fire. Your choice is remembered.">&#8734; Loop</button>
       <button id="reset" style="overflow:auto" title="Restart the model/effect from time 0 (Backspace)">&#8635; Reset</button>
     </div>
     <div class="row"><input type="range" id="scrub" min="0" max="0" value="0" style="flex:1;min-width:0" title="Scrub through frames ( [ and ] step one frame )"><span class="co" id="frlab">frame 0</span></div>
     <div class="row co">speed <input type="range" id="speed" min="2" max="60" value="20" style="max-width:120px" title="Playback speed in frames per second"> <span id="fps">20</span> fps</div>
     <div class="row co" id="surfRow" style="display:none">
       <button id="surfBtn" style="max-width:150px" title="Hide or show surfaces - the same thing `surface &lt;name&gt; +nodraw` does in script. Surfaces the .tik itself turns off at spawn start out struck through. The list STAYS OPEN while you toggle; click the button again, press Esc, or click off the list to close it."><span class="albl">&mdash; surfaces &mdash;</span><span class="acar">&#9668;</span></button>
       <span id="surfCount" class="dim">0 / 0 surfaces</span></div>
     <div class="row co" id="attRow" style="display:none">
       <button id="attBoneBtn" style="max-width:150px" title="Hang a model off a bone or tag. Type to search the skeleton - a human rig has 85 nodes - then click a row or press Enter to take the top match."><span class="albl">&mdash; attach to bone &mdash;</span><span class="acar">&#9668;</span></button>
       <span id="attCount" class="dim">0 / 8 attached</span></div>
     <div id="attList"></div>
   </div>
   <div class="sect">
     <h2>Camera</h2>
     <div class="row">
       <button id="bFree" class="on" style="flex:1" title="Fly camera: WASD moves, Q/E tilts, Space/C rises/lowers (V toggles modes)">Free-look</button>
       <button id="bLock" style="flex:1" title="Orbit camera: drag orbits around the model or a clicked tag (V toggles modes)">Tag-lock</button>
     </div>
     <div id="camHelpLock" style="display:none">
       <div class="row co"><b>Tag-lock:</b> orbit a clicked tag</div>
       <div class="row co">&nbsp;</div>
       <div class="row co">mouse drag = orbit</div>
       <div class="row co">mouse wheel = zoom in / out</div>
       <div class="row co"><kbd>R</kbd> reset camera</div>
     </div>
     <div id="camHelpFree">
       <div class="row co"><b>Free-look</b> (fly camera):</div>
       <div class="row co">&nbsp;</div>
       <div class="row co">mouse drag = look around</div>
       <div class="row co">mouse wheel = zoom in / out</div>
       <div class="row co"><kbd>R</kbd> reset camera</div>
       <div class="row co">&nbsp;</div>
       <div class="row co"><kbd>W</kbd>/<kbd>S</kbd> move forward / back</div>
       <div class="row co"><kbd>A</kbd>/<kbd>D</kbd> strafe side to side</div>
       <div class="row co"><kbd>Q</kbd>/<kbd>E</kbd> tilt left / right</div>
       <div class="row co"><kbd>C</kbd>/<kbd>Space</kbd> move down / up</div>
     </div>
   </div>
   <div class="sect">
     <h2>Display</h2>
     <div class="row">
       <button id="bTex" class="on" title="Show / hide resolved skin textures (1)">Texture</button><button id="bMesh" class="on" title="Show / hide the shaded mesh surfaces (2)">Mesh</button><button id="bWire" title="Show / hide the triangle wireframe (3)">Wire</button><button id="bSize" title="Wireframe box of the model's setsize / .map bounding box (4)">Setsizes</button>
       <button id="bNodes" class="on" title="Show / hide tag / bone node circles (5)">Nodes</button><button id="bLbl" class="on" title="Show / hide tag / bone name labels (6)">Labels</button><button id="bFace" class="on" title="Play the facial blend-shape layer that rides along with this body animation (7). Only shown while a body animation is carrying a face layer - a face-only track IS the animation, so there is nothing to toggle." style="display:none">Face Anims</button><button id="bGlow" title="Illustrative: adds a synthetic placement tilt so corona light-glows swing off-center as the camera moves, like in-game (the real placement rotation lives in the .bsp/.map, not the .tik). The camera-facing billboard and toward-eye grow/fill are always on; this only adds the off-center orbit.">Corona orbit</button><button id="bTreeSpr" title="Show ONLY the flat billboard stand-in the engine swaps in for a tree at long range (deformVertexes autoSprite2 + alphaGen oneMinusDistFade), with every canopy and trunk card hidden and the stand-in pinned opaque regardless of zoom.">Tree Sprite</button>
     </div>
     <div class="row co">&nbsp;</div>
     <div class="row co" style="align-items:center">
       <button id="angAxis" style="min-width:52px;padding:5px 6px" title="Which of the entity's three placement angles the slider is editing. Click to cycle Pitch -&gt; Yaw -&gt; Roll; each axis keeps its own value.">Pitch</button>
       <span class="angwrap"><input type="range" id="angsl" min="0" max="4" step="any" value="0"
         title="Entity placement angle for the axis named on the left, in quarter turns: the four ticks are 0 / 90 / 180 / 270 degrees. The track is a full turn and it WRAPS - arrow-right off the 270 end comes back at 0, arrow-left off the 0 end goes to 270 - so you can keep stepping round in either direction. A .tik carries no orientation - in-game it comes from the entity's `angles` key in the .bsp/.map, which the engine feeds to AnglesToAxis (q_math.c:774-800) to build the refEntity axis. Set it here to view a wall-, ceiling- or vehicle-mounted emitter the way it is actually placed. Dragging (and the arrow keys) always land on one of the four detents; for anything in between, type it with the pencil on the right - the thumb then parks between two ticks. Remembered."></span>
       <span id="angslv" style="min-width:100px;text-align:right;color:var(--dim);white-space:nowrap"
         title="The full placement orientation: ( pitch yaw roll ) in degrees. All three are shown at once, so the two axes the slider is not currently driving stay visible.">( 0 0 0 )</span><button id="angEdit" style="padding:0 6px;line-height:1.5;font-size:12px" title="Edit the placement angles by hand - any value, not just the four quarter turns (45, 22.5, -7 ...). The slider thumb moves to match, parking between tick marks for an off-detent angle. Values are kept when you close the editor.">&#9998;</button>
     </div>
     <div class="row co" style="align-items:center">backdrop
       <input type="color" id="bgcol" value="#0e1116" style="width:44px;height:22px;padding:1px;border:1px solid var(--line);border-radius:6px;background:var(--btn);cursor:pointer" title="Backdrop colour behind the model. Overrides the theme's default; remembered.">
       <button id="bgReset" title="Return the backdrop to the current theme's default colour">Default</button>
     </div>
     <div class="row legend">
       <span><i style="background:var(--tag)"></i>Tag/Bone</span>
       <span><i style="background:var(--origin)"></i>Origin</span>
       <span><i style="background:var(--sel)"></i>Selected</span>
     </div>
     <div class="row co">shift-click any circle = hide/show all</div>   </div>
   <div class="sect" style="padding:8px 12px;display:flex;gap:8px">
     <button id="bFilterTag" class="on" style="flex:1" title="List only tags and origin markers below">Tags</button>
     <button id="bFilterBone" style="flex:1" title="List only skeleton bones below">Bones</button>
   </div>
   <div id="taglist"></div>
 </div>
</div>
<script>
// Side-panel collapse tab: the arrow on the stage's right edge retracts / restores the
// whole control panel. When #side is hidden the stage stretches to the window edge, so
// the tab stays visible for pulling the panel back out. Wired before any model parsing
// so it works even when an asset fails to load. Not persisted - opens fresh every load.
{const sideTab=document.getElementById('sideTab'),sideEl=document.getElementById('side');
 sideTab.onclick=()=>{const hide=sideEl.style.display!=='none';
   sideEl.style.display=hide?'none':'flex';
   sideTab.innerHTML=hide?'&#10094;':'&#10095;';
   sideTab.title=(hide?'Expand':'Collapse')+' the control panel (\\)';
   window.dispatchEvent(new Event('resize'));};}
const DATA=__DATA__;
// SPR_UNIT: a MOHAA sprite's native world size at scale 1.0 (about 100u)
// this fixed base - it is NOT tied to texture resolution (the .spr files carry origin_x/y
// and aren't in the extracted data). Sizing sprites by texture pixels made tiny-scale
// effects (mortar/mine dirt at scale .0625) ~16x too small.
// SPR_K: flat-sprite world size per texture-pixel per scale-unit. A .spr's on-screen size
// tracks its texture resolution (the engine bakes native size into the .spr, which we don't
// have, but texture px is a faithful proxy: 32px smoke puff small, 128px splash large, 256px
// dirt largest). World size = texturePx * SPR_K * scale * (1 + scalerate*age). This replaces
// the flat SPR_UNIT base, which sized every sprite the same regardless of texture and so
// couldn't fit both tiny vsssource-smoke puffs and big water splashes at once. Tune here.
const SPR_K=1.1;
// VSS_UNIT: the world size (at puff radius 5) of a volumetric smoke puff, i.e. the texel
// base the engine's radius/5 refEntity scale multiplies. Independent of SPR_UNIT (flat
// sprites) so the two can be tuned separately. VSS puff world size = VSS_UNIT * (radius/5)
// * spritescale. Lower = smaller/tighter smoke columns; raise to fatten them. 32 matched
// the vsssource texture-pixel assumption; tune here to trim overall smoke size.
const VSS_UNIT=32;
function qmat(q){const x=-q[0],y=-q[1],z=-q[2],w=q[3];return[
 1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y),
 2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x),
 2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)];}
function mmul(A,B){const R=new Array(9);for(let i=0;i<3;i++)for(let j=0;j<3;j++){let s=0;for(let k=0;k<3;k++)s+=A[i*3+k]*B[k*3+j];R[i*3+j]=s;}return R;}
function mvec(A,v){return[A[0]*v[0]+A[1]*v[1]+A[2]*v[2],A[3]*v[0]+A[4]*v[1]+A[5]*v[2],A[6]*v[0]+A[7]*v[1]+A[8]*v[2]];}
// ===== ENTITY PLACEMENT ANGLES (pitch / yaw / roll) ==========================
// A .tik holds no orientation. In-game an object's placement comes from the entity's
// `angles` key in the .bsp/.map, which the engine converts to the refEntity axis with
// AnglesToAxis (q_math.c:774-800):
//     axis[0] = forward = ( cp*cy,            cp*sy,            -sp   )
//     axis[1] = left    = ( sr*sp*cy+cr*-sy,  sr*sp*sy+cr*cy,    sr*cp)
//     axis[2] = up      = ( cr*sp*cy+-sr*-sy, cr*sp*sy+-sr*cy,   cr*cp)
// and a model-space vector v reaches world space as v[0]*axis[0]+v[1]*axis[1]+v[2]*axis[2]
// (R_RotateForEntity places axis[i] in COLUMN i of the modelview), i.e. world = EROT*v with
// EROT holding the three axes as its columns. Everything here stays in MOHAA space (Z-up);
// the viewer's Y-up swap happens later in skin()/bonePts(), so this composes ahead of it.
let EANG=[0,0,0];      // degrees, [pitch, yaw, roll] - driven by the Display panel dial
let EROT=null;         // 3x3 row-major (world = EROT * local); null while all angles are 0
function anglesToRot(pitch,yaw,roll){
 const D=Math.PI/180;
 const sy=Math.sin(yaw*D),cy=Math.cos(yaw*D),
       sp=Math.sin(pitch*D),cp=Math.cos(pitch*D),
       sr=Math.sin(roll*D),cr=Math.cos(roll*D);
 const f=[cp*cy, cp*sy, -sp];                          // axis[0] forward
 const l=[sr*sp*cy+cr*-sy, sr*sp*sy+cr*cy, sr*cp];     // axis[1] left
 const u=[cr*sp*cy+-sr*-sy, cr*sp*sy+-sr*cy, cr*cp];   // axis[2] up
 return[f[0],l[0],u[0],
        f[1],l[1],u[1],
        f[2],l[2],u[2]];}                              // axes as COLUMNS
function erotV(x,y,z){if(!EROT)return[x,y,z];
 return[EROT[0]*x+EROT[1]*y+EROT[2]*z,
        EROT[3]*x+EROT[4]*y+EROT[5]*z,
        EROT[6]*x+EROT[7]*y+EROT[8]*z];}
const NB=DATA.bones.length;
function worldFromPose(over){
 const R=new Array(NB),T=new Array(NB),done=new Uint8Array(NB);
 function res(i){if(done[i])return;done[i]=1;const b=DATA.bones[i];let p,q;
   if(over&&over[i]){const a=over[i];
     // 4 numbers = ROTATION-ONLY entry: the animation drives this bone's rotation but supplies
     // no "<bone> pos" channel, so the translation comes from the base pose - the engine's
     // movement slot. 7 numbers = a full local transform (bones the animation does position,
     // plus the IK/helper bakes). Cached sidecars built before this are all 7-element.
     if(a.length===4){p=DATA.base[i].p;q=[a[0],a[1],a[2],a[3]];}
     else{p=[a[0],a[1],a[2]];q=[a[3],a[4],a[5],a[6]];}}
   else{p=DATA.base[i].p;q=DATA.base[i].q;}
   const lR=qmat(q);
   // ENTITY ANGLES are composed at the ROOT of the skeleton - exactly where the engine puts
   // them. The bone solve is model-space; the placement rotation only enters when the whole
   // refEntity is turned. Doing it here instead of inside project() means every downstream
   // consumer inherits it for free: skinned vertices, bone/tag world positions AND tag AXES
   // (so tagspawn / tagspawnlinked emitters fire in the rotated frame), while the ground grid
   // and the camera-facing sprite billboards stay put in world space, as in-game.
   if(b.parent<0){R[i]=EROT?mmul(EROT,lR):lR;T[i]=EROT?erotV(p[0],p[1],p[2]):[p[0],p[1],p[2]];}
   else{res(b.parent);R[i]=mmul(R[b.parent],lR);const pt=mvec(R[b.parent],p);
     T[i]=[pt[0]+T[b.parent][0],pt[1]+T[b.parent][1],pt[2]+T[b.parent][2]];}}
 for(let i=0;i<NB;i++)res(i);return{R:R,T:T};}
// ===== facial blend shapes (morph targets) ===============================
// DATA.morphs is a SPARSE map "vertexIndex" -> [morphIdx,dx,dy,dz, morphIdx,dx,dy,dz, ...]
// read straight out of the .skd (skeletorMorph_t, tiki_shared.h:361-364). Only the head
// mesh carries them - about 400 of ~2900 vertices on a body+head model - so a dense array
// would be almost entirely empty.
//
// The deltas sit in the SAME bone space as each weight's offset (on every retail head all
// but 2 of the morphed vertices are single-weighted to Bip01 Head), so applying them is
// just: offset += sum(delta_i * weight[morphIndex_i]), before the bone matrix. The engine
// keeps the weights as integers on a 0..100 scale (skeletor.cpp:1096-1146) and the .skd
// deltas are stored pre-divided by 100, so the weight is used raw.
const MORPHS=DATA.morphs||{}, MORPH_N=(DATA.morphNames||[]).length;
const HAS_MORPH=MORPH_N>0&&Object.keys(MORPHS).length>0;
let curMorphW=null;            // null = neutral face (all weights zero)
function morphOf(i){return HAS_MORPH?MORPHS[i]:undefined;}

function skin(w){const V=DATA.verts,out=new Float32Array(V.length*3);
 const MW=curMorphW;
 for(let i=0;i<V.length;i++){let X=0,Y=0,Z=0;const ws=V[i];
   let mx=0,my=0,mz=0;
   if(MW){const md=morphOf(i);
     if(md){for(let m=0;m<md.length;m+=4){const wv2=MW[md[m]];
       if(wv2){mx+=md[m+1]*wv2;my+=md[m+2]*wv2;mz+=md[m+3]*wv2;}}}}
   for(let k=0;k<ws.length;k++){const wt=ws[k],bi=wt[0],wv=wt[1];
     const ox=wt[2]+mx,oy=wt[3]+my,oz=wt[4]+mz;
     const Rb=w.R[bi],Tb=w.T[bi];
     X+=wv*(Rb[0]*ox+Rb[1]*oy+Rb[2]*oz+Tb[0]);
     Y+=wv*(Rb[3]*ox+Rb[4]*oy+Rb[5]*oz+Tb[1]);
     Z+=wv*(Rb[6]*ox+Rb[7]*oy+Rb[8]*oz+Tb[2]);}
   out[i*3]=X;out[i*3+1]=Z;out[i*3+2]=Y;}
 return out;}
function bonePts(w){const P=new Float32Array(NB*3);
 for(let i=0;i<NB;i++){const t=w.T[i];P[i*3]=t[0];P[i*3+1]=t[2];P[i*3+2]=t[1];}return P;}
const cv=document.getElementById('c'),ctx=cv.getContext('2d');
const glcv=document.getElementById('gl');
let GLR=null;   // WebGL renderer (created near the end of this script, after the surface
                // tables exist); stays null when no GL context -> the 2D path takes over
let DPR=Math.min(2,window.devicePixelRatio||1),W=0,H=0;
function resize(){const r=cv.getBoundingClientRect();W=r.width;H=r.height;
 cv.width=W*DPR;cv.height=H*DPR;ctx.setTransform(DPR,0,0,DPR,0,0);
 if(GLR)GLR.resize();draw();}
window.addEventListener('resize',resize);
let modelBase=skin(worldFromPose(null));
// ===== deformVertexes flap (tr_shade_calc.c RB_CalcFlapVertexes :306-388) =====
// MOHAA's foliage wind. Each flap stage pushes every vertex ALONG ITS NORMAL by
//     scale       = WAVEVALUE(func, base, amplitude, phase, frequency)
//     vertexScale = (max - min) * st[coordsToUse] + min
//     xyz        += scale * vertexScale * normal
// Two engine details that are easy to get wrong, both plain in the source:
//  1. `off = (x+y+z) * deformationSpread` is computed at :371 and then NEVER USED - the
//     WAVEVALUE call on the next line does not reference it. So unlike `deformVertexes wave`,
//     flap is NOT a travelling wave: the surface swings in unison and the `div` operand (24
//     here) has no effect. Reproducing it as a travelling wave would be wrong.
//  2. The per-vertex weight comes from the TEXCOORD, not from height. trees.shader passes
//     min=1 max=0, so vertexScale = 1 - t: the top edge of a leaf card (t=0) swings fully
//     while the branch-attached bottom edge (t=1) stays pinned.
// bush_full stacks two stages at frequency 0.2 and 0.3 a quarter-period apart. Detuned sines
// BEAT at |0.3-0.2| = 0.1 Hz - a ~10s gust envelope, which is the wind "varying" rather than
// any wind system. Measured off the in-game capture: 0.214 / 0.321 Hz sway, 0.107 Hz envelope.
const FLAPS=DATA.surfRanges.map(s=>(s.flap&&s.flap.length)?s.flap:null);
const hasFlap=FLAPS.some(f=>f);
let VN=null;                                    // per-vertex normals, area-weighted
function buildNormals(){
  if(!hasFlap){VN=null;return;}
  const T=DATA.tris,n=modelBase.length;
  VN=new Float32Array(n);
  // DATA.tris is an array of [i0,i1,i2] TRIPLES, not a flat index list - draw2DScene reads it
  // as `const tr=Tt[ti]; tr[0]`. Walking it flat made every index NaN, so no face normal was
  // ever accumulated and every vertex fell through to the (0,1,0) fallback: the whole bush
  // flapped straight up and down at the correct amplitude and beat, but on the wrong axis.
  for(let i=0;i<T.length;i++){
    const tr=T[i], a3=tr[0]*3, b3=tr[1]*3, c3=tr[2]*3;
    const ux=modelBase[b3]-modelBase[a3],uy=modelBase[b3+1]-modelBase[a3+1],uz=modelBase[b3+2]-modelBase[a3+2];
    const vx=modelBase[c3]-modelBase[a3],vy=modelBase[c3+1]-modelBase[a3+1],vz=modelBase[c3+2]-modelBase[a3+2];
    const nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx;   // unnormalised = area weighted
    VN[a3]+=nx;VN[a3+1]+=ny;VN[a3+2]+=nz;
    VN[b3]+=nx;VN[b3+1]+=ny;VN[b3+2]+=nz;
    VN[c3]+=nx;VN[c3+1]+=ny;VN[c3+2]+=nz;}
  for(let i=0;i<n;i+=3){
    const l=Math.hypot(VN[i],VN[i+1],VN[i+2]);
    if(l>1e-9){VN[i]/=l;VN[i+1]/=l;VN[i+2]/=l;}else{VN[i]=0;VN[i+1]=1;VN[i+2]=0;}}
}
// WAVEVALUE = base + table[(phase + shaderTime*freq)*SIZE & MASK]*amplitude (tr_shade_calc.c).
function waveVal(f,base,amp,phase,freq,t){
  let x=phase+t*freq; x-=Math.floor(x);                    // & FUNCTABLE_MASK
  let v;
  switch(f){
    case 'square':   v=(x<0.5)?1:-1; break;
    case 'triangle': v=(x<0.5)?(4*x-1):(3-4*x); break;
    case 'sawtooth': v=x; break;
    case 'inversesawtooth': v=1-x; break;
    default:         v=Math.sin(x*6.2831853);              // sin (and noise, kept bounded)
  }
  return base+v*amp;
}
let model=modelBase;
function applyFlap(){
  if(!hasFlap||!VN)return;
  if(model===modelBase)model=new Float32Array(modelBase.length);
  model.set(modelBase);
  const UVa=DATA.uvs;
  for(let si=0;si<FLAPS.length;si++){
    const fl=FLAPS[si]; if(!fl)continue;
    const sr=DATA.surfRanges[si];
    for(const d of fl){
      const sc=waveVal(d.func,d.base,d.amp,d.phase,d.freq,effT);
      if(!sc)continue;
      const ax=(d.axis==='s')?0:1, mn=d.min, span=d.max-d.min;
      for(let v=sr.vstart;v<sr.vend;v++){
        const i3=v*3;
        const st=UVa?UVa[v*2+ax]:0;
        const w=sc*(span*st+mn);
        model[i3]+=w*VN[i3];model[i3+1]+=w*VN[i3+1];model[i3+2]+=w*VN[i3+2];}
    }
  }
}
buildNormals();   // applyFlap() is driven by effLoop: effT is declared below (TDZ)
let cx=0,cy=0,cz=0,rad=1;
let cx0=0,cy0=0,cz0=0,selectedIdx=-1;const hidden=new Set();
(function(){let mn=[1e9,1e9,1e9],mx=[-1e9,-1e9,-1e9];
 for(let i=0;i<model.length;i+=3)for(let k=0;k<3;k++){mn[k]=Math.min(mn[k],model[i+k]);mx[k]=Math.max(mx[k],model[i+k]);}
 cx=(mn[0]+mx[0])/2;cy=(mn[1]+mx[1])/2;cz=(mn[2]+mx[2])/2;
 rad=Math.max(mx[0]-mn[0],mx[1]-mn[1],mx[2]-mn[2])*0.6+1;})();
// Emitter effects animate far beyond the tiny dummy the camera would otherwise frame;
// widen to the particle activity volume so sprites are a sane size and sphere / inward
// spawns (e.g. electric's radius-23 shell) don't smear across the whole screen.
(function(){const _EMf=DATA.emitters||[];if(!_EMf.length)return;
 function camp(c){if(!c||!c.length)return 0;return c[0]==='range'?Math.abs(c[2])+Math.abs(c[1]):Math.abs(c[1]||0);}
 let er=0;
 for(const e of _EMf){const off=e.offset||e.offsetalongaxis||[];
   const offm=Math.max(camp(off[0]),camp(off[1]),camp(off[2]));
   const vel=e.velocity||0,life=Math.max(e.life||1,0.1),R=e.radius||0;
   // A large sprite/mesh occupies frame space even from a point emitter. If the framing
   // ignores it (here the waterfall's velocity spread is only ~6u but each water_g sprite is
   // ~72u), the camera sits too close, every sprite hits the per-sprite px cap, and the effect
   // stops resizing with zoom. Fold in the particle's world size (engine sprite width =
   // imagePx * scale * shader spritescale, tr_sprite.c:101,153-155) so the default view fits
   // it and zoom then scales it normally.
   // Representative on-screen scale for framing. scalerate grows the sprite unbounded
   // (see the draw path), so use the base random-scale midpoint plus a bounded slice of
   // growth as a stand-in for "typical size seen" - NOT clamped to scalemax (that is only
   // the spawn range, not a runtime cap; clamping here re-shrinks the fast-growing
   // mortar/mine sprites the framing is meant to fit).
   // VSS (volumetric) puffs size off their world RADIUS (1..32u, grown per-type), NOT the
   // flat-sprite SPR_UNIT base - their scalemin/scalemax ARE that radius, so feeding them
   // through the SPR_UNIT path made framing swing wildly with SPR_UNIT (thin_black_short/
   // tanksmoke shrank, aircraft_explosion/fx_explosion_mine ballooned). A VSS puff spans
   // ~2*radius; use the max radius (clamped to the engine's 32u cap) as its framing size.
   const _isVol=(e.volumetric||(e.flags&&e.flags.indexOf('volumetric')>=0));
   let sw;
   if(_isVol){
     // frame VSS by the actual drawn puff size: VSS_UNIT * (radius/5), matching the draw
     // path so zoom-to-fit tracks whatever VSS_UNIT is tuned to.
     const _r=Math.min(32,Math.max(e.scalemax||e.scale||10,1));
     sw=VSS_UNIT*(_r/5);
   } else {
     const _base=(e.scalemin!=null||e.scalemax!=null)
                 ? ((e.scalemin||0)+(e.scalemax||e.scalemin||0))*0.5
                 : (e.scale!=null?e.scale:1);
     // scalerate-grown peak size is TRANSIENT (the sprite is large only in its final frames,
     // usually while fading out) - framing to that peak let one steep-scalerate sprite
     // (mortar_dirthit: scale .25, scalerate 8 -> ~900u framing size) dominate the effect
     // radius and shove the camera so far back the WHOLE emitter rendered tiny. Cap the
     // growth multiplier at 3x so framing reflects a representative mid-life size, not the
     // fleeting maximum. The draw path is unchanged - sprites still grow to full size; only
     // the auto-zoom distance is kept sane.
     // Also clamp the framing base to scalemax when present: the burst is authored around
     // scalemax, and letting a big-scalerate sprite (air_explosion: scale 3, scalerate 9,
     // texw 256) drive the framing shoved the camera so far back the shrapnel rendered
     // ~half size. Framing only - the draw path still grows sprites to full size.
     let _fbase=_base;
     if(e.scalemax!=null) _fbase=Math.min(_fbase, e.scalemax);
     const _grow=Math.min(3, 1+(e.scalerate||0)*Math.min(life,1.5));
     const _es=Math.max(0.1,_fbase*_grow);
     // match the texture-proportional draw: framing size = texturePx * SPR_K * scale.
     const _tpx=Math.max(e.texw||32,e.texh||32);
     sw=(e.basesize>0?e.basesize:_tpx*SPR_K*(e.spritescale||1))*_es;
   }
   // Effect radius = the larger of the particle SPREAD (offset + velocity travel) and a
   // bounded allowance for sprite size. A big but transient flash sprite (air_explosion:
   // ~800u framing size) must NOT set the camera distance for the whole effect - it parks
   // at the origin for a few frames while the persistent smoke/shrapnel define the real
   // extent. The sprite term is capped at 160u so no single oversized/fast-growing sprite
   // zooms the camera out past what the effect actually occupies (the user can still zoom
   // in/out freely); the true particle spread is always honoured in full.
   const _spread=0.6*offm + R + vel*Math.min(life,0.6)*0.2;
   er=Math.max(er, _spread, Math.min(0.7*sw, 160));}
 if(er>rad){const f=Math.min(1,(er-rad)/er);          // ease the centre toward the emitter origin (0,0,0)
   cx+=(0-cx)*f;cy+=(0-cy)*f;cz+=(0-cz)*f;rad=er;}})();
cx0=cx;cy0=cy;cz0=cz;
// GROUND PLANE. The grid (and the `collision` particle floor) used to sit at the heuristic
// cy0-rad*0.55, which for a character lands ~17% of its height ABOVE its own lowest vertex -
// so the boots render half-buried and any pose whose feet reach the bind-pose minimum looks
// sunk through the floor. Take the LOWER of that heuristic and the bind-pose mesh floor: for a
// biped the mesh floor wins and the grid lands exactly under the feet; for an emitter model
// (where rad was widened to the particle activity volume and the mesh is a tiny dummy at the
// origin) the heuristic still wins, so the welding-sparks fall distance is untouched. The
// floor can only ever move DOWN relative to today, so nothing that renders correctly now can
// start clipping.
let groundY=cy0-rad*0.55;
(function(){let m=1e9;for(let i=1;i<model.length;i+=3)if(model[i]<m)m=model[i];
  if(m<1e9&&m<groundY)groundY=m;})();
let yaw=0.7,pitch=-0.4,roll=0,dist=rad*2.6;
let eye=null;   // free-look camera world position; null until free-look is first entered
let camMode='lock';   // 'lock' = orbit a tag, 'free' = MOHRadiant-style fly camera
// camera basis from yaw/pitch: forward (into view), right (strafe). World +Y is up.
function camBasis(){const ca=Math.cos(yaw),sa=Math.sin(yaw),ce=Math.cos(pitch),se=Math.sin(pitch);
 return{f:[-sa*ce,se,ca*ce], r:[ca,0,sa]};}
// in free-look the eye is fixed/flown and the orbit center is derived in front of it,
// so the existing orbit projection renders a true first-person fly camera.
function syncCenterFromEye(){if(!eye)return;const b=camBasis();
 cx=eye[0]+dist*b.f[0];cy=eye[1]+dist*b.f[1];cz=eye[2]+dist*b.f[2];}
function enterFreeLook(){const b=camBasis();eye=[cx-dist*b.f[0],cy-dist*b.f[1],cz-dist*b.f[2]];}
const hasTex=DATA.surfRanges.some(s=>s.tex||s.pulse);
// Mesh on by default so any surface without a resolved texture still shows as flat
// shaded polygons (rather than a hole) underneath the textured surfaces.
// `sprite` has NO button any more. It never gated emitter particles despite the old "Show /
// hide emitter sprites and particles" tooltip - its only readers are the three autosprite
// branches (deformVertexes autoSprite surfaces billboarded onto the 2D overlay / skipped in
// the GL pass), so on the overwhelming majority of models the button did nothing visible.
// Pinned true so those surfaces always billboard, which is the engine behaviour anyway.
const view={tex:hasTex,mesh:true,wire:false,nodes:true,labels:true,wasd:false,sprite:true,setsize:false,tilt:false,treesprite:false,face:true};
// per-surface texture images (decoded from embedded data URLs). Effect surfaces
// (deformVertexes autosprite / blendfunc add / animMap) carry extra fields the
// in-game renderer uses: a camera-facing billboard, additive glow and frame cycling.
// A `pulse` overlay (items.shader bangalore_pulsating*) is a second additive stage whose
// brightness oscillates via rgbGen wave; pulseOnly surfaces (..._ghosting) have no solid base.
function mkSurfTex(s){
  if(!s.tex&&!s.pulse)return null;
  const rec={additive:!!s.additive,autosprite:!!s.autosprite,autosprite2:!!s.autosprite2,lightglow:!!s.lightglow,twosided:!!s.twosided,fps:s.fps||0,frames:null,pulse:null,pulseOnly:false,texrotate:s.texrotate||0,clamp:!!s.clamp,distfade:s.distfade||null,atest:s.atest||null};
  if(s.tex){const im=new Image();im.onload=()=>{im._ok=1;draw();};im._clamp=!!s.clamp;im.src=s.tex;rec.img=im;}
  if(s.frames&&s.frames.length>1){
    rec.frames=s.frames.map(u=>{const f=new Image();f.onload=()=>{f._ok=1;draw();};f.src=u;return f;});
  }
  if(s.pulse){
    const pim=new Image();pim.onload=()=>{pim._ok=1;draw();};pim.src=s.pulse.tex;
    const w=s.pulse.wave||['sin',0.25,0.25,0,0.75];
    rec.pulse={img:pim,wave:w,
               white:(typeof s.pulse.tex==='string'&&s.pulse.tex.length<400),  // synthesized $whiteimage overlay vs a real pulse.tga
               distNear:(s.pulse.distnear!=null?s.pulse.distnear:1024),
               distRange:(s.pulse.distrange!=null?s.pulse.distrange:512)};
    rec.pulseOnly=!s.tex;   // ..._ghosting: pulse with no solid base stage
  }
  return rec;}
// A tree's LOD stand-in: `deformVertexes autoSprite2` + `alphaGen oneMinusDistFade`. That
// pairing is what the engine swaps in as the real canopy fades out (the canopy cards use the
// non-inverted `alphaGen distFade`), so it identifies the billboard unambiguously and is what
// the "Tree Sprite" toggle isolates - and what decides whether that button applies at all.
const surfTex=DATA.surfRanges.map(mkSurfTex);
// LIVE draw arrays = the model's own geometry plus whatever is attached to it. Both
// renderers read these instead of DATA.* so an attachment is just another surface: it
// picks up the existing texture fill, wireframe, painter sort and depth test for free.
let LT=DATA.tris, LUV=DATA.uvs, LSR=DATA.surfRanges, LTEX=surfTex;
function isLodSprite(si){const t=LTEX[si];return !!(t&&t.autosprite2&&t.distfade&&t.distfade.inv);}
const hasLodSprite=DATA.surfRanges.some(s=>s.autosprite2&&s.distfade&&s.distfade.inv);
const hasEffectSurf=DATA.surfRanges.some(s=>s.autosprite||s.additive||s.pulse||(s.frames&&s.frames.length>1));
// rev 63: the effect clock can also be started AFTER load. hasEffectSurf is baked from the
// host's own surfaces, so on a plain static model (a cannon) the loop never ran - and an
// attached muzzle flash then had no clock for its animmap frames or its camera-facing
// billboard to advance against. effLoop is a hoisted function declaration, so calling this
// from attRebuild (defined earlier in the file) is fine; the flag keeps it to one loop.
let _effStarted=false;
function startEffLoop(){if(_effStarted)return;_effStarted=true;requestAnimationFrame(effLoop);}
// True once an attachment (or the host) has a surface that needs that clock.
function liveEffectSurf(){return LTEX.some(t=>t&&(t.additive||t.autosprite||t.autosprite2
  ||t.pulse||t.texrotate||(t.frames&&t.frames.length>1)));}
// surfaces whose base stage has a `tcmod rotate` (spinning propeller discs) need the
// continuous effect clock running so their texcoords advance even when the model itself
// is idle / not "playing" - see the effLoop start gate below.
const hasTexRot=DATA.surfRanges.some(s=>s.texrotate);
// world-space centre + radius of a surface (for autosprite billboarding); recomputed
// from the live skinned verts so it follows animation.
function surfCenterRadius(si){const s=LSR[si];const V=model;
  let cx2=0,cy2=0,cz2=0,k=0;
  for(let i=s.vstart;i<s.vend;i++){cx2+=V[i*3];cy2+=V[i*3+1];cz2+=V[i*3+2];k++;}
  if(!k)return null; cx2/=k;cy2/=k;cz2/=k;
  let r=0;for(let i=s.vstart;i<s.vend;i++){const dx=V[i*3]-cx2,dy=V[i*3+1]-cy2,dz=V[i*3+2]-cz2;
    r=Math.max(r,Math.hypot(dx,dy,dz));}
  return [cx2,cy2,cz2,r];}
// effect animation clock (advances continuously so flames/arcs cycle even at rest)
let effT=0;
// PULSATING OVERLAY brightness (items.shader bangalore_pulsating / _ghosting).
// Engine math: a `rgbGen wave` stage's colour multiplier is, per tr_shade_calc.c,
//   glow = WAVEVALUE(base,amp,phase,freq) * tr.identityLight,  clamped to [0,1]
// where WAVEVALUE = base + amp * sin(2*PI*(phase + shaderTime*freq)) (1024-entry sin LUT).
// The stage blends additively (GL_SRC_ALPHA GL_ONE) and is faded by alphaGen distFade
// (tr_shade.c AGEN_DIST_FADE): full strength within fDistNear, ramping to 0 over fDistRange.
// PULSE_IDENTITY is tr.identityLight, calibrated to 0.70 from bangalores.mp4 (the M1A1 body's
// pure-red pulse swings 0.175 in 0..1 framebuffer = 0.498*0.5*identityLight => identityLight~0.70).
const PULSE_IDENTITY=0.70;
// Item pulses (items.shader) all use `rgbGen wave sin <base> <amp> 0 0.75`. OpenMOHAA's
// WAVEVALUE (tr_shade_calc.c:27) advances one full cycle per 1/freq s => 1/0.75 = 1.33s.
// In-game footage pulses ~0.75s, so scale the wave rate to hit that period (1.33/0.75 = 1.78).
const PULSE_RATE=1.00;
// The healthpack white glow (map $whiteimage) has a dim base/amp (0.15/0.075) so its peak reads
// ~half the red pulse.tga glow. Boost the white overlay ~2x to match the in-game brightness,
// leaving the calibrated red-pulse intensity untouched.
const PULSE_WHITE_BOOST=2.0;
function pulseGlow(P){
  const w=P.wave,fn=w[0]||'sin',x=(w[3]||0)+effT*(w[4]||0)*PULSE_RATE;
  let s;
  if(fn==='square')s=(Math.sin(6.2831853*x)>=0?1:-1);
  else if(fn==='triangle'){const fr=x-Math.floor(x);s=fr<0.5?(4*fr-1):(3-4*fr);}
  else if(fn==='sawtooth')s=(x-Math.floor(x))*2-1;
  else if(fn==='inversesawtooth')s=1-(x-Math.floor(x))*2;
  else s=Math.sin(6.2831853*x);            // 'sin' (and default)
  let v=((w[1]||0)+(w[2]||0)*s)*PULSE_IDENTITY*(P.white?PULSE_WHITE_BOOST:1);
  if(v<0)v=0;else if(v>1)v=1;
  // alphaGen distFade: camera-distance fade. The orbit `dist` is far below fDistNear (1024u)
  // in normal viewing, so this is 1.0 in practice - wired faithfully nonetheless.
  if(P.distRange>0){const len=(dist-P.distNear)/P.distRange;
    v*=(len<0?1:(len>1?0:(1-len)));}
  return v;
}
// current animation frame image for a surface record (animMap cycling), else its base image
function curImg(rec){if(!rec)return null;
  if(rec.frames&&rec.frames.length){const n=rec.frames.length;
    let k=Math.floor(effT*(rec.fps||15))%n; if(k<0)k+=n;
    const f=rec.frames[k]; if(f&&f._ok)return f;}
  return (rec.img&&rec.img._ok)?rec.img:null;}
let filterMode='tag'; // 'tag' or 'bone'
let curWorld=worldFromPose(null);
const palette=['#7aa7d8','#d8a07a','#9bd87a','#d87ac0','#7ad8c8','#d8d07a','#b07ad8','#d87a7a'];
// ---- particle emitter simulation (.tik client effects: fire/smoke/sparks) ----
const EM=DATA.emitters||[];
let parts=[]; const spawnAcc=EM.map(()=>0); const PMAX=900;
// Theme colours used by the canvas renderer (grid + tag-label bg) are mirrored from CSS vars so
// they track the Light/Dark toggle. Cached and refreshed on toggle rather than read every frame.
let TH={grid:'#1b212a',labelbg:'8,11,16',tag:'#f2f5f8',origin:'#c084fc',sel:'#7ee787',setsize:'#ff5b6e',bg:'#0e1116'};
function cssVar(n){try{return getComputedStyle(document.documentElement).getPropertyValue(n).trim();}catch(e){return '';}}
function readTheme(){TH.grid=cssVar('--grid')||TH.grid;TH.labelbg=cssVar('--labelbg')||TH.labelbg;
  TH.tag=cssVar('--tag')||TH.tag;TH.origin=cssVar('--origin')||TH.origin;TH.sel=cssVar('--sel')||TH.sel;
  TH.bg=cssVar('--bg')||TH.bg;}
// timed emitter schedule (adamspark-style start-anim sequences). FXC.sched maps an
// emitter NAME to [on,off] windows relative to one instance's start. The level re-triggers
// the whole effect every FXC.refire seconds; each instance runs for FXC.schedlen seconds, so
// when schedlen>refire (lingering smoke past the re-fire point) instances OVERLAP - that
// overlap is what gives the in-game ~1s cadence and the close double-corona, not a 2s loop.
// Emitters absent from the schedule (fire, electric arc, welding) stay continuous.
const FXC=DATA.fxcmds||null;
const EMSCHED=EM.map(e=>(FXC&&FXC.sched&&FXC.sched[e.name])?FXC.sched[e.name]:null);
const FX_REFIRE=FXC?(FXC.refire||FXC.period||1):0;
const FX_SCHEDLEN=FXC?(FXC.schedlen||FXC.period||1):0;
const _hasSched=EMSCHED.some(s=>s);
let _triggers=[];                          // live instances: {t0, acc:[per-emitter stream accum]}
// burst spawn: pass (index,total) so T_CIRCLE bursts distribute EVENLY around the ring -
// SpawnTempModel (cg_tempmodels.cpp:1210-1216): angle = count/spawnthing->count * 360 when
// mcount>1, random only for single spawns. gren_exp / higgins ring smoke and bombdirt's
// stonechip ring rely on this to read as a coherent expanding ring.
function spawnBurst(ei,n){
 const e=EM[ei];
 // VSS spawn events: the engine multiplies count by life seconds (SpawnVSSSource,
 // cg_volumetricsmoke.cpp:730-738, fCountScale = cgd.life/1000) into its 3D volumetric
 // renderer - but the canvas alpha-STACKS overlapping puffs, so applying that multiplier
 // here reads far denser than in-game (thin_black_short / tanksmoke side-by-side footage).
 // One puff per spawn event matches the in-game density; only the pool-saturation cap is
 // kept (VOLMAX mirrors the engine's source pool).
 if(e&&(e.volumetric||(e.flags&&e.flags.indexOf('volumetric')>=0))){
   const room=VOLMAX-_volAlive(); if(room<=0)return; if(n>room)n=room;
 }
 for(let i=0;i<n&&parts.length<PMAX;i++)spawnParticle(ei,i,n);}
// ---- runtime emitter on/off state -------------------------------------------
// Engine default: an emitter is active unless its block carries `startoff`
// (emitterthing_t::GetEmitTime seeds et->active=!startoff, cg_commands.h:531-557;
// EmitterStartOff, cg_commands.cpp:2112-2121). Per-anim `emitteron <n>` /
// `emitteroff <n>` frame commands flip this by NAME (EmitterOn/EmitterOff,
// cg_commands.cpp:3789-3835). Emitters governed by the FXC start-anim schedule
// keep their signed-off timed behaviour and ignore these runtime toggles.
function _emDefaultActive(e){return !(e.flags&&e.flags.indexOf('startoff')>=0);}
const emActive=EM.map(_emDefaultActive);
function setEmitter(name,on){for(let i=0;i<EM.length;i++){
  if(EM[i].name===name&&!EMSCHED[i])emActive[i]=on;}}
// delayed frame commands (commanddelay / delayedsfx wrappers, CommandDelay
// cg_commands.cpp:1573-1607): queued against the effect clock and run when due.
let pendingFx=[];
function queueFx(delay,fn){if(delay>0.001)pendingFx.push({t:effT+delay,fn:fn});else fn();}
function runPendingFx(){if(!pendingFx.length)return;
  const keep=[];for(const p of pendingFx){if(effT>=p.t)p.fn();else keep.push(p);}
  pendingFx=keep;}
// init{client{}} `sfx <spawncmd> ( ... )` one-shots (grenexp_water): the engine runs
// the registered command list when the effect spawns (StartSFXCommand,
// cg_commands.cpp:1623-1678). The viewer's "spawn" is page load - fired once at load,
// again on Reset / Play, and (while Loop is on) every INITFX.period so the one-shot
// stays watchable instead of playing once and never again.
const INITFX=DATA.initfx||null;
let _initfxLast=-1e9;
function fireInitFx(){if(!INITFX)return;_initfxLast=effT;
  for(const sp of INITFX.spawn){const e=EM[sp.em];
    queueFx(sp.delay||0,((ii,n)=>()=>spawnBurst(ii,n))(sp.em,Math.max(1,Math.round(e.count||1))));}}
// ---- per-animation TIKI fx ---------------------------------------------------
// A .tik's animations{} entries carry client tagspawn/originspawn blocks (one-shot
// bursts of `count` tempmodels at the tag's/entity's CURRENT orientation -
// cg_commands.cpp BeginTagSpawn:3534 -> EndTagSpawn:3561 -> SpawnEffect(count))
// and server `surface <name> +/-nodraw` toggles (entity.cpp SurfaceCommand:4158;
// `all` + trailing-* wildcards). They were exported as extra EM entries flagged
// `animfx` plus a per-anim DATA.anims[i].fx trigger table; playback fires them.
const ANIMKIND=DATA.animsKind||'skc';
// Loop defaults OFF (play once and stop - correct for one-shot fx). The user's choice
// is persisted, so if they turn it on it stays on across reloads.
let loopAnim=false;
try{if(localStorage.getItem('mohaaViewerLoop')==='on')loopAnim=true;}catch(_e){}
let animStreams=[];                // flattened sub-tik init emitters: {ei,t0,dur,acc}
const hiddenSurf=new Set();        // surface indices currently +nodraw
function surfIdxByName(nm){const out=[];nm=(nm||'').toLowerCase();
 const star=nm.endsWith('*'),base=star?nm.slice(0,-1):nm;
 DATA.surfRanges.forEach((s,i)=>{const n=(s.name||'').toLowerCase();
  if(nm==='all'||n===base||(star&&n.indexOf(base)===0))out.push(i);});
 return out;}
// ---- surfaces the .tik itself turns off at SPAWN ------------------------------
// `surface bang* +nodraw` in init{server{}} (Entity::SurfaceCommand, entity.cpp:4158-4243,
// mask MDL_SURFACE_NODRAW) or `surface <n> flags nodraw` in setup{} (TIKI_ParseSurfaceFlag,
// tiki_parse.cpp:513-537). These are entity/TIKI load state, NOT an animation command: the
// engine has them set before the model is ever drawn, which is why dday_ranger_private
// carries the whole bangalore_assembly mesh yet shows none of it until the assembly
// animation asks for it.
//
// The ops arrive as PATTERNS in file order and are resolved here, because this is the only
// place the fully assembled (multi-.skd) surface list exists - and in order, because a later
// `-nodraw` clears an earlier `+nodraw` (FLAG_CLEAR, :4234). surfIdxByName already
// implements the engine's matching rule exactly: `all`, or a trailing '*' as a
// case-insensitive PREFIX test over everything before the star (:4222-4227).
//
// Seeded into hiddenSurf right here, before the first draw() and before GL builds its
// buffers, so a hidden surface is never visible for even one frame.
const TIK_NODRAW=new Set();
for(const op of (DATA.tikNodraw||[]))
  for(const i of surfIdxByName(op.name)){if(op.nodraw)TIK_NODRAW.add(i);else TIK_NODRAW.delete(i);}
for(const i of TIK_NODRAW)hiddenSurf.add(i);
// Attachments the ANIMATION asked for. Kept flagged rather than mixed in with the user's
// own, because they are torn down wholesale the moment the animation ends or changes -
// deliberately NOT trusting the .tik to balance its own attach/remove pairs. smoking02 and
// smoking03 both attach breath_emitter.tik to "Bip01 Head" with no removeattachedmodel and
// no removetime (docs: "if not specified, never"), so on repeat playback they would stack
// forever. Duplicates against a user slot on the same bone are allowed through, as asked.
function attPurgeAnim(){
  let n=0;
  for(let i=ATT.length-1;i>=0;i--){if(ATT[i].fromAnim){ATT.splice(i,1);n++;}}
  if(n)attRebuild();
  return n;}

function attAnimDo(at){
  if(curAnim<0)return;
  const fx=DATA.anims[curAnim].fx;if(!fx)return;
  // removeattachedmodel is deliberately NOT acted on. Everything an animation attaches is
  // torn down when the animation ends anyway, so honouring it would only ever strip a
  // model EARLY - smoking01 opens with `first removeattachedmodel "Bip01 L Finger11"`,
  // which in-game clears a leftover from a previous animation but here would just fight
  // the frame-16 attach. It also cannot touch a model the user placed by hand, since only
  // fromAnim slots are ever removed.
  for(const a of (fx.attach||[])){
    if(a.at!==at)continue;
    const bi=attBoneIdx(a.tag);
    if(bi<0)continue;                              // this skeleton has no such bone
    if(ATT.length>=ATT_MAX)continue;               // the engine's own ceiling
    const slot={tag:bi,key:null,path:a.model,scale:a.scale||1,off:[0,0,0],
                ang:attDefaultAng(a.model),bang:attBaseAng(a.model),
                ready:false,fromAnim:true};
    ATT.push(slot);
    const known=ATT_BUILT[a.model];
    if(known&&ATTGEO[known]){slot.key=known;slot.ready=true;attRebuild();}
    else attRequest(a.model);
    attPanelRender();}}

function attBoneIdx(name){
  if(!name)return -1;
  const n=String(name).toLowerCase();
  for(let i=0;i<DATA.bones.length;i++)if(DATA.bones[i].name.toLowerCase()===n)return i;
  return -1;}

function fireAnimAt(at){           // at: 'entry'|'first'|'last'|'end'|'every'|frame number
 attAnimDo(at);
 if(curAnim<0)return;const fx=DATA.anims[curAnim].fx;if(!fx)return;
 for(const sp of (fx.spawn||[])){if(sp.at!==at)continue;
   for(const ei of sp.em){const e=EM[ei];
     // optional commanddelay wrapper (fx_bike_explosion `entry commanddelay 0.100
     // originspawn`): the burst fires sp.delay seconds after its frame trigger
     queueFx(sp.delay||0,((ee,ii)=>()=>{
       if(ee.subdur){
         // sub-tik stream: RESTART a live stream for this emitter instead of
         // stacking a new one - a looping 1-frame anim (jeep `skidding`) re-fires
         // `first` every wrap, and unbounded stacked streams were the lag source.
         const live=animStreams.find(s=>s.ei===ii);
         if(live){live.t0=effT;}
         else animStreams.push({ei:ii,t0:effT,dur:ee.subdur,acc:0});
       } else {
         // one-shot originspawn/tagspawn burst. VOLUMETRIC spawns: the engine's per-call
         // puff count is count * (life/1000) (SpawnVSSSource, cg_volumetricsmoke.cpp:730-736,
         // clamped by vss_maxcount) but these long-lived debris-type puffs accumulate as the
         // effect re-fires, so the VISIBLE steady-state population is far higher than one
         // call. Measured in-game against explosion_bombwall (life 10 -> ~2 puffs, 20 -> ~4,
         // ... ~life/5), so the one-shot volumetric burst emits life/5 puffs - dozens for
         // `life 1536` - instead of the single puff the raw per-call count produced.
         // Continuous VSS smoke stacks are unaffected (still 1 puff/event, the earlier
         // over-spawn fix); only this one-shot burst path multiplies.
         const isVol=(ee.volumetric||(ee.flags&&ee.flags.indexOf('volumetric')>=0));
         let n=Math.max(1,Math.round(ee.count||1));
         if(isVol){
           // ENGINE-EXACT one-shot VSS burst (SpawnVSSSource, cg_volumetricsmoke.cpp:730-760).
           // The engine stores cgd.life = tik_life_seconds * 1000 (ms; cg_testemitter.cpp:540),
           // then fCountScale = cgd.life/1000 = tik_life_seconds. Our ee.life is ALREADY the
           // tik seconds value, so fCountScale = ee.life (no extra /1000).
           //   if (count*fCountScale < vss_maxcount(10)) iSmokeLeft = (int)(count*fCountScale)
           //   else                                      iSmokeLeft = max(10,(int)(fCountScale*count*cg_effectdetail))
           //   while(iSmokeLeft>0){ spawn 1 puff; iSmokeLeft -= 10 }  -> puffs = ceil(iSmokeLeft/10)
           //
           // cg_effectdetail (default 1.0, cg_tempmodels.cpp:234) is the ENGINE'S OWN
           // performance knob and it multiplies iSmokeLeft on the >=10 branch (:734) - lowering
           // it is exactly how the game trims VSS density on weak hardware. explosion_bombwall's
           // debris burst is `count 1 life 1536` -> fCountScale 1536 -> iSmokeLeft 1536 -> 154
           // full 3D volumetric+collision puffs in ONE frame. Every puff then runs per-frame
           // physics + O(n^2) inter-puff repulsion + a multi-layer volumetric composite; the C
           // engine absorbs that (fixed 1024 pool, vss_physics_fps=8 throttle, native render),
           // but 154 in JS at 60fps is the reported lag. We apply an effect-detail scale on the
           // >=10 branch, bounded so the puff count never exceeds VSS_BURST_CAP. Because debris
           // puffs pile up heavily overlapped on the ground (and all decay out together in ~7s
           // via the type-11 density fade, _vssDecay=0.125/s), ~CAP puffs are visually
           // indistinguishable from 154 while costing a fraction. Short/normal bursts are far
           // under the cap and completely unaffected (mist count 30 life 15 -> 450... capped;
           // a typical count 8 life 2 -> 16 puffs, untouched).
           const VSS_BURST_CAP=100;                 // max puffs from one volumetric burst
           const cnt=(ee.count||1), fCountScale=(ee.life||0);
           let iSL;
           if(cnt*fCountScale < 10) iSL=Math.floor(cnt*fCountScale);
           else {
             const _detail=Math.min(1,(VSS_BURST_CAP*10)/(fCountScale*cnt));   // <=1: engine cg_effectdetail
             iSL=Math.floor(fCountScale*cnt*_detail); if(iSL<10)iSL=10;
           }
           ee._vssISL=iSL;
           n=(iSL<=0)?0:Math.ceil(iSL/10);
         }
         if(n>0)spawnBurst(ii,n);
       }
     })(e,ei));}}
 // emitteron / emitteroff toggles (EmitterOn/Off, cg_commands.cpp:3789-3835), with
 // their commanddelay offsets (fx_explosion_tank `enter commanddelay 60 emitteroff smoke`)
 for(const em of (fx.emit||[])){if(em.at!==at)continue;
   queueFx(em.delay||0,((n,o)=>()=>setEmitter(n,o))(em.name,em.on));}
 // fx.surf is deliberately NOT applied here. Firing +/-nodraw incrementally as frames
 // tick past only produces the right picture if every frame is visited in order exactly
 // once - scrubbing, seeking, re-entering an animation or dropping frames under load all
 // desynchronise it, and nothing ever puts it back. animSurfFold() (in the surface section
 // below) instead FOLDS every command with a trigger frame <= curFrame on each applyFrame,
 // so the surface state is a pure function of the frame being displayed.
}
let _lastWrapFire=-1e9;            // throttle stamp for Loop-wrap command re-fires
function fireAnimStart(){_lastWrapFire=effT;
 fireAnimAt('entry');fireAnimAt('first');fireAnimAt(0);
 if(curAnim>=0&&DATA.anims[curAnim].frames.length===1)fireAnimAt('last');}
function fireAnimFrame(f){fireAnimAt('every');fireAnimAt(f);
 if(curAnim>=0&&f===DATA.anims[curAnim].frames.length-1)fireAnimAt('last');}
// resolve tagspawn anchors once: EM.tag name -> bone index (exact, then suffix match)
EM.forEach(e=>{if(!e.tag)return;const tl=e.tag.toLowerCase();
 let hit=DATA.tags.find(t=>t.name.toLowerCase()===tl);
 if(!hit)hit=DATA.tags.find(t=>t.name.toLowerCase().endsWith(tl));
 e._tagIdx=hit?hit.idx:-1;});
// world-units per texture-pixel for .spr sprites. Calibrated so vsssource (32px) at
// scale 1.5 = 27u (the smoke the look is signed off on): 32*0.5625*1.5 = 27. This makes
// the electric arc (256px) render wide like in-game instead of a tiny 5u smear.
// (sprite world-size constant SPR_UNIT is declared near the top of the script)
// load an image and, once decoded, bake the emitter colour into it (so e.g. the
// electric arc reads green) while preserving the original alpha.
// ALPHA-TEST VARIANTS (alphafunc GT0/LT128/GE128, tr_shader.c NameToAFunc :175-196).
// The engine's alpha test is a per-FRAGMENT pass/discard against a fixed cutoff, applied
// to texelAlpha * vertexAlpha (alphaGen vertex). With no blendfunc on the stage
// (effects.shader mortar_dirthit / dirtplume - `blendfunc blend` is commented out),
// passing fragments write fully OPAQUE and failing ones are holes the scene shows
// through. So a fading particle does not turn translucent - it ERODES, losing its
// low-alpha texels first, and vanishes entirely once a < 128/255 (no texel can pass).
// Emulated with per-image threshold canvases:  pass <=> texA * a >= 128  (ge128;
// gt0 / lt128 analogous), computed on a 2x bilinear UPSAMPLE of the texture -
// approximating the GPU's per-fragment test on bilinear-filtered texels, so hole edges
// land at half-texel precision instead of hard texel blocks.
// GRANULARITY: fade alpha is quantised to 128 buckets - on even a 2-second fade that is
// one erosion step per rendered frame, so texels pop off frame-by-frame exactly like the
// engine's continuous cutoff (16 buckets visibly chunked slow fades into ~4-frame steps).
// Fine buckets are affordable because the expensive part - upsample + getImageData - is
// cached ONCE per image (_atBase); each new cutoff is only an alpha-byte pass over a copy
// + putImageData (~1-2ms), and a small FIFO keeps the most recent variant canvases so a
// burst of same-age particles reuses one canvas instead of rebuilding per particle.
const _AT_BUCKETS=128;
const _AT_KEEP=6;                            // variant canvases kept per image (FIFO)
function _atestBase(img,w,h){
 // one-time upsampled RGBA snapshot of the (tinted) sprite; variants copy from this so
 // the pristine pixels are never mutated by thresholding.
 if(img._atBase!==undefined)return img._atBase;
 try{
   const up=(w*h<=320000)?2:1;               // supersample small/medium sprites only
   const cv=document.createElement('canvas'); cv.width=w*up; cv.height=h*up;
   const c2=cv.getContext('2d');
   c2.imageSmoothingEnabled=true;
   c2.drawImage(img,0,0,cv.width,cv.height);
   const id=c2.getImageData(0,0,cv.width,cv.height);
   img._atBase={w:cv.width,h:cv.height,rgba:id.data};
 }catch(_e){ img._atBase=null; }
 return img._atBase;
}
function _atestVariant(img,func,a){
 const w=img.naturalWidth||img.width||0, h=img.naturalHeight||img.height||0;
 if(!w||!h)return null;                       // not decodable yet - caller falls back
 let ai=Math.round(a*_AT_BUCKETS); if(ai>_AT_BUCKETS)ai=_AT_BUCKETS;
 if(ai<=0)return undefined;                   // a == 0: nothing can pass
 const ab=ai/_AT_BUCKETS;
 if(func==='ge128'&&255*ab<128)return undefined;   // fully eroded: even texA=255 fails
 const key=(func==='gt0')?'gt0':(func+':'+ai);
 const C=img._atv||(img._atv={m:{},o:[]});
 if(C.m[key]!==undefined)return C.m[key];
 const base=_atestBase(img,w,h);
 if(!base){ C.m[key]=null; return null; }
 try{
   // POOLED canvases + one reusable ImageData: during a fade the bucket changes nearly
   // every frame, and allocating a fresh full-size canvas + ImageData per bucket was
   // constant GPU-surface/GC churn. Evicted canvases go back to the pool for reuse.
   if(!C.pool)C.pool=[];
   const cv=C.pool.pop()||document.createElement('canvas');
   if(cv.width!==base.w||cv.height!==base.h){cv.width=base.w;cv.height=base.h;}
   const c2=cv.getContext('2d');
   let id=C.id;
   if(!id||id.width!==base.w||id.height!==base.h){id=C.id=c2.createImageData(base.w,base.h);}
   id.data.set(base.rgba);
   const d=id.data;
   for(let i=3;i<d.length;i+=4){
     const A=d[i];
     let pass;
     if(func==='gt0')      pass=A>0;
     else if(func==='lt128')pass=A*ab<128;
     else                   pass=A*ab>=128;   // ge128
     d[i]=pass?255:0;
   }
   c2.putImageData(id,0,0);
   C.m[key]=cv; C.o.push(key);
   if(C.o.length>_AT_KEEP){                              // FIFO: recent fade levels stay warm
     const k0=C.o.shift(), old=C.m[k0]; delete C.m[k0];
     if(old&&C.pool.length<2)C.pool.push(old);
   }
   return cv;
 }catch(_e){ C.m[key]=null; return null; }
}
// ===== ANIMATED DETAIL BUNDLE (nextbundle + tcmod scroll/rotate) =====
// GL_MODULATE second bundle (tr_shader.c:1841-1853) with ANIMATED texcoords. In-game this
// is what makes mortar_dirthit read as 3D falling dirt: `tcmod scroll 0 -.1` listed BEFORE
// `tcmod scale 8 16` gives tc=(uv+o)*S, so the grain drifts DOWN the sprite at 0.1 of the
// texture height per second while the sprite itself climbs - strong internal motion the
// static bake could not show. dirtplume's `tcmod rotate 360` spins its grain instead.
// Fast path (opaque noise): base RGB x noise via canvas 'multiply' + 'destination-in',
// one composite per texture per FRAME (all particles share it) - pure GPU, no readbacks.
// BUNDLE CLOCK: effT is the viewer's effect clock - it advances only while unpaused
// (effLoop: dt=0 when paused), matching the engine, where tcmod time is
// tess.shaderTime = backEnd.refdef.floatTime (tr_shade.c:1524) = client GAME time,
// which freezes on pause. Quantised to 16ms so all particles in a frame share one
// composite; while paused the key holds, so every cache hits and rebuild cost is zero.
function _bfKey(){return Math.floor(effT*62.5);}
function _bfSec(){return _bfKey()*0.016;}
function _bndTile(bnd,tw,th){
 tw=Math.max(1,Math.round(tw)); th=Math.max(1,Math.round(th));
 if(bnd._tile&&bnd._tile.width===tw&&bnd._tile.height===th)return bnd._tile;
 const cv=document.createElement('canvas'); cv.width=tw; cv.height=th;
 cv.getContext('2d').drawImage(bnd.img,0,0,tw,th);
 bnd._tile=cv; return cv;
}
function _bndTileOp(bnd,tw,th){
 // OPAQUE-RGB noise tile (alpha forced 255). GL_MODULATE multiplies the FULL RGB of both
 // bundles regardless of alpha; canvas 'multiply' with a semi-transparent source only
 // PARTIALLY modulates (Co=(1-as)*Cb+as*Cb*Cs), which left vsssource's smoke too bright.
 // a=0 texels lose their RGB to premultiplication (become black), but the halpha
 // destination-in pass multiplies final alpha by that same ~0, so they never show.
 tw=Math.max(1,Math.round(tw)); th=Math.max(1,Math.round(th));
 if(bnd._tileOp&&bnd._tileOp.width===tw&&bnd._tileOp.height===th)return bnd._tileOp;
 const cv=document.createElement('canvas'); cv.width=tw; cv.height=th;
 const c=cv.getContext('2d'); c.drawImage(bnd.img,0,0,tw,th);
 try{
   const d=c.getImageData(0,0,tw,th), a=d.data;
   for(let i=3;i<a.length;i+=4)a[i]=255;
   c.putImageData(d,0,0);
 }catch(_e){}
 bnd._tileOp=cv; return cv;
}
function _baseOp(base){
 // OPAQUE-RGB copy of the (tinted) base, alpha forced 255, cached once per emitter image.
 // Canvas 'multiply' is a BLEND, not a component multiply: at dest alpha ab it computes
 // Co = (1-ab)*Cs + ab*Cs*Cb, i.e. it interpolates toward the SOURCE colour wherever the
 // base is translucent. A soft smoke sprite is low-alpha nearly everywhere, so the halpha
 // composite's RGB collapsed to the bright grey of the raw noise (~0.7) instead of the
 // engine's GL_MODULATE product tintedBase*noise (~0.24) - mid-grey puffs that read WHITE
 // on a dark backdrop and brown on a light one. With BOTH layers opaque the blend reduces
 // to the exact component product; the two destination-in passes then rebuild the true
 // alpha (base.a * noise.a). a=0 texels lose their RGB to premultiplication (black), but
 // final alpha is ~0 there, so they never show.
 if(base._op)return base._op;
 const w=base.naturalWidth||base.width||0, h=base.naturalHeight||base.height||0;
 const cv=document.createElement('canvas'); cv.width=w; cv.height=h;
 const c=cv.getContext('2d'); c.drawImage(base,0,0);
 try{
   const d=c.getImageData(0,0,w,h), a=d.data;
   for(let i=3;i<a.length;i+=4)a[i]=255;
   c.putImageData(d,0,0);
 }catch(_e){}
 base._op=cv; return cv;
}
function _bndPaint(c2,bnd,W2,H2,tSec,mode,opq,rs){
 // paint the animated, tiled noise over c2. mode 'multiply' (default) modulates the RGB
 // already there (caller re-masks alpha); mode 'destination-in' multiplies the ALPHA
 // already there by the noise alpha (GL_MODULATE A=A0*A1). opq swaps in the alpha-255
 // tile so the multiply pass modulates FULL RGB even where the noise is translucent.
 const sx=Math.abs(bnd.scale[0])||1, sy=Math.abs(bnd.scale[1])||1;
 const tw=W2/sx, th=H2/sy;
 const tile=opq?_bndTileOp(bnd,tw,th):_bndTile(bnd,tw,th);
 let pat=null; try{pat=c2.createPattern(tile,'repeat');}catch(_e){pat=null;}
 if(!pat)return false;
 let ox=0,oy=0;
 if(bnd.scroll){
   // pattern drift: -scrollrate in base-uv/sec when scroll is listed before scale
   // (tc=(uv+o)*S - drift independent of S); listed after -> drift divided by scale.
   ox=(-bnd.scroll[0]*tSec*W2)*(bnd.prescale?1:1/sx);
   oy=(-bnd.scroll[1]*tSec*H2)*(bnd.prescale?1:1/sy);
   ox=((ox%tw)+tw)%tw; oy=((oy%th)+th)%th;
 }
 c2.save();
 c2.globalCompositeOperation=mode||'multiply';
 if(bnd.rotate){
   // tcmod rotate (tr_shade_calc.c:1599-1631): degs = -degsPerSecond * shaderTime, applied
   // to TEXCOORDS about (0.5,0.5). Inverting the sampling relation, the visible PATTERN
   // spins at +degsPerSecond clockwise (y-down screen space) - canvas rotate(+).
   c2.translate(W2/2,H2/2); c2.rotate(bnd.rotate*(rs||1)*tSec*Math.PI/180); c2.translate(-W2/2,-H2/2);
 }
 c2.translate(ox,oy);
 c2.fillStyle=pat;
 // overfill rect whose pattern-space centre (W2/2-ox, H2/2-oy) maps EXACTLY to the canvas
 // centre through the translate+rotate chain, with a diagonal-sized half-extent - covers
 // the whole canvas under any rotation angle and any scroll offset, tall canvases included.
 const _E=Math.hypot(W2,H2)+Math.hypot(tw,th);
 c2.fillRect(W2/2-ox-_E, H2/2-oy-_E, 2*_E, 2*_E);
 c2.restore();
 return true;
}
function _bndK(bnd,w,h){
 // DETAIL FACTOR: rasterising the noise tile at base/scale pixels crushed mortar_noise to
 // 32x32, averaging away exactly the high-frequency grain the engine keeps (GL samples the
 // full-res bundle texture per tile). That single loss caused BOTH regressions: erosion in
 // big soft radial chunks (smooth combined alpha) and visible dark "waves" (each tile
 // reduced to its light/dark average - a periodic band scrolling by). Composite at k x
 // base so tiles keep >=64px of noise detail, capped by total area.
 const sx=Math.abs(bnd.scale[0])||1, sy=Math.abs(bnd.scale[1])||1;
 const tmin=Math.min(w/sx,h/sy);
 let k=Math.max(1,Math.ceil(64/Math.max(1,tmin)));
 while(k>1&&(w*k)*(h*k)>2400000)k--;
 return k;
}
function _bundleFrame(base,bnd,modAlpha){
 // (tinted) base x animated noise - engine GL_MODULATE (nextbundle, tr_shader.c:1841-1853).
 // Cached per effect-frame per image: every particle of the burst reuses one composite.
 // Rendered at k x base resolution (see _bndK) so the tiled noise keeps its grain.
 // modAlpha (NON-alpha-tested sprites only): GL texture-env MODULATE multiplies ALPHA as
 // well as RGB (A = A0*A1). vsssource's counter-rotating vsssource2 bundle carries a real
 // alpha channel (bnd.halpha, shipped by the launcher); dropping it left every puff far
 // too opaque - 40 alpha-.5 sprites stacked to near-solid white splotches instead of the
 // translucent brown churn in-game (mortar_dirt_dustcloud). Alpha-TESTED sprites keep the
 // base-alpha-only path: the in-game-verified erosion pattern is the BASE texture's alpha
 // (mortar_dirthit sign-off), so their behaviour is bit-identical to before.
 // bnd.brot: the BASE stage's own `tcmod rotate` (vsssource: +20 vs bundle -20 -
 // scripts/sprites.shader). RB_CalcRotateTexCoords spins base texcoords about (.5,.5);
 // for a clampmap sprite with transparent borders, rotating the drawn image about centre
 // is exactly the clamped-texcoord rotation. Base and noise counter-rotate = the churn.
 const w=base.naturalWidth||base.width||0, h=base.naturalHeight||base.height||0;
 if(!w||!h||!bnd.img._ok)return null;
 const fk=_bfKey(), _ma=!!(modAlpha&&bnd.halpha);
 let R=base._bf;
 if(R&&R.k===fk&&R.ma===_ma)return R.cv;
 if(!R)R=base._bf={k:-1,ma:false,cv:document.createElement('canvas')};
 const K=_bndK(bnd,w,h), W2=w*K, H2=h*K;
 // PERSISTENT canvas: resizing a canvas reallocates its GPU surface - doing that every
 // frame was a large part of the bundle lag. Resize only when dims actually change.
 if(R.cv.width!==W2||R.cv.height!==H2){R.cv.width=W2;R.cv.height=H2;}
 const c2=R.cv.getContext('2d');
 const _t=_bfSec(), _br=(bnd.brot||0)*_t*Math.PI/180;
 const _db=function(img){                             // draw base with its tcmod rotate
   if(_br){c2.save();c2.translate(W2/2,H2/2);c2.rotate(_br);c2.translate(-W2/2,-H2/2);
           c2.drawImage(img,0,0,W2,H2);c2.restore();}
   else c2.drawImage(img,0,0,W2,H2);
 };
 c2.globalCompositeOperation='source-over';
 c2.clearRect(0,0,W2,H2);
 c2.imageSmoothingEnabled=true;
 _db(_ma?_baseOp(base):base);   // _ma: opaque base so 'multiply' is a pure component product
 if(!_bndPaint(c2,bnd,W2,H2,_t,'multiply',_ma))return null;   // no pattern support: caller falls back
 c2.globalCompositeOperation='destination-in';       // rebuild alpha: re-mask by REAL base
 _db(base);
 if(_ma)_bndPaint(c2,bnd,W2,H2,_t,'destination-in'); // x noise alpha: A = A0 * A1
 c2.globalCompositeOperation='source-over';
 R.k=fk; R.ma=_ma; return R.cv;
}
// ===== VOLUMETRIC (VSS) PER-PUFF FRAME =====
// The engine renders each VSS puff as VSSSource.spr / VSSSource2.spr (AddVSSSources,
// cg_volumetricsmoke.cpp:1167-1168) with per-puff state the shared flat-sprite composite
// cannot express: colour = lighting x (0.7..1.0 jitter) x cgd.color (:762-766 +
// VSS_LerpSource :651-662), rotation direction by the per-puff T_RANDOMROLL coin flip
// (:779-781, :1331-1340) and a per-puff tcmod phase frozen at spawn (:1342, roll walk
// :1312-1329). _vssFrame builds/caches a composite per (tint, sign, phase-bucket) key.
// SMOKE_LIGHT stands in for R_GetLightingForSmoke (:1261): the engine samples the MAP's
// lighting grid at every puff and multiplies it into the colour. The viewer has no map, so
// this is pinned at the engine-neutral value - vss_color defaults to 1 (:266) and an unlit
// sample is a 1.0 multiplier, i.e. the puff shows its authored `color` untouched. (This used
// to be a panel dial; the slot now holds the placement-angle dial. Anything other than 1.0 is
// a lighting guess the .tik does not contain, so the constant is the faithful choice.)
const SMOKE_LIGHT=1.0;
function _vssTint(rec,e,fq){
 // tint variant: raw sprite x min(1, emitter colour * fq), alpha re-masked - the exact
 // _loadTinted math with the lighting/jitter factor folded in. Cached per quantized fq.
 let T=rec._tv; if(!T)T=rec._tv={m:new Map()};
 let cv=T.m.get(fq); if(cv)return cv;
 const im=rec.img; const w=im.naturalWidth||im.width||0,h=im.naturalHeight||im.height||0;
 if(!w||!h)return null;
 const col=(e.rgbvertex===false)?[1,1,1]:(e.color||[1,1,1]);
 const tr=Math.min(1,col[0]*fq),tg=Math.min(1,col[1]*fq),tb=Math.min(1,col[2]*fq);
 cv=document.createElement('canvas');cv.width=w;cv.height=h;const c2=cv.getContext('2d');
 c2.drawImage(im,0,0);
 c2.globalCompositeOperation='multiply';
 c2.fillStyle='rgb('+(tr*255|0)+','+(tg*255|0)+','+(tb*255|0)+')';c2.fillRect(0,0,w,h);
 c2.globalCompositeOperation='destination-in';c2.drawImage(im,0,0);
 c2.globalCompositeOperation='source-over';
 if(T.m.size>40)T.m.clear();
 T.m.set(fq,cv); return cv;
}
function _vssComposite(rec,bnd,base,tSec,rs){
 // one puff-state composite: the _bundleFrame halpha pipeline with an explicit tinted
 // base, explicit tcmod time and the per-puff rotation sign on BOTH layers.
 const w=base.width,h=base.height; if(!w||!h||!bnd.img._ok)return null;
 const K=_bndK(bnd,w,h), W2=w*K, H2=h*K;
 const cv=document.createElement('canvas');cv.width=W2;cv.height=H2;
 const c2=cv.getContext('2d');
 const _ha=!!bnd.halpha;
 const _br=(bnd.brot||0)*rs*tSec*Math.PI/180;
 const _db=function(img){
   if(_br){c2.save();c2.translate(W2/2,H2/2);c2.rotate(_br);c2.translate(-W2/2,-H2/2);
           c2.drawImage(img,0,0,W2,H2);c2.restore();}
   else c2.drawImage(img,0,0,W2,H2);
 };
 c2.imageSmoothingEnabled=true;
 _db(_ha?_baseOp(base):base);
 if(!_bndPaint(c2,bnd,W2,H2,tSec,'multiply',_ha,rs))return null;
 c2.globalCompositeOperation='destination-in';
 _db(base);
 if(_ha)_bndPaint(c2,bnd,W2,H2,tSec,'destination-in',false,rs);
 c2.globalCompositeOperation='source-over';
 return cv;
}
function _vssFrame(p){
 const rec=emitImg[p.ei]; if(!rec||!rec.img||!rec.img._ok)return null;
 const e=EM[p.ei], V=p.v||{};
 const f=Math.max(0,Math.min(1.5,(V.cj||1)*SMOKE_LIGHT));
 const fq=Math.round(f*16)/16;                       // 1/16 tint quantization
 const base=_vssTint(rec,e,fq); if(!base)return null;
 const bnd=rec.bnd;
 if(!(bnd&&bnd.img&&bnd.img._ok))return base;        // bundle not shipped/loaded yet
 const ph=(V.ph||0)+(V.rw||0), rs=V.rs||1;
 const pb=Math.round(ph*16);                         // 62.5 ms phase buckets (1.25deg at 20deg/s)
 const key=fq+'|'+rs+'|'+pb;
 let C=rec._vssC; if(!C)C=rec._vssC={m:new Map()};
 let cv=C.m.get(key); if(cv)return cv;
 cv=_vssComposite(rec,bnd,base,pb/16,rs);
 if(!cv)return base;
 if(C.m.size>96)C.m.clear();
 C.m.set(key,cv);
 return cv;
}
function _maskApply(mod,mask){
 // modulated RGB cut by the cached alpha-test mask (destination-in) - pure GPU. Cached on
 // the mask per frame, so same-fade-bucket particles share one canvas.
 const fk=_bfKey();
 let R=mask._fin;
 if(R&&R.k===fk)return R.cv;
 if(!R)R=mask._fin={k:-1,cv:document.createElement('canvas')};
 if(R.cv.width!==mask.width||R.cv.height!==mask.height){R.cv.width=mask.width;R.cv.height=mask.height;}
 const c2=R.cv.getContext('2d');
 c2.globalCompositeOperation='source-over';
 c2.clearRect(0,0,mask.width,mask.height);
 c2.imageSmoothingEnabled=true;
 c2.drawImage(mod,0,0,mask.width,mask.height);
 c2.globalCompositeOperation='destination-in';
 c2.drawImage(mask,0,0);
 c2.globalCompositeOperation='source-over';
 R.k=fk; return R.cv;
}
function _loadTinted(url,col){
  const im=new Image();
  im.onload=()=>{ im._ok=1;
    // ENGINE TINT - EXACT byte path (cg_tempmodels.cpp TempModelRealtimeEffects:417-451):
    //   tempColor[i] = (int)(cgd.color[i] * 255.0f)   // stored in a `byte tempColor[4]`
    //   ent.shaderRGBA[i] = tempColor[i]              // (no grid-lighting -> direct copy)
    // tempColor is a BYTE array, so the (int) result is TRUNCATED into a byte: the value
    // WRAPS mod 256, it is NOT clamped to 255. This is the crux of adam-hallfire2:
    //   color 4.50 0.20 0.00 -> (int)(4.5*255)=1147 -> 1147 & 0xFF = 123  -> (123, 51, 0)
    //   color 3.00 2.00 1.00 -> 765&255=253, 510&255=254, 255            -> (253,254,255) ~ WHITE
    //   color 4.00 2.00 2.00 -> 1020&255=252, 510&255=254, 510&255=254   -> (252,254,254) ~ WHITE
    // So the two "3/4-ish x2 x1/2" emitters wrap to near-white and let the warm fireball
    // texture show through as orange/white (the big blooms in-game), while 4.5/0.2/0 wraps
    // to a dim warm brown. The old min(1,col) pre-clamp turned 4.5 into 1.0 and multiplied
    // the texture by pure red -> the solid-red blobs. Reproduce the wrap, THEN multiply the
    // texel by (wrappedByte/255), clamping the PRODUCT at the framebuffer (never the factor).
    const wr=(c)=>((Math.trunc(c*255))&0xFF)/255;
    const fr=wr(col[0]),fg=wr(col[1]),fb=wr(col[2]);
    if(Math.abs(fr-1)>0.004||Math.abs(fg-1)>0.004||Math.abs(fb-1)>0.004){
      const cw=im.naturalWidth||64,ch=im.naturalHeight||64;
      const cv=document.createElement('canvas');cv.width=cw;cv.height=ch;const c2=cv.getContext('2d');
      c2.drawImage(im,0,0);
      try{
        const id=c2.getImageData(0,0,cw,ch),d=id.data;
        for(let i=0;i<d.length;i+=4){
          d[i]  =Math.min(255,d[i]  *fr);
          d[i+1]=Math.min(255,d[i+1]*fg);
          d[i+2]=Math.min(255,d[i+2]*fb);   // alpha (d[i+3]) untouched
        }
        c2.putImageData(id,0,0);
        im._tinted=cv;
      }catch(_e){
        // getImageData can throw on a tainted canvas; fall back to the clamped multiply.
        c2.globalCompositeOperation='multiply';c2.fillStyle='rgb('+(fr*255|0)+','+(fg*255|0)+','+(fb*255|0)+')';c2.fillRect(0,0,cw,ch);
        c2.globalCompositeOperation='destination-in';c2.drawImage(im,0,0);
        c2.globalCompositeOperation='source-over';
        im._tinted=cv;
      }
    }
    if(typeof draw==='function')draw();
  };
  im.src=url; return im;
}
// per-emitter sprite record. e.sprite is either a data-url string (single frame) or
// {tex, frames:[...], fps, additive} for animMap sprites (electric arc cycles 3 frames).
const emitImg=EM.map(e=>{
  if(!e.sprite) return null;
  // SHADER TINT RULE: the emitter `color` reaches the framebuffer only through
  // `rgbGen vertex` (sprites carry shaderRGBA on their verts). Shaders WITHOUT it -
  // corona_util / corona_reg / gren_boom / air_explosion, all plain `blendfunc add`
  // stages in scripts/sprites.shader - render their texture colours untouched, so the
  // blowtorch's `color 1.5 0.1 0.1` corona is WHITE in-game, not red. e.rgbvertex===false
  // is set by the launcher from the shader props; absent info keeps the old tint fallback.
  const col=(e.rgbvertex===false)?[1,1,1]:(e.color||[1,1,1]);
  let rec;
  if(typeof e.sprite==='string') rec={img:_loadTinted(e.sprite,col),frames:null,fps:0};
  else{
    rec={img:_loadTinted(e.sprite.tex,col),fps:e.sprite.fps||0,frames:null};
    if(e.sprite.frames&&e.sprite.frames.length>1) rec.frames=e.sprite.frames.map(u=>_loadTinted(u,col));
  }
  // ANIMATED nextbundle (tcmod scroll/rotate): the detail texture is shipped separately
  // and multiplied over the sprite per frame at runtime (see _bundleFrame) - the drifting
  // grain that reads as dirt falling through the plume in-game. NOT tinted: GL_MODULATE
  // chains base x bundle x shaderRGBA, and the tint is already in rec.img.
  // EROSION IMAGE: the launcher's old-style phase-0 bake (base x noise). Its alpha is
  // the in-game-verified granular dissolve pattern - the speckle comes from the NOISE
  // texture's alpha, which the unbaked base lacks (its own alpha has smooth mid-tone
  // regions that thresholded into the rounded-blob fade). Only the alpha is consumed.
  if(e.erode_sprite){ rec.erode=_loadTinted(e.erode_sprite,col); }
  if(e.bundle&&e.bundle.tex){
    const ni=new Image(); ni.onload=()=>{ni._ok=1;}; ni.src=e.bundle.tex;
    // halpha (noise alpha varies) is exported by the launcher but intentionally NOT used:
    // frame-by-frame in-game comparison - the project's sign-off standard - shows the
    // dissolve pattern is the BASE texture's granular alpha, neither animated by the
    // bundle's tcmods nor blended with the bundle's smooth per-tile alpha. The bundle
    // affects RGB grain only.
    rec.bnd={img:ni, scale:(e.bundle.scale||[1,1]), scroll:(e.bundle.scroll||null),
             prescale:!!e.bundle.prescale, rotate:(e.bundle.rotate||0),
             brot:(e.bundle.brot||0), halpha:!!e.bundle.halpha};
  }
  return rec;
});
// per-emitter debris-mesh texture (M3.tex data-url from the sub-tik's surface shader)
const _meshImgs=EM.map(()=>undefined);
function _meshImg(ei){
  let im=_meshImgs[ei];
  if(im!==undefined)return (im&&im._ok)?im:null;
  const M3=EM[ei].mesh;
  if(!M3||!M3.tex){_meshImgs[ei]=null;return null;}
  im=new Image(); im.onload=()=>{im._ok=1;if(typeof draw==='function')draw();};
  im.src=M3.tex; _meshImgs[ei]=im;
  return im._ok?im:null;
}
// true when this emitter HAS a debris-mesh texture that just hasn't decoded yet (first play,
// before the Image onload fires). Distinguishes "still loading" from "genuinely untextured"
// so the mesh draw can SKIP the frame instead of painting the flat-colour fallback - which,
// when the emitter color is white (bh_wood_piece / bh_stone_piece debris, color 1 1 1),
// showed as a one-frame WHITE FLASH on the very first play only. Kicks off the load if needed.
function _meshTexPending(ei){
  const M3=EM[ei].mesh; if(!M3||!M3.tex)return false;   // no texture at all -> flat is correct
  const im=_meshImg(ei);                                 // triggers the load, returns img|null
  return !im;                                            // has tex but not ready -> pending
}
// FLAT SHADE WITHOUT DESTROYING TEXTURE ALPHA. The old facet path painted the shade as a
// solid black triangle ON TOP of the textured facet, so every TRANSPARENT texel of an
// alpha-cut skin showed the shade instead of the scene behind it - the semi-transparent black
// square around every bh_foliage_leaf card (and around any foliage/wire debris skin).
// In-engine a tempmodel is an RT_MODEL refEntity (cg_tempmodels.cpp:1322-1325) drawn through
// the normal GL_MODULATE stage chain: the lit colour multiplies the TEXEL and leaves its alpha
// untouched. Reproduce that by multiplying the shade into a cached copy of the skin and
// restoring the source alpha with destination-in (the same compositing _loadTinted uses).
// m = 1-(1-lit)*0.55 is the exact shade factor the signed-off debris chunks were calibrated
// with, so fully-opaque skins (metal_section / ibeam_piece / concrete) stay pixel-identical;
// only transparent texels change.
function _meshShade(img,lit){
  const m=Math.max(0,Math.min(1,1-(1-lit)*0.55));
  const q=Math.round(m*16)/16;                 // 1/16 buckets -> at most 17 cached canvases
  if(q>=0.999)return img;
  let C=img._msh; if(!C)C=img._msh={};
  if(C[q])return C[q];
  const w=img.naturalWidth||img.width||64, h=img.naturalHeight||img.height||64;
  const cv=document.createElement('canvas'); cv.width=w; cv.height=h;
  const c2=cv.getContext('2d');
  c2.drawImage(img,0,0);
  c2.globalCompositeOperation='multiply';
  const g=(q*255)|0; c2.fillStyle='rgb('+g+','+g+','+g+')'; c2.fillRect(0,0,w,h);
  c2.globalCompositeOperation='destination-in'; c2.drawImage(img,0,0);
  c2.globalCompositeOperation='source-over';
  C[q]=cv; return cv;
}
// current (tinted) sprite frame for a particle's emitter, cycling animMap frames on effT
// cg_tempmodels.cpp:1312: ent.shaderTime = cg.time/1000 at spawn; :1046 copies it to
// newEnt unchanged. Renderer frame = (currentTime - shaderTime) * fps = p.age * fps.
// effT (global time) was wrong: bang.spr started mid-animation on every fire.
function emitFrame(ei,age){const r=emitImg[ei];if(!r)return null;let im=r.img;
  if(r.frames&&r.frames.length){const n=r.frames.length;let k=Math.floor((age??effT)*(r.fps||15))%n;if(k<0)k+=n;
    if(r.frames[k]&&r.frames[k]._ok)im=r.frames[k];}
  if(!im||!im._ok)return null;return im._tinted||im;}
function _rc(c){if(!c)return 0;const v=c[1];
  // MOHAA `range A B` => base=A, amplitude=B (value = A + rand*B), per SetBaseAndAmplitude.
  // (was c[2]+rand*c[1], which swapped base/amplitude and biased offset+velocity off-centre.)
  return c[0]==='crandom'?(Math.random()*2-1)*v:c[0]==='random'?Math.random()*v:c[0]==='range'?c[1]+Math.random()*c[2]:v;}
function spawnParticle(ei,bidx,btot){
 const e=EM[ei],rv=e.randvel||e.randvelaxis||[],ac=e.accel||[0,0,0],col=e.color||[1,1,1];
 // Spawn position is built in MOHAA space (mx,my,mz; z=up), converted to render (x,z,y) at
 // the end - the old code mixed the two spaces and put the T_CIRCLE ring on the render UP
 // axis, which turned every mushroom-ring (higgins / barracks `test` / explosion_tank) into
 // a VERTICAL ring: puffs sprayed "in random planar directions" and spawned ABOVE the origin
 // (the +radius landed on the up axis). Engine order per SpawnTempModel
 // (cg_tempmodels.cpp:1198-1290): shape placement (sphere/circle/inwardsphere/cone/radius)
 // -> origin_offset -> forwardVelocity along newForward -> axis offsets -> radialvelocity ->
 // randvel. The effect entity's axis is treated as identity with forward=UP: fx entities are
 // placed `angles 270 0 0` (pitch 270 = facing straight up) so axis[0]=up and the circle/cone
 // ring (built around axis[0], cg_tempmodels.cpp:1207-1216 / :1239-1264) lies HORIZONTAL.
 let mx=0,my=0,mz=0;
 const spd=e.velocity||0; let dxm=0,dym=0,dzm=1;      // newForward, MOHAA space (default up)
 const fl=e.flags||[], inw=fl.indexOf('inwardsphere')>=0;
 if(inw){                                             // spawn on a shell, fly toward centre
   // SetInwardSphere/T_INWARDSPHERE (cg_tempmodels.cpp:1227-1238): dir is sampled from the
   // unit BALL (crandom cube, rejected while dot>1, NOT normalized), spawn at dir*radius
   // (i.e. INSIDE the shell, biased outward), forward = -dir - so both spawn distance and
   // inward speed vary per particle instead of a uniform shell at constant speed.
   let ox,oy,oz,l2;
   do{ox=Math.random()*2-1;oy=Math.random()*2-1;oz=Math.random()*2-1;l2=ox*ox+oy*oy+oz*oz;}while(l2>1);
   // sphereRadius DEFAULTS TO 0 (SetSpawnthing, cg_commands.cpp:3055) - it is only nonzero
   // when the tik sets `radius`. water_splash2 has no radius line, so every puff spawns AT
   // the origin (end = origin + dir*0) and flies inward along -dir at `velocity`; with
   // friction 1 they stay tightly centralized. The old ||12 fallback scattered them onto a
   // radius-12 shell and then let them overshoot the centre, spreading them out like the
   // separate oceanspray.sphere effect - the "too spread out" look you saw.
   const R=(e.radius!=null)?e.radius:0;
   mx+=ox*R;my+=oy*R;mz+=oz*R; dxm=-ox;dym=-oy;dzm=-oz;
 } else if(fl.indexOf('sphere')>=0){
   // T_SPHERE (cg_tempmodels.cpp:1201-1206): newForward = crandom cube REJECTED to the unit
   // ball and NOT normalized - forwardVelocity rides this short vector, so sphere-burst
   // speeds are distributed 0..velocity (mean ~0.48x), not a constant full-speed shell.
   // This is why in-game panelmelt/welding sparks read slower and less uniform than the
   // viewer's old always-unit directions.
   do{dxm=Math.random()*2-1;dym=Math.random()*2-1;dzm=Math.random()*2-1;}
   while(dxm*dxm+dym*dym+dzm*dzm>1);
 } else if(fl.indexOf('circle')>=0){
   // T_CIRCLE (cg_tempmodels.cpp:1207-1226): end = vLeft * sphereRadius, rotated around
   // vFORWARD - with the fx entity's identity axis (forward=+X, left=+Y, up=+Z) the ring
   // lies in the MOHAA Y-Z plane, i.e. a VERTICAL ring perpendicular to the X axis
   // (confirmed against in-game footage: higgins/wallsplitter rings expand "one axis
   // over", not flat). Burst spawns are EVENLY spaced (angle = i/count*360), single
   // spawns random; forward = outward from centre.
   // NOTE: sphereRadius here is whatever the LAST radius-setting command stored - `cone
   // h r` writes r into the same slot (SetCone, cg_commands.cpp:2326-2334), so a block
   // with both `cone 300 20` and `circle` (wallsplitter blockcrete) rings at radius 20.
   // Without that fallback the chunk spawned AT the origin and radialvelocity's
   // zero-length radial vector nulled its velocity - the straight-down fall.
   const th=(btot>1)?(bidx/btot)*6.2832:Math.random()*6.2832;
   const R=(e.radius!=null)?e.radius:((e.cone&&e.cone[1])||0);
   // Ring in the MOHAA X-Y (horizontal) plane by default: most ring emitters are mine/
   // explosion effects mounted on the ground, whose entity forward faces up, so the ring
   // sprays outward flat along the floor. Wall-mounted ring effects (wallsplitter) will
   // read rotated until per-emitter orientation exists, but the common ground case is the
   // sensible default.
   if(R){dxm=Math.cos(th);dym=Math.sin(th);dzm=0;
         mx+=dxm*R;my+=dym*R;}
   else{
     // sphereRadius == 0: the ENTIRE circle block is skipped in-engine (cg_tempmodels.cpp:
     // 1208 `if (sphereRadius != 0)`) and newForward stays the ENTITY's forward axis
     // (:1198). For prop/wall-mounted fx (welding_spark sparks1b: `circle`, no radius,
     // velocity 200) that forward is HORIZONTAL in the map, so the sparks spray sideways
     // and arc down under gravity - never a vertical fountain. The viewer has no map
     // orientation, so emulate a horizontal forward at a random (or burst-even) ring angle;
     // randvelaxis/randvel spread then applies on top exactly as in-game.
     dxm=Math.cos(th);dym=Math.sin(th);dzm=0;
   }
 } else if(fl.indexOf('cone')>=0){
   // T2_CONE (cg_tempmodels.cpp:1239-1264): h=random, r=random, swap so h>=r; pos =
   // forward*h*coneHeight + ring of coneRadius at a random angle. Forward stays the axis
   // (up), so `velocity` lifts the puff while radialvelocity pushes it outward - the
   // bombdirt central cloud's low, wide burst.
   const cn=e.cone||[0,0]; let fh=Math.random(),fr=Math.random();
   if(fh<fr){const t_=fh;fh=fr;fr=t_;}
   const th=Math.random()*6.2832,R=(cn[1]||0);
   mz+=fh*(cn[0]||0); mx+=Math.cos(th)*R; my+=Math.sin(th)*R;
 } else if(e.radius){
   // bare `radius` (cg_tempmodels.cpp:1265-1275): dir = normalized random vector, spawn ON
   // the shell at dir*radius (not scattered in a cube), forward = dir.
   const th=Math.random()*6.2832,ph=Math.acos(2*Math.random()-1);
   dxm=Math.sin(ph)*Math.cos(th);dym=Math.sin(ph)*Math.sin(th);dzm=Math.cos(ph);
   mx+=dxm*e.radius;my+=dym*e.radius;mz+=dzm*e.radius;
 }
 // origin offset AND axis offset BOTH apply (cg_tempmodels.cpp:1283-1288 origin_offset,
 // then :1497-1508 axis_offset along the tag/entity axis). The old `offset||offsetalongaxis`
 // dropped whichever came second - fireandsmoke's `offset 0 0 135` swallowed its
 // `offsetalongaxis crandom 16 ...` scatter so every puff spawned at the exact same spot.
 const ofo=e.offset||[],ofa=e.offsetalongaxis||[];
 // ENTITY-SPACE vs WORLD-SPACE split, which only becomes visible once the placement dial is
 // off zero. axis_offset is added ALONG the tag/entity axis (cg_tempmodels.cpp:1497-1508) and
 // the shape placement + newForward are built FROM that axis (vForward/vLeft/vUp, :1163-1168),
 // so all three turn with the entity. origin_offset is added in raw WORLD components
 // (:1279-1283) and does NOT. Likewise plain `randvel` adds to velocity[i] componentwise in
 // world space - only `randvelaxis` goes through the axis (:1524-1538) - and `accel` is world
 // gravity. So the rotation is applied to the entity-space part alone, in between.
 mx+=_rc(ofa[0]); my+=_rc(ofa[1]); mz+=_rc(ofa[2]);
 if(EROT){const _rp=erotV(mx,my,mz);  mx=_rp[0]; my=_rp[1]; mz=_rp[2];
          const _rd=erotV(dxm,dym,dzm);dxm=_rd[0];dym=_rd[1];dzm=_rd[2];}
 mx+=_rc(ofo[0]); my+=_rc(ofo[1]); mz+=_rc(ofo[2]);
 // MOHAA -> render mapping (x,z,y)
 let px=mx,py=mz,pz=my, dx=dxm,dy=dym,dz=dzm;
 // tagspawn anchor: spawn at the named tag's CURRENT world position (the engine
 // reads the tag orientation at command time - GetOrientation in BeginTagSpawn,
 // cg_commands.cpp:3534) instead of the model origin. MOHAA (x,y,z) -> render (x,z,y).
 if(e._tagIdx>=0&&curWorld){const Tt=curWorld.T[e._tagIdx];px+=Tt[0];py+=Tt[2];pz+=Tt[1];}
 // flattened sub-tik stream: offset by the parent tempmodel's ballistic position
 if(e._dyn){px+=e._dyn[0];py+=e._dyn[2];pz+=e._dyn[1];}
 let vx=dx*spd,vy=dy*spd,vz=dz*spd;
 // radialvelocity a b c (SetRadialVelocity, cg_commands.cpp:2739-2754 stores
 // velocity=[a,b,c-b]; SpawnTempModel :1511-1521): velocity = (spawnpos - origin) *
 // (a + (b + (c-b)*random)/len) - i.e. constant outward speed uniform in [b,c] plus a*len.
 // Runs AFTER the shape+offset placement and REPLACES forwardVelocity, then randvel ADDS
 // on top (:1523-1537) - it does not override randvel as the old code did.
 if(e.radialvelocity){const rvp=e.radialvelocity;
   const len=Math.hypot(mx,my,mz);           // radial vector from effect origin, MOHAA space
   if(len>1e-4){const fv=rvp[0]+(rvp[1]+(rvp[2]-rvp[1])*Math.random())/len;
     vx=mx*fv;vy=my*fv;vz=mz*fv;}
   else{vx=0;vy=0;vz=0;}}
 vx+=_rc(rv[0]);vy+=_rc(rv[1]);vz+=_rc(rv[2]);
 // per-component randomized angular velocity (SetAngularVelocity via SetBaseAndAmplitude,
 // cg_commands.cpp:2772-2795; per-particle draw at cg_tempmodels.cpp:1473-1479:
 // avelocity[i] = amp[i]*random + base[i]). Sprite roll spins by the ROLL component
 // (angles[2]); debris meshes tumble on all three.
 const avc=e.avelocity||[]; const av=[_rc(avc[0]),_rc(avc[1]),_rc(avc[2])];
 const aroll=av[2]||0;
 const bright=(col[0]+col[1]+col[2])>1.6;
 // varycolor (cg_tempmodels): darken each spawned particle's colour by 0 to -20% (engine does
 // this per channel; a single uniform factor is a close, cheap approximation). Sprite tint is
 // baked per-emitter at load, so this primarily affects the soft-blob fallback path.
 const _vc=(fl.indexOf('varycolor')>=0)?(0.8+Math.random()*0.2):1;
 // 3D MESH ORIENTATION: for debris chunks (e.mesh present) seed a per-particle Euler orientation
 // from the `angles` components (pitch,yaw,roll, in deg) via the engine's base+amplitude rule,
 // and a spin rate from `avelocity` (deg/s). With no angles, randomize so chunks aren't aligned.
 // metalchunk/metal have random angles + no avelocity -> fixed random orientation (no tumble).
 let _mrot=null,_mrate=null;
 if(e.mesh){
   const ag=e.angles, D=Math.PI/180;
   // ENGINE-EXACT SEED (SpawnTempModel, cg_tempmodels.cpp:1471-1478):
   //     p->cgd.angles[i] = angles_amplitude[i]*random() + m_spawnthing->cgd.angles[i]
   // With no `angles` in the block the spawnthing angles are ZERO - the tempmodel simply
   // inherits the tag/entity axis. The old code randomized ALL THREE components on a miss,
   // which sent mg42_gun / jeep_30cal's `tagspawnlinked tag_barrel (... model
   // models/fx/muzflash.tik randomroll ...)` card off in an arbitrary direction every shot
   // instead of firing straight down the barrel.
   _mrot=[(ag&&ag[0])?_rc(ag[0])*D:0,
          (ag&&ag[1])?_rc(ag[1])*D:0,
          (ag&&ag[2])?_rc(ag[2])*D:0];
   _mrate=[av[0]*D,av[1]*D,av[2]*D];
   // TAG AXIS (mrot[3]): a tempmodel spawned off a tag is oriented BY that tag.
   //  * tagspawnlinked sets T_WAVE (BeginTagSpawnLinked, cg_commands.cpp:3517) and the
   //    render pass composes the tempmodel's own axis with the tag's world axis every
   //    frame: MatrixMultiply(newEnt.axis, linked_axis, axis) (cg_tempmodels.cpp:1027-1039).
   //  * a plain tagspawn runs GetOrientation, which OVERWRITES the spawnthing angles with
   //    vectoangles(tag forward) - but only when the block set no `angles`
   //    (T_ANGLES, cg_commands.cpp:3483-3487); with explicit angles they are absolute.
   // The tag pose is sampled at spawn (as the tag ORIGIN already is a few lines above);
   // tempmodel lives are short (muzflash: 0.03-0.04s) so re-reading per frame is moot.
   if(e._tagIdx>=0&&curWorld&&(e.kind==='tagspawnlinked'||!e.angles)){
     const _R=curWorld.R[e._tagIdx];
     // curWorld.R is row-major MOHAA-space (world = R*local, see skin()), so the tag's
     // forward/left/up axes are its COLUMNS. That pose already carries the placement
     // rotation (composed at the skeleton root in worldFromPose), so nothing extra here.
     _mrot[3]=[[_R[0],_R[3],_R[6]],[_R[1],_R[4],_R[7]],[_R[2],_R[5],_R[8]]];
   } else if(EROT){
     // No tag to inherit from: AxisCopy(m_spawnthing->axis, p->ent.axis) (:1492-1493) leaves
     // the chunk/card on the ENTITY axis, so hand it the placement rotation's rows directly.
     _mrot[3]=[[EROT[0],EROT[3],EROT[6]],[EROT[1],EROT[4],EROT[7]],[EROT[2],EROT[5],EROT[8]]];
   }
   // T_RANDOMROLL (cg_tempmodels.cpp:601-602) randomizes ONLY angles[ROLL]; pitch and yaw are
   // never touched. It is driven by p.roll in stepParts (the 10 Hz physics-tick + shortest-arc
   // lerp already used by the sprite path) and read back in the draw step - NOT re-rolled at
   // draw time. Doing it at draw time made a PAUSED viewer churn the card every render frame,
   // which read as an endless muzzle-flash even with playback stopped and Loop off.
 }
 // BLEND MODE: prefer the sprite's real shader blendfunc (e.additive from sprites.shader) so
 // alpha sprites (water_g `blend`, vsssource smoke) composite translucently instead of stacking
 // additively to opaque white. Only guess from colour/alpha when no shader info exists.
 const _sa=(e.additive!=null)?e.additive
          :((e.sprite&&typeof e.sprite==='object'&&e.sprite.additive!=null)?e.sprite.additive:null);
 // FALLBACK (no shader info, _sa==null): only an HDR/over-bright COLOUR signals a glow
 // (corona/arc/flash). The old `||a0>0.45` clause forced ANY smoke with alpha>0.45 to be
 // additive, so dark smoke (e.g. color 0.2 0.2 0.2, alpha 0.5) whose sprite shader isn't in
 // the props index stacked additively and washed out to a featureless white orb. Smoke is
 // never additive; its darkness comes from a sub-1.0 colour tint, so `bright` is already
 // false for it. Shader-resolved effects (_sa!=null) are unaffected by this branch.
 const isAdd=(_sa!=null)?_sa:bright;
 // a `fadedelay` (even without the bare `fade` flag) means the artist wanted the
 // particle to fade rather than blink out at end-of-life - e.g. the electric arc's
 // short-lived inward sparks, which otherwise hard-pop in and out of existence.
 let doFade=(fl.indexOf('fade')>=0)||(e.fadedelay!=null);
 // SHADER ALPHA RULE (.spr sprites only; .tik sub-model particles keep the signed-off
 // billboard/mesh path): a shader whose blend does not read source alpha ignores the
 // emitter's alpha, fade and flickeralpha entirely - `blendfunc add` == GL_ONE GL_ONE, so
 // shaderRGBA[3] never reaches the framebuffer. corona_util/corona_reg/gren_boom/
 // air_explosion carry NO alphaGen and blend add (scripts/sprites.shader) - the blowtorch's
 // `color 1.5 .1 .1  alpha .7` corona is therefore FULL-STRENGTH WHITE in-game, and the
 // electric arcs are solid, not ghosted. e.srcalpha===false is set by the launcher when the
 // shader's src blend factor is not GL_SRC_ALPHA; the same solidity is assumed for the
 // no-shader-info additive fallback (HDR colour) so unresolved arc/corona shaders match.
 const _isMeshPart=!!(e.mesh||(e.basesize>0));
 let a0=(e.alpha!=null?e.alpha:1), _flick=(fl.indexOf('flickeralpha')>=0);
 if(!_isMeshPart && isAdd && (e.srcalpha===false || (_sa==null&&bright))){
   a0=1; doFade=false; _flick=false;
 }
 // per-particle life = base + random*amplitude (SetLife, cg_commands.cpp:2935-2952;
 // SpawnTempModel, cg_tempmodels.cpp:1412-1414)
 let _life=Math.max(0.05,(e.life||1)+(e.liferand?Math.random()*e.liferand:0));
 // SCALE (cg_tempmodels SpawnTempModel :1351-1358): when scalemin/scalemax are present the
 // engine flags T_RANDSCALE and seeds the particle's BASE scale to a random value in
 // [scalemin,scalemax], overriding `scale`; otherwise the base is `scale`. scalemin/scalemax
 // are a spawn range, NOT a per-frame clamp. scalerate then grows base as base*(1+rate*age)
 // in the draw step (TempModelRealtimeEffects :373-375). (Volumetric overrides this below.)
 let _hasrand=(e.scalemin!=null||e.scalemax!=null);
 let _sc=_hasrand?((e.scalemin||0)+Math.random()*Math.max(0,(e.scalemax||0)-(e.scalemin||0)))
                :((e.scale!=null?e.scale:1)+(e.scalerand?Math.random()*e.scalerand:0));
 let _scr=(e.scalerate||0),_smin=0,_smax=0,_vol=0;
 let _ax=ac[0],_ay=ac[2],_az=ac[1];                  // render-space accel (default = tik accel)
 // VOLUMETRIC SMOKE (MOHAA VSS, cg_volumetricsmoke.cpp) - engine-exact puff model:
 //  * initial radius: RANDSCALE ? random(scalemin,scalemax) : `scale` (SpawnVSSSource :690-693:
 //    fRadius = scale * vss_maxcount(10) * 0.1 = scale), clamped to 32 (:691-693, :750-756).
 //  * density: starts at 0 and RAMPS IN over a per-type window (VSS_ClampAlphaLife :1362-1371,
 //    density = lifeTime/maxlife * startAlpha while smokeType is still negative :572-596),
 //    where startAlpha = (0.85 + 0.15*random) * alpha (:747). Once ramped, density DECAYS at a
 //    per-type rate * fadeMult per second (:522-570) and the puff dies at density <= 0.06.
 //    `life` does NOT time out a VSS puff - it only multiplies the spawn count
 //    (fCountScale = cgd.life/1000, :730-738), which is why tanksmoke's `life 40` cloud
 //    still fades in ~1.5s in-game (greasefire decay 0.016/s x fadeMult 25 from
 //    `smokeparms 32 25 25`) while the viewer previously kept it for 40s.
 //  * radius growth: per-type rate * scaleMult per second, clamped [1,32] (:463-520).
 //  * accel[] is [typeInfo, fadeMult, scaleMult] (SpawnVSSSource :707-729); fadeMult<0.0001
 //    -> 1, scaleMult 0 -> 1; fire/greasefire typeInfo 0 -> 24.
 let _v=null;
 if(e.volumetric||fl.indexOf('volumetric')>=0){
   _vol=1;
   const _vt=_vssTypeIdx(e.model);
   let r0=_hasrand?_sc:(e.scale!=null?e.scale:1);
   r0=Math.max(1,Math.min(32,r0));
   // last-pass radius shrink (SpawnVSSSource :758-760): a burst pass entered with
   // 0 < iSmokeLeft < vss_maxcount spawns at radius * iSmokeLeft/10. bidx counts the
   // passes; iSmokeLeft at pass k = _vssISL - 10k.
   if(e._vssISL){const _rem=e._vssISL-bidx*10;
     if(_rem>0&&_rem<10)r0*=_rem/10;}
   _sc=r0; _scr=0; _smin=1; _smax=32;
   let fm=(ac[1]||0); if(fm<0.0001)fm=1;
   let sm=(ac[2]||0); if(!sm)sm=1;
   let ti=(ac[0]||0); if((_vt===9||_vt===10)&&ti===0)ti=24;
   _v={t:_vt, fm:fm, sm:sm, ti:ti, sa:(0.85+Math.random()*0.15)*a0, d:0,
       inMs:_VSS_IN[_vt]||100, ramped:0,
       // per-puff colour jitter: newColor = (0.7 + 0.3*random) * cgd.color
       // (SpawnVSSSource, cg_volumetricsmoke.cpp:762-766, vss_color default 1 :266)
       cj:(0.7+Math.random()*0.3),
       // per-puff 50/50 T_RANDOMROLL (:779-781) picks VSSSource.spr vs VSSSource2.spr
       // (AddVSSSources :1331-1340) - the two shaders are exact rotation MIRRORS
       // (scripts/sprites.shader: base +20/noise -20 vs base -20/noise +20), so half
       // the puffs churn one way and half the other. rs flips both tcmod signs.
       rs:(Math.random()<0.5?1:-1),
       // tcmod phase: shaderTime = (roll + cg.time - lifeTime)/1000 (:1342) where
       // lifeTime is the puff AGE counter - so the phase is FROZEN at the spawn
       // timestamp and only walks with roll (see stepParts). ph = spawn-time offset.
       ph:effT, rw:0};
   _ax=0;_ay=0;_az=0;                                // VSS ignores world accel entirely
   _life=600;                                        // death is density-driven, not life-driven
 }
 parts.push({ei:ei, x:px,y:py,z:pz, vx:vx,vy:vz,vz:vy, ax:_ax,ay:_ay,az:_az,
   sx:px,sy:py,sz:pz,                                // spawn anchor (swarm homing target)
   age:0,life:_life, sc:_sc,scr:_scr,
   smin:_smin,smax:_smax, vol:_vol, v:_v, sscale:(e.spritescale||1), sprtype:(e.sprite_type||null), lglow:!!e.lightglow,
   swarm:(e.swarm||null), clampvel:(e.clampvel||null),
   basesize:(e.basesize||0), baseaspect:(e.baseaspect||1), texw:(e.texw||0), texh:(e.texh||0),
   atest:(e.alphatest||null),
   r:col[0]*_vc,g:col[1]*_vc,b:col[2]*_vc,a0:a0, flick:_flick,
   // INITIAL ROLL: randomroll picks a fresh roll each frame in-game (here: random spawn roll);
   // otherwise honour the `angles` ROLL component (index 2) - e.g. electric_arc lightning1's
   // `angles 0 crandom -40 range 11 -30` gives roll in [-19,11] deg, the subtle arc tilt seen
   // in-game. pitch/yaw only matter for `spritegen oriented` shaders (world-fixed quad,
   // carried in opy below); camera-facing sprite types only ever show roll.
   roll:(fl.indexOf('randomroll')>=0?Math.random()*6.2832
          :((e.angles&&e.angles[2])?_rc(e.angles[2])*Math.PI/180:0)), aroll:aroll*Math.PI/180,
   rroll:(fl.indexOf('randomroll')>=0),   // T_RANDOMROLL: re-randomize roll EVERY frame (flicker)
   // SPRITE_ORIENTED (tr_sprite.c:96-99) builds its quad from the entity axes, i.e. the
   // tempmodel's full Euler angles, which avelocity spins on ALL THREE components (roll is
   // integrated in p.roll above; pitch/yaw here). Only kept for oriented sprites.
   opy:(e.sprite_type==='oriented')?[
        (e.angles&&e.angles[0])?_rc(e.angles[0])*Math.PI/180:0,
        (e.angles&&e.angles[1])?_rc(e.angles[1])*Math.PI/180:0]:null,
   opyr:(e.sprite_type==='oriented')?[av[0]*Math.PI/180,av[1]*Math.PI/180]:null,
   // T2_ALIGNSTRETCH scale2: `alignstretch <s>` sets scale2 (no arg -> 1.0) and implies
   // T_ALIGN (SetAlignStretch, cg_commands.cpp:1815-1821); bare `align` orients along
   // velocity WITHOUT any stretch. Stretch math is applied at draw time.
   stretch:(e.alignstretch||0),
   algn:(fl.indexOf('align')>=0||fl.indexOf('alignonce')>=0||(e.alignstretch||0)>0),
   collision:(fl.indexOf('collision')>=0), bounce:(e.bouncefactor!=null?e.bouncefactor:0.3),
   mrot:_mrot, mrate:_mrate,
   additive:isAdd, fade:doFade, fadedelay:(e.fadedelay||0), fadein:(e.fadein||0),
   fric:(e.friction||0)});
 if(parts.length>PMAX)parts.shift();
}
// VSS smoke-type registry (cg_volumetricsmoke.cpp cg_vsstypes, SpawnVSSSource :703-717):
// default gun bulletimpact bulletdirtimpact heavy steam mist smokegrenade grenade fire
// greasefire debris -> indexes 0..11.
const _VSS_NAMES=['default','gun','bulletimpact','bulletdirtimpact','heavy','steam','mist',
                  'smokegrenade','grenade','fire','greasefire','debris'];
function _vssTypeIdx(m){const n=(m||'').toLowerCase().replace(/"/g,'');
  // Unknown model refs (vsssource.spr etc.) are type 0 "default": SpawnVSSSource inits
  // iSmokeType = 0 and only overwrites it on an exact cg_vsstypes name match
  // (cg_volumetricsmoke.cpp:700-717). Type 0 has NO vertical adjustment and no buoyancy
  // (typeInfo is only read for types 9/10), so these puffs launch at the tik `velocity`
  // and simply bleed speed toward the wind at 4 u/s - the slower, uniform in-game stack
  // (shermansmoke). A greasefire fallback would add a phantom 24 u/s buoyancy climb.
  const k=_VSS_NAMES.indexOf(n);return k<0?0:k;}
// per-type density fade-IN window in ms (VSS_ClampAlphaLife callers, :572-596)
const _VSS_IN={0:100,1:100,2:100,3:150,4:200,5:50,6:600,7:800,8:600,9:1500,10:1500,11:50};
// per-type radius growth u/s (VSS_SourcePhysics :463-513); f(radius) for the staged types
function _vssGrow(t,r){
  switch(t){case 2:return 0.7;case 3:return 0.7;case 5:return 5.0;case 6:return 0.8;
    case 7:case 8:return (r>=24?0.4:1.6);
    case 9:case 10:return (r>=16?0.4:0.8);
    case 11:return 0.8;default:return 1.2;}}
// per-type density decay 1/s (VSS_SourcePhysics :522-570); f(density) for the staged types
function _vssDecay(t,d){
  switch(t){case 1:return 0.07;case 2:return 0.075;
    case 3:return (d>0.6?0.05:0.4);case 4:return 0.008;case 5:return 0.75;case 6:return 0.016;
    case 7:return 0.005;case 8:return (d>0.7?0.025:0.38);case 11:return 0.125;
    default:return (d>0.4?0.01:0.0075);}}          // default covers types 0, 9, 10
// T_SWARM runs on a FIXED tick because the engine's re-roll and homing terms are per-frame
// and unscaled (tr_ghost.cpp:131-152). 125 Hz is the classic Q3-engine com_maxfps value and
// puts the re-roll rate at 125/24 = 5.2/s for lightswarmers, inside the 5-6.5/s measured from
// in-game capture. Adjust here if it reads too frantic or too sluggish - it is the one number
// that sets the whizzing rate.
// UpdateSwarm runs once per RENDER frame (TempModelRealtimeEffects, cg_tempmodels.cpp:485,
// called ungated at :953), but the position integration and the parentOrigin write live in
// TempModelPhysics, which is gated to cg_effect_physicsrate - default 10, i.e. 10 Hz (:237,
// :959). That 12.5:1 ratio is the whole effect: ~12 unscaled +-delta nudges pile into velocity
// while the position stays frozen, so each physics step launches the particle with a velocity
// far larger than swarmmaxspeed. 125 Hz puts the re-roll at 125/24 = 5.2/s, matching the
// 5-6.5/s measured from in-game capture.
const SWARM_TICK_HZ=125, SWARM_MAX_TICKS=16, SWARM_PHYS_HZ=10;
function stepParts(dt){
 // CONTINUOUS-VSS LIVE-PUFF PRUNE (fx_fattysmoke lag): a continuous volumetric emitter reaches
 // a steady state of ~ spawnrate * life live 3D puffs (fattysmoke: 10 * 11 = ~110), each running
 // per-frame growth + 4Hz O(n^2) repulsion + a large multi-layer radial composite (scale 7,
 // radius 40). The native engine eats that from its 1024-source pool (vss_maxvisible,
 // cg_volumetricsmoke.cpp:176), but the Canvas-2D path bogs down once the cloud fills in past
 // ~10s. Rather than thin the spawn (which visibly sparsens the whole column), enforce a hard
 // cap on simultaneously-live VSS puffs and PRUNE THE OLDEST when over it: puffs are pushed in
 // spawn order, so the oldest sit at the front of `parts`, and for rising smoke those are the
 // highest, most-faded, least-noticeable puffs. Full density is kept at the source; only the
 // dissipating top is trimmed. Non-VSS particles are never touched. cg_effectdetail thins VSS
 // the same way on weak hardware (:734), so this is faithful to how the game itself sheds load.
 const VSS_LIVE_CAP=100;                       // max simultaneous volumetric puffs (canvas budget)
 {
   let _vn=0; for(let i=0;i<parts.length;i++) if(parts[i].vol) _vn++;
   if(_vn>VSS_LIVE_CAP){
     let _drop=_vn-VSS_LIVE_CAP;               // remove this many oldest (front-most) VSS puffs
     for(let i=0;i<parts.length && _drop>0;){
       if(parts[i].vol){parts.splice(i,1);_drop--;} else i++;
     }
   }
 }
 // re-fire the whole effect every FX_REFIRE; each instance lives FX_SCHEDLEN, so lingering
 // emitters (smoke) from one instance overlap the next - giving continuous smoke + the in-game
 // double-corona cadence rather than a single 2s play-through.
 if(_hasSched){
   if(!_triggers.length || (effT-_triggers[_triggers.length-1].t0)>=FX_REFIRE-1e-6)
     _triggers.push({t0:effT, acc:EM.map(()=>0)});
   while(_triggers.length && (effT-_triggers[0].t0)>FX_SCHEDLEN+0.05) _triggers.shift();
 }
 // anim-triggered sub-tik streams (e.g. gas_mushroom_cloud's `cloud` emitter riding a
 // spawned tempmodel): run for `subdur` seconds after their trigger, spawning along the
 // parent's vertical ballistic carrier path so the column climbs as it puffs.
 for(let i=animStreams.length-1;i>=0;i--){const st=animStreams[i],e=EM[st.ei];
   const age=effT-st.t0;
   if(age>st.dur+0.02){animStreams.splice(i,1);continue;}
   const rate=Math.min(120,(e.spawnrate||10));
   st.acc+=dt*rate;
   if(st.acc>=1){const cv=e.carrier||[0,0,0],ca=e.carrieracc||[0,0,0];
     e._dyn=[cv[0]*age+0.5*ca[0]*age*age,cv[1]*age+0.5*ca[1]*age*age,cv[2]*age+0.5*ca[2]*age*age];
     while(st.acc>=1){st.acc-=1;spawnParticle(st.ei);}
     e._dyn=null;}}
 for(let ei=0;ei<EM.length;ei++){const e=EM[ei];
   // anim-triggered one-shots/streams fire from playback triggers (fireAnimAt), never here
   if(e.animfx)continue;
   // CONTINUOUS/STREAM RATE: a continuous emitter spawns one tempmodel per interval at exactly
   // `spawnrate`/sec (cg_commands SetSpawnRate: spawnRate=(1/value)*1000 ms; UpdateEmitter calls
   // SpawnEffect(1,...) each interval). `count` does NOT inflate it - count is the per-burst size
   // for originspawn / circle distribution (handled on schedule ON-crossings below). Only fall
   // back to count/life when an emitter declares no spawnrate. The old max(2,count/life) floor
   // made `spawnrate 1` flashes fire ~7x too often and forced low-rate arcs to 2/s.
   const _isVol=(e.volumetric||(e.flags&&e.flags.indexOf('volumetric')>=0));
   const _sr=(e.spawnrate||0);
   // spawnrate is uncapped in-engine (UpdateEmitter, cg_commands.cpp:4968-5025 spawns one per
   // interval however short); the old 120/s ceiling starved blowtorch_cutter's 300/s spark
   // fountain into a sparse dribble. 300/s under the PMAX budget is safe for the canvas.
   const rate=Math.min(300, _sr>0?_sr:Math.max(_isVol?0.1:1,(e.count||0)/Math.max(e.life||1,0.1)));
   const sched=EMSCHED[ei];
   if(!sched){                                   // continuous emitter: spawn as before
     // runtime on/off: `startoff` emitters wait for an anim's emitteron; emitteroff
     // silences a running one (existing particles live out their own lives)
     if(!emActive[ei])continue;
     // commanddelay: hold emission until the delay elapses after effect start (e.g.
     // aircraft_explosion `flash` waits 0.2s). Continuous emitters don't re-fire here, so this
     // is a one-time start offset relative to load/reset.
     if(effT<(e.startdelay||0)){continue;}
     spawnAcc[ei]+=dt*rate;
     // a VSS spawn event routes through spawnBurst so the engine's count*life puff
     // multiplier applies (norbigstacksmoke's dense column at spawnrate 0.5, life 30).
     while(spawnAcc[ei]>=1){spawnAcc[ei]-=1;
       if(_isVol)spawnBurst(ei,(e.count||1)); else spawnParticle(ei);}
     continue;}
   // timed emitter: run its windows against EACH live instance. Fire a count-burst on every
   // ON crossing (so zero-width corona/inward-spark toggles still emit) and stream inside any
   // window with real width (the initial spark burst, the lingering smoke).
   for(const tr of _triggers){const age=effT-tr.t0, agePrev=age-dt; let active=false;
     for(const iv of sched){const on=iv[0],off=iv[1];
       if(agePrev<on && on<=age) spawnBurst(ei,Math.max(1,Math.round(e.count||1)));
       if(off>on && age>=on && age<off) active=true;}
     if(active){tr.acc[ei]+=dt*rate;
       while(tr.acc[ei]>=1){tr.acc[ei]-=1;
         if(_isVol)spawnBurst(ei,(e.count||1)); else spawnParticle(ei);}}}
 }
 // VSS INTER-PUFF REPULSION (VSS_AddRepulsion, cg_volumetricsmoke.cpp:76-135): every pair of
 // puffs pushes apart with force (rA+rB)*0.03*fSum, where each half of fSum follows a falloff
 // curve of normalized gap f=(dist-rOther)/rSelf - 1.2887 at contact, 0 beyond f>1.49 - and
 // counts 1.0 when fully overlapped. Forces are recomputed at vss_repulsion_fps = 4 Hz over
 // all pairs (VSS_CalcRepulsionForces :892-940, cleared each pass) and integrated as
 // velocity += repulsion*ftime each physics tick (:291-293). THE FORCE SCALES WITH RADIUS:
 // this is why scale/scalemin/scalemax directly control how far a smoke column spreads -
 // radius-24 puffs shove each other into a wide expanding cloud while radius-3 puffs rise as
 // a thin pillar (short_grey_fat_trans scale sweep), and tanksmoke reads conical because its
 // puffs grow as they rise, so the spread force increases downstream.
 _repAcc+=dt;
 if(_repAcc>=0.25){_repAcc=0;
   const vp=[];for(const p of parts)if(p.vol){p.rpx=0;p.rpy=0;p.rpz=0;vp.push(p);}
   for(let ai=0;ai<vp.length;ai++){const A=vp[ai];
     for(let bi=ai+1;bi<vp.length;bi++){const B=vp[bi];
       let ux=A.x-B.x,uy=A.y-B.y,uz=A.z-B.z;
       if(ux===0&&uy===0&&uz===0){
         // coincident puffs: unscaled random push (engine :83-88)
         ux=Math.random()*2-1;uy=Math.random()*2-1;uz=Math.random()*2-1;
         A.rpx+=ux;A.rpy+=uy;A.rpz+=uz;B.rpx-=ux;B.rpy-=uy;B.rpz-=uz;continue;}
       const d=Math.hypot(ux,uy,uz);
       if(d>(A.sc+B.sc)*2.5)continue;            // beyond both force cutoffs
       ux/=d;uy/=d;uz/=d;
       let fF,f=d-B.sc;
       if(f>0){f/=A.sc;if(f>1.49)f=0;else f=f*(f*0.0161-0.3104)+1.2887;if(f<0)f*=1.1;fF=f;}
       else fF=1;
       f=d-A.sc;
       if(f>0){f/=B.sc;if(f>1.49)f=0;else f=f*(f*0.0161-0.3104)+1.2887;if(f<0)f*=1.1;fF+=f;}
       else fF+=1;
       if(fF>-0.05&&fF<0.05)continue;
       // Horizontal: 0.09 = engine 0.03 (VSS_AddRepulsion, cg_volumetricsmoke.cpp:130) x3,
       // calibrated against in-game footage - lateral spread must overcome the 4 u/s
       // wind-dampen pin, and in-game the origin de-crowds after ~5 puffs where the
       // literal constant took ~10+ in the canvas sim.
       // Vertical: engine-exact 0.03. In a rising column the pair vectors are mostly
       // vertical, so a boosted constant chain-pushes each puff's climb and the stack ran
       // ~1.25x faster than in-game (shermansmoke side-by-side); onset calibration only
       // concerns the lateral axes. Falloff curve and radius scaling stay engine-exact.
       const sh=(A.sc+B.sc)*0.09*fF, sv=(A.sc+B.sc)*0.03*fF;
       A.rpx+=ux*sh;A.rpy+=uy*sv;A.rpz+=uz*sh;
       B.rpx-=ux*sh;B.rpy-=uy*sv;B.rpz-=uz*sh;}}}
 for(let i=parts.length-1;i>=0;i--){const p=parts[i];p.age+=dt;
   if(p.age>=p.life){parts.splice(i,1);continue;}
   if(p.swarm){
     // T_SWARM. Particle::Update (tr_ghost.cpp:131-152) runs, ONCE PER ENGINE FRAME:
     //     if (!(rand() % m_swarmfrequency)) { velocity[k] = crandom() * m_maxspeed; }
     //     velocity[k] += (parentOrigin[k] > position[k]) ? +delta : -delta;
     // i.e. a 1-in-freq chance of a HARD re-roll of all three components, then a bang-bang
     // pull of constant magnitude toward the spawn anchor. Operand order is fixed by the
     // writer at cg_testemitter.cpp:1411 - `swarm %i %g %g` = freq, maxspeed, delta - which
     // is NOT the order tr_ghost.cpp:1192-1194 serialises internally.
     //
     // BOTH terms are per-FRAME and neither is scaled by ftime, so the engine's behaviour is
     // tied to its framerate. Driving them off the viewer's rAF delta (the previous approach)
     // therefore ran the whole effect at whatever rate the browser happened to paint: at 60fps
     // that is 60/24 = 2.5 re-rolls/s against the ~5-6.5/s measured off in-game capture, so the
     // swarmers drifted smoothly instead of whizzing, and the homing nudge came in at roughly
     // half strength, letting them wander too far off the anchor. Run it on a fixed accumulator
     // instead: rate now matches the engine and is identical on any display.
     const fq=Math.max(1,p.swarm[0]|0), ms=p.swarm[1], dl=p.swarm[2];
     // The homing TARGET is not the spawn anchor. For a swarm tempmodel that is not
     // T_PARENTLINK/T_HARDLINK - and lightswarmers is neither, its flags are varycolor/fade/
     // randomroll/swarm - cg_tempmodels.cpp:585-586 does:
     //     p->cgd.parentOrigin = p->cgd.velocity + p->cgd.accel * ftime * scale;
     // assigning a VELOCITY into the position field it just compared against. Almost certainly
     // an engine bug, but it is the shipped behaviour and it is the entire character of the
     // effect: the "anchor" is re-pointed every physics step to a small vector near the origin,
     // so the bang-bang term drives long one-way runs that only reverse when the particle
     // overshoots it. Homing to the true spawn point instead - what this did before - binds the
     // particle inside its own spawn sphere, which is the stationary wobble.
     // px/py/pz is the PHYSICS origin (p->cgd.origin, stepped at 10Hz); ox/oy/oz is the
     // previous one (p->lastEnt.origin). p.x/y/z is the RENDER origin and is derived from
     // them by interpolation at the bottom - never stepped directly.
     if(p.po===undefined){p.po=[0,0,0];
       p.px=p.x;p.py=p.y;p.pz=p.z; p.ox=p.x;p.oy=p.y;p.oz=p.z;}
     p.swacc=(p.swacc||0)+dt; p.phacc=(p.phacc||0)+dt;
     let nt=Math.floor(p.swacc*SWARM_TICK_HZ); p.swacc-=nt/SWARM_TICK_HZ;
     if(nt>SWARM_MAX_TICKS)nt=SWARM_MAX_TICKS;      // never catch up across a tab stall
     const pdt=1/SWARM_PHYS_HZ;
     const physStep=()=>{p.ox=p.px;p.oy=p.py;p.oz=p.pz;
       p.px+=p.vx*pdt; p.py+=p.vy*pdt; p.pz+=p.vz*pdt;
       p.po[0]=p.vx; p.po[1]=p.vy; p.po[2]=p.vz;};   // :585-586, accel is 0 for these
     for(let k=0;k<nt;k++){
       if(Math.random()*fq<1){                      // rand() % freq == 0
         p.vx=(Math.random()*2-1)*ms; p.vy=(Math.random()*2-1)*ms; p.vz=(Math.random()*2-1)*ms;}
       // physics origin and parentOrigin are BOTH frozen between physics steps, so the sign of
       // each comparison holds for the whole window and the nudges accumulate coherently.
       p.vx+=(p.px<p.po[0]? dl:-dl); p.vy+=(p.py<p.po[1]? dl:-dl); p.vz+=(p.pz<p.po[2]? dl:-dl);
       if(p.phacc>=pdt){p.phacc-=pdt;physStep();}
     }
     let guard=0;
     while(p.phacc>=pdt&&guard++<4){p.phacc-=pdt;physStep();}   // viewer slower than 10Hz
     // LerpTempModel (:842-847) interpolates the RENDERED origin between the last two physics
     // origins for T_SWARM, exactly as it does for T2_MOVE/T2_ACCEL:
     //     newEnt->origin[i] = lastEnt.origin[i] + frac * (ent.origin[i] - lastEnt.origin[i])
     // with frac = (cg.time - lastPhysicsTime) / physics_rate, clamped to 0..1 (:981-988).
     // Without it the particle is drawn only at 10Hz and jumps its whole 100ms of travel in one
     // frame - at these velocities that is tens of units per hop, which reads as the sprite
     // blinking in and out of existence rather than flying.
     const frac=Math.max(0,Math.min(1,p.phacc*SWARM_PHYS_HZ));
     p.x=p.ox+(p.px-p.ox)*frac; p.y=p.oy+(p.py-p.oy)*frac; p.z=p.oz+(p.pz-p.oz)*frac;
   } else {
     p.vx+=p.ax*dt;p.vy+=p.ay*dt;p.vz+=p.az*dt;
   }
   if(p.vol&&p.v){
     const V=p.v;
     // VSS physics (VSS_SourcePhysics, cg_volumetricsmoke.cpp):
     // 0) inter-puff repulsion integrates into velocity FIRST (:291-293);
     p.vx+=(p.rpx||0)*dt; p.vy+=(p.rpy||0)*dt; p.vz+=(p.rpz||0)*dt;
     // 1) every velocity component converges toward the WIND - which is NOT zero:
     //    vss_wind_x=8, vss_wind_y=4, vss_wind_z=2 by default (cg_volumetricsmoke.cpp:
     //    268-271) - at vss_movement_dampen = 4 u/s (:365-405; vss_wind_strength only
     //    applies to negative winds). This is what makes every in-game plume drift
     //    diagonally AND what breaks the straight-vertical streamline: the curved path
     //    de-collinearizes the puffs so inter-puff repulsion gains perpendicular
     //    components and the column expands outward, scaling with puff radius.
     //    MOHAA (x,y,z) -> render (x,z,y): wind targets are vx->8, vz->4, vy->2.
     const d=4*dt;
     p.vx=(p.vx>8?Math.max(8,p.vx-d):Math.min(8,p.vx+d));
     p.vz=(p.vz>4?Math.max(4,p.vz-d):Math.min(4,p.vz+d));
     p.vy=(p.vy>2?Math.max(2,p.vy-d):Math.min(2,p.vy+d));
     // 2) per-type vertical behaviour (:407-450): steam rises hard, heavy/mist/smokegrenade
     //    settle, debris plummets, fire/greasefire ride the decaying typeInfo buoyancy
     //    (typeInfo -= 4%/s toward a floor of 10, :433-443).
     switch(V.t){
       case 3: if(p.vy>-8)  p.vy-=dt*8;   break;
       case 4: if(p.vy>-5)  p.vy-=dt*3;   break;
       case 5: if(p.vy<256) p.vy+=dt*40;  break;
       case 6: if(p.vy>-25) p.vy-=dt*10;  break;
       case 7: if(p.vy>-10) p.vy-=dt*4;   break;
       case 9: case 10:
         if(V.ti>8){ if(p.vy<V.ti)p.vy=Math.min(V.ti,p.vy+dt*V.ti);
                     V.ti-=dt*V.ti*0.04; if(V.ti<10)V.ti=10; }
         break;
       case 11: if(p.vy>-800) p.vy-=dt*300; break;
     }
     // 3) radius growth per type * scaleMult, clamped [1,32] (:463-520)
     p.sc=Math.max(1,Math.min(32,p.sc+dt*_vssGrow(V.t,p.sc)*V.sm));
     // 4) density: ramp in over inMs to startAlpha (VSS_ClampAlphaLife :1362-1371), then
     //    decay per type * fadeMult and die at <= 0.06 (:522-570)
     const ms=p.age*1000;
     if(!V.ramped){
       if(ms>=V.inMs){V.ramped=1;V.d=V.sa;}
       else V.d=(ms/V.inMs)*V.sa;
     } else {
       V.d-=dt*_vssDecay(V.t,V.d)*V.fm;
       if(V.d<=0.06){parts.splice(i,1);continue;}
     }
     // 5) per-puff tcmod ROLL WALK (AddVSSSources, cg_volumetricsmoke.cpp:1312-1329):
     //    roll += frame; per axis j = int(frame*|vel_i|*0.03), softened past frame
     //    (j = frame + (j-frame)*0.75) and capped at 2*frame, then roll -= j. Net
     //    phase speed = 1 - sum(j)/frame in [-5,+1]x realtime: near-still puffs'
     //    patterns crawl forward, fast movers spin their pattern backward.
     {const _dm=dt*1000; let _sj=0; const _vv=[p.vx,p.vy,p.vz];
      for(let _k=0;_k<3;_k++){let _j=Math.floor(_dm*Math.abs(_vv[_k])*0.03);
        if(_j>_dm)_j=_dm+(_j-_dm)*0.75; if(_j>2*_dm)_j=2*_dm; _sj+=_j;}
      V.rw+=(_dm-_sj)/1000;}
   }
   // T2_FRICTION (TempModelPhysics, cg_tempmodels.cpp:650-658): per PHYSICS STEP velocity
   // is scaled by (1 - ftime*friction), zeroed if the factor goes <= 0 - and tempmodel
   // physics steps at 10 Hz (ftime = 0.1), so per second this compounds to
   // (1 - friction/10)^10 (stated verbatim in the SetFriction docstring, cg_commands.cpp:
   // 253). NEGATIVE friction is a growth term: electrical_fire sparks1b `friction -40`
   // multiplies velocity 5x per 0.1s step (~9.7e6x per second) - those sparks are meant to
   // explode off-scene within a few frames. The old per-render-frame linear (1 - f*dt)
   // compounded far faster than the engine at high magnitudes (1.667x per 16.7ms frame ->
   // ~4.6e13x per second), so they hit absurd speeds instantly and their capped-length
   // stretch streaks lingered as full-screen vertical bars. pow(base, dt*10) reproduces
   // the engine's step compounding at any render framerate.
   // VSS puffs skip friction entirely - VSS_SourcePhysics has no friction term
   // (cg_volumetricsmoke.cpp:281-460); only wind-dampen, repulsion, and per-type rates.
   if(p.fric&&!p.swarm&&!p.vol){
     const base=1-p.fric*0.1;
     if(base<=0){p.vx=0;p.vy=0;p.vz=0;}
     else{const f=Math.pow(base,dt*10);p.vx*=f;p.vy*=f;p.vz*=f;}}
   // clampvel minX maxX minY maxY minZ maxZ (T2_CLAMP_VEL, cg_tempmodels.cpp:656-660),
   // applied after accel/friction each tick. MOHAA (x,y,z) -> render (x,z,y): the tik's
   // Z clamp bounds the render-Y (vertical) component - e.g. bombdirt's cloud
   // `clampvel ... -175 9999` stops the accel -600 plunge at 175 u/s down.
   if(p.clampvel){const c=p.clampvel;
     if(p.vx<c[0])p.vx=c[0]; else if(p.vx>c[1])p.vx=c[1];
     if(p.vz<c[2])p.vz=c[2]; else if(p.vz>c[3])p.vz=c[3];
     if(p.vy<c[4])p.vy=c[4]; else if(p.vy>c[5])p.vy=c[5];}
   if(!p.swarm){p.x+=p.vx*dt;p.y+=p.vy*dt;p.z+=p.vz*dt;}   // swarm integrated per fixed tick above
   // T_RANDOMROLL (cg_tempmodels.cpp:601-602): every physics tick sets angles[ROLL] =
   // random()*360, and the engine runs TempModelPhysics at cg_effect_physicsrate = 10 Hz
   // (every 100ms; :237,959-968). BUT between ticks the render LERPS the axis matrix from the
   // previous roll to the new one (:854-859, newEnt.axis = lastEnt.axis + frac*(ent.axis -
   // lastEnt.axis)). Extracting the roll from that component-wise matrix lerp traces the
   // SHORTEST ARC old->new, so the sprite ROLLS its way to each new random angle rather than
   // snapping - wild but smooth. Reproduce: pick a new random target every 100ms and
   // shortest-arc interpolate p.roll from the previous target to it across the window.
   if(p.rroll){
     if(p.rollT===undefined){ p.rollF=p.roll; p.rollT=Math.random()*6.2832; p.rrt=0; }
     p.rrt+=dt;
     if(p.rrt>=0.1){ p.rrt-=0.1; p.rollF=p.rollT; p.rollT=Math.random()*6.2832; }
     let _d=(p.rollT-p.rollF)%6.2832;                // shortest signed delta in (-2pi,2pi)
     if(_d>Math.PI)_d-=6.2832; else if(_d<-Math.PI)_d+=6.2832;   // -> [-pi,pi]
     p.roll=p.rollF+_d*(p.rrt/0.1);                  // lerp across the 100ms tick
   } else {
     p.roll+=p.aroll*dt;
   }
   // invisible ground plane for `collision` particles (welding sparks1a). It sits at the
   // GRID plane (cy0 - rad*0.55), the visible floor under the emitter - NOT at the origin -
   // so sparks fall a realistic distance and bounce off the floor instead of spraying
   // horizontally straight out of the emitter gem.
   if(p.collision){ const fy=groundY;
     if(p.y<fy && p.vy<0){ p.y=fy; p.vy=-p.vy*p.bounce; p.vx*=0.7; p.vz*=0.7; } }}
}
// live volumetric puff count, for the engine-like source-pool saturation cap
function _volAlive(){let n=0;for(const p of parts)if(p.vol)n++;return n;}
const VOLMAX=460;
let _repAcc=0.25;   // VSS repulsion refresh timer (vss_repulsion_fps = 4 Hz); starts due
// ---- particle occlusion vs the opaque mesh (2D path) -----------------------------
// The Canvas-2D fallback paints particles OVER the model with no z-buffer, so tag-anchored
// sparks/smoke behind the barrel or gun-shield showed THROUGH the mesh (flak88_d smoke visible
// on top of the plate). The engine draws tempmodels depth-TESTED against opaque world/model
// geometry, so a puff behind the shield is occluded. Emulate cheaply: once per frame rasterise
// the drawn mesh triangles into a COARSE min-depth grid (camera-space depth per cell), then in
// drawParticles skip any particle whose depth is clearly greater (further) than the mesh depth
// at its screen cell. Only built when the mesh is actually drawn - +dontdraw effect dummies,
// or Texture/Mesh/Wire all off, leave the grid null so nothing is occluded (pure-effect models
// keep every particle, as before). GL path has a real depth buffer and never uses this.
const _OCC_CELL=10;                 // screen px per depth cell (coarse = cheap, ~120x80 grid)
let _occW=0,_occH=0,_occZ=null;     // min mesh camera-depth per cell (Float32Array), null=off
function _buildOcclusionDepth(){
  _occZ=null;
  if(GLR)return;                                            // GL path: real depth test, skip
  if(DATA.dontdraw||!(view.tex||view.mesh||view.wire))return;  // mesh not drawn -> no occluder
  const V=model,T=DATA.tris; if(!V||!T||!T.length)return;
  const gw=Math.max(1,Math.ceil(W/_OCC_CELL)), gh=Math.max(1,Math.ceil(H/_OCC_CELL));
  const z=new Float32Array(gw*gh); z.fill(Infinity);
  const cache={};
  const pr=(i)=>{let c=cache[i];if(c)return c;c=project([V[i*3],V[i*3+1],V[i*3+2]]);cache[i]=c;return c;};
  const sr=DATA.surfRanges;
  for(let t=0;t<T.length;t++){
    const tr=T[t],a=pr(tr[0]),b=pr(tr[1]),c=pr(tr[2]);
    if(a[2]<=0||b[2]<=0||c[2]<=0)continue;                  // behind camera - not an occluder
    // skip surfaces the mesh loop itself skips: +nodraw and two-sided FX (autosprite/additive)
    // don't act as solid occluders (they're the fire/arc cards, not the gun shell).
    let si=0;for(let q=0;q<sr.length;q++){if(t>=sr[q].start&&t<sr[q].end){si=q;break;}}
    if(hiddenSurf.has(si))continue;
    const tex=LTEX[si];
    if(tex&&(tex.additive||tex.autosprite||tex.pulseOnly))continue;
    // conservative bbox fill at cell resolution with the triangle's MAX depth (so a particle is
    // only culled when it is behind the FARTHEST corner of a covering tri - avoids z-fighting
    // haloes at silhouette edges while still hiding puffs well behind the plate).
    const zt=Math.max(a[2],b[2],c[2]);
    let x0=Math.min(a[0],b[0],c[0]),x1=Math.max(a[0],b[0],c[0]);
    let y0=Math.min(a[1],b[1],c[1]),y1=Math.max(a[1],b[1],c[1]);
    let cx0=Math.max(0,Math.floor(x0/_OCC_CELL)), cx1=Math.min(gw-1,Math.floor(x1/_OCC_CELL));
    let cy0=Math.max(0,Math.floor(y0/_OCC_CELL)), cy1=Math.min(gh-1,Math.floor(y1/_OCC_CELL));
    for(let gy=cy0;gy<=cy1;gy++)for(let gx=cx0;gx<=cx1;gx++){
      const idx=gy*gw+gx; if(zt<z[idx])z[idx]=zt;
    }
  }
  _occW=gw;_occH=gh;_occZ=z;
}
// true if a particle at screen (sx,sy) with camera-depth zc is hidden behind the opaque mesh.
function _occluded(sx,sy,zc){
  if(!_occZ)return false;
  const gx=Math.floor(sx/_OCC_CELL), gy=Math.floor(sy/_OCC_CELL);
  if(gx<0||gy<0||gx>=_occW||gy>=_occH)return false;
  const mz=_occZ[gy*_occW+gx];
  // a small bias (2u) keeps sprites sitting ON the surface (muzzle at the barrel tip) from
  // flickering out; only clearly-behind particles are dropped.
  return isFinite(mz) && zc > mz+2;
}
function drawParticles(){
 if(!parts.length)return;
 const arr=[];
 // NEAR-CLIP CULL: sp[2] is camera-space depth in world units. Requiring only >0 let
 // hyper-fast sparks (electrical_fire sparks1a/1b under negative friction) skim within
 // ~0-2u of the camera plane, where px-per-unit explodes - their streaks pinned at the
 // screen cap and the direction sample crossed behind the camera, so they drew as giant
 // camera-facing vertical bars. The engine's near plane (r_znear, ~4u) culls that zone
 // outright; 6u gives a small safety margin for the streak's own extent.
 for(const p of parts){const sp=project([p.x,p.y,p.z]);
   if(sp[2]>6 && !_occluded(sp[0],sp[1],sp[2]))arr.push([sp,p]);}   // drop puffs behind the mesh
 arr.sort((a,b)=>b[0][2]-a[0][2]);   // far first for correct blending
 ctx.save();
 for(const it of arr){const sp=it[0],p=it[1];
   const t=p.age/p.life;
   // scalerate grows the BASE scale multiplicatively: scale(age)=base*(1+rate*age), from the
   // engine's per-frame `ent.scale += cgd.scale*cgd.scaleRate*dt` integrated over age. The old
   // additive base+rate*age over-inflated short-lived rate-driven sprites - electric_arc
   // lightning2 (base .10 rate 5, life .09) ballooned to ~.55 and read at lightning1's .30
   // instead of staying ~1/3. Volumetric (VSS) keeps the hand-tuned additive radius growth.
   // VSS radius growth now runs in stepParts (per-type engine rates); p.sc IS the radius.
   // SCALE OVER TIME (TempModelRealtimeEffects, cg_tempmodels.cpp:373-374):
   //   ent.scale += cgd.scale * (scaleRate * ftime)   -> scale = base * (1 + scaleRate*age)
   // scaleRate grows the sprite WITHOUT BOUND for its whole life; scalemin/scalemax are ONLY
   // the T_RANDSCALE spawn-range for the BASE scale (SpawnTempModel :1351-1358), NOT a
   // runtime cap. The old draw clamped the GROWN size to scalemax, which pinned every
   // scaled sprite at its spawn size - mortar_dirt/explosion_mine sprites (dirtplume
   // scalemax .6 + scalerate .2, mortar_dirthit scale .0625 + scalerate 16) froze tiny
   // instead of blooming to full size. The base random scale is already baked into p.sc at
   // spawn, so no clamp belongs here.
   let scl=p.vol?p.sc:(p.sc*(1+p.scr*p.age));
   // restore spawn-range clamp for NON-VSS scaled particles (was removed for the mortar
   // sprite fix; harmless when smin/smax are 0, but restores mesh-shrapnel sizing if those
   // pieces carry a nonzero spawn range).
   if(!p.vol){ if(p.smax){scl=Math.min(scl,p.smax);} if(p.smin){scl=Math.max(scl,p.smin);} }
   // FADE (TempModelRealtimeEffects, cg_tempmodels.cpp:346-357):
   //   fade = 1 - (aliveTime - fadedelay)/(life - fadedelay), clamped [0,1]
   // fadedelay is ABSOLUTE SECONDS (SetFadeDelay stores GetFloat*1000 ms, cg_commands.cpp:
   // 2495-2503), NOT a fraction of life. The old fraction formula went NEGATIVE for any
   // fadedelay >= 1s, so `fadedelay 1.5` particles (gren_exp ring smoke, bombdirt/mine
   // clouds + stonechip/dirt pieces, mortar dirtplumes, dustcloud puffs) computed a <= 0
   // from birth and were completely invisible.
   let a=p.a0;
   if(p.fade){
     const den=Math.max(0.001,p.life-p.fadedelay);
     let fd=1-(p.age-p.fadedelay)/den;
     if(fd>1)fd=1; if(fd<0)fd=0;
     a=p.a0*fd;
   }
   // FADEIN (cg_tempmodels.cpp:362-366 + :459-461): while age < fadeintime the alpha is
   // color[3] * (age/fadeintime * alpha) and OVERRIDES the fadeout - higgins/gren_exp ring
   // puffs (`fadein 1`/`1.5`) build up softly instead of popping in at full strength.
   if(p.fadein>0 && p.age<p.fadein) a=p.a0*(p.age/p.fadein);
   // FLICKERALPHA (T_FLICKERALPHA, cg_tempmodels.cpp:463-471): random per-frame alpha.
   if(p.flick) a*=Math.random();
   if(p.vol&&p.v){
     // VSS density computed in stepParts per cg_volumetricsmoke (ramp-in, per-type decay).
     a=p.v.d;
   }
   if(a<=0.01)continue;
   // 3D DEBRIS CHUNK: render the real sub-model geometry, rotated to this particle's orientation
   // (cg_tempmodels: each tempmodel is a full refEntity with ent.axis = AnglesToAxis(angles)).
   // Verts are MOHAA model space (Z-up), centred; rotate in MOHAA space, convert to render
   // (x,z,y), place at the particle, project, then paint depth-sorted flat-shaded facets.
   const M3=EM[p.ei].mesh;
   if(M3&&p.mrot){
     // FIRST-PLAY WHITE FLASH FIX: a textured debris chunk (bh_wood_piece / bh_stone_piece,
     // splinter.skd) whose skin data-url hasn't decoded yet on the very first play would fall
     // through to the flat-colour fallback below; with the debris color 1 1 1 that painted a
     // one-frame WHITE chunk. If the texture is merely PENDING (exists, not yet loaded), skip
     // drawing this frame entirely - the onload handler calls draw() the instant it is ready,
     // so the chunk simply appears textured a frame later instead of flashing white. Genuinely
     // untextured chunks (no M3.tex) still use the flat fallback as before.
     if(_meshTexPending(p.ei)){ctx.globalAlpha=1;continue;}
     const pa=p.mrot[0]+p.mrate[0]*p.age, ya=p.mrot[1]+p.mrate[1]*p.age,
           // randomroll: p.roll is maintained by stepParts, which only runs while the effect
           // clock advances - so a frozen/paused particle holds its orientation.
           ra=p.rroll?p.roll:(p.mrot[2]+p.mrate[2]*p.age);
     const cp=Math.cos(pa),sp_=Math.sin(pa),cy=Math.cos(ya),sy=Math.sin(ya),cr=Math.cos(ra),sr=Math.sin(ra);
     // AnglesToAxis (q_math.c): row vectors forward/left/up; local vert maps v.x*ax0+v.y*ax1+v.z*ax2
     let ax0=[cp*cy,cp*sy,-sp_],
         ax1=[sr*sp_*cy-cr*sy, sr*sp_*sy+cr*cy, sr*cp],
         ax2=[cr*sp_*cy+sr*sy, cr*sp_*sy-sr*cy, cr*cp];
     // COMPOSE WITH THE TAG AXIS (mrot[3], see the spawn step): MatrixMultiply(own, tag, out)
     // -> out row i = own[i][0]*tag[0] + own[i][1]*tag[1] + own[i][2]*tag[2]
     // (cg_tempmodels.cpp:1037-1038). This is what makes the muzzle-flash card fire down the
     // barrel while `randomroll` spins it about that forward axis, instead of tumbling free.
     const _TX=p.mrot[3];
     if(_TX){const T0=_TX[0],T1=_TX[1],T2=_TX[2];
       const _mm=r=>[r[0]*T0[0]+r[1]*T1[0]+r[2]*T2[0],
                     r[0]*T0[1]+r[1]*T1[1]+r[2]*T2[1],
                     r[0]*T0[2]+r[1]*T1[2]+r[2]*T2[2]];
       ax0=_mm(ax0);ax1=_mm(ax1);ax2=_mm(ax2);}
     const Vv=M3.v,Tt=M3.t,r3=[],pj=[];
     for(let k=0;k<Vv.length;k++){const v=Vv[k];
       const wx=v[0]*ax0[0]+v[1]*ax1[0]+v[2]*ax2[0];
       const wy=v[0]*ax0[1]+v[1]*ax1[1]+v[2]*ax2[1];
       const wz=v[0]*ax0[2]+v[1]*ax1[2]+v[2]*ax2[2];
       const rx=p.x+scl*wx, ry=p.y+scl*wz, rz=p.z+scl*wy;   // MOHAA Z-up -> render Y-up
       r3.push([rx,ry,rz]); pj.push(project([rx,ry,rz]));
     }
     const order=[];
     for(let ti=0;ti<Tt.length;ti++){const tr=Tt[ti];const A=pj[tr[0]],B=pj[tr[1]],C=pj[tr[2]];
       if(A[2]<=0||B[2]<=0||C[2]<=0)continue;
       order.push([(A[2]+B[2]+C[2]),tr,A,B,C,ti]);}
     order.sort((u,w)=>w[0]-u[0]);   // far first
     const col3=M3.color||[0.56,0.56,0.60], Ld=[0.40,0.82,0.41];  // fixed key light (render space)
     // TEXTURED DEBRIS: the sub-model .skd carries real UVs and its surface's shader texture
     // (metal_section / concrete1 / woodbeams ...). Paint each triangle with the same affine
     // texel->screen transform the main mesh uses, then darken by the flat-shade factor -
     // matching the in-game tempmodel, which is a full refEntity rendered with its own skin
     // (SpawnTempModel registers the model, ent.reType = RT_MODEL). Flat colour remains the
     // fallback when no texture resolved.
     const mimg=_meshImg(p.ei);
     // ADDITIVE SUB-MODEL SURFACES (M3.add - the sub-tik's `surface ... shader ...` blends
     // add). muzflash.tik is `surface material1 shader muzmodel`, and muzmodel (effects.shader)
     // is `blendFunc GL_SRC_ALPHA GL_ONE` + `cull none`: the card is ADDED to the scene, so
     // flashnode1.tga's black surround contributes nothing. Drawing it source-over painted
     // that surround as an opaque BLACK RECTANGLE around the flame. Canvas 'lighter' is
     // premultiplied add - dst += src*srcAlpha - which is exactly GL_SRC_ALPHA/GL_ONE.
     // Such a stage also carries no rgbGen, so FinishShader gives it CGEN_IDENTITY_LIGHTING
     // (tr_shader.c:1755-1765) - a flat full-bright constant, NOT lightingDiffuse. So the
     // per-facet flat shade must be skipped too (lit=1 -> _meshShade returns the image
     // untouched), otherwise the flash is directionally darkened.
     const _madd=!!M3.add;
     ctx.globalCompositeOperation=_madd?'lighter':'source-over'; ctx.globalAlpha=Math.min(1,a);
     for(const o of order){const tr=o[1],A=r3[tr[0]],B=r3[tr[1]],Cc=r3[tr[2]];
       // flat shade from the true render-space face normal (two-sided: chunks are open shells)
       const e1=[B[0]-A[0],B[1]-A[1],B[2]-A[2]], e2=[Cc[0]-A[0],Cc[1]-A[1],Cc[2]-A[2]];
       let nx=e1[1]*e2[2]-e1[2]*e2[1], ny=e1[2]*e2[0]-e1[0]*e2[2], nz=e1[0]*e2[1]-e1[1]*e2[0];
       const nl=Math.hypot(nx,ny,nz)||1; nx/=nl;ny/=nl;nz/=nl;
       const lit=_madd?1:(0.35+0.65*Math.abs(nx*Ld[0]+ny*Ld[1]+nz*Ld[2]));
       let painted=false;
       if(mimg&&M3.uv&&M3.uv.length){
         const tr3=o[1],a2=o[2],b2=o[3],c2=o[4];
         const iw=mimg.naturalWidth||64,ih=mimg.naturalHeight||64;
         const p0x=M3.uv[tr3[0]*2]*iw,p0y=M3.uv[tr3[0]*2+1]*ih,
               p1x=M3.uv[tr3[1]*2]*iw,p1y=M3.uv[tr3[1]*2+1]*ih,
               p2x=M3.uv[tr3[2]*2]*iw,p2y=M3.uv[tr3[2]*2+1]*ih;
         const e1x=p1x-p0x,e1y=p1y-p0y,e2x=p2x-p0x,e2y=p2y-p0y;
         const det=e1x*e2y-e2x*e1y;
         if(Math.abs(det)>1e-6){
           const f1x=b2[0]-a2[0],f1y=b2[1]-a2[1],f2x=c2[0]-a2[0],f2y=c2[1]-a2[1];
           const A00=(f1x*e2y-f2x*e1y)/det,A01=(-f1x*e2x+f2x*e1x)/det;
           const A10=(f1y*e2y-f2y*e1y)/det,A11=(-f1y*e2x+f2y*e1x)/det;
           const dx0=a2[0]-(A00*p0x+A01*p0y),dy0=a2[1]-(A10*p0x+A11*p0y);
           // shade is baked INTO the texel (alpha preserved), never painted over the facet
           const sim=_meshShade(mimg,lit);
           if(sim._pat===undefined){try{sim._pat=ctx.createPattern(sim,'repeat');}catch(e){sim._pat=null;}}
           ctx.save();
           ctx.setTransform(A00*DPR,A10*DPR,A01*DPR,A11*DPR,dx0*DPR,dy0*DPR);
           ctx.beginPath();ctx.moveTo(p0x,p0y);ctx.lineTo(p1x,p1y);ctx.lineTo(p2x,p2y);ctx.closePath();
           if(sim._pat){ctx.fillStyle=sim._pat;ctx.fill();}
           else{try{ctx.clip();ctx.drawImage(sim,0,0);}catch(e){}}
           ctx.restore();
           painted=true;
         }
       }
       if(!painted){
         const R=Math.min(255,(col3[0]*255*lit)|0),G=Math.min(255,(col3[1]*255*lit)|0),Bb=Math.min(255,(col3[2]*255*lit)|0);
         ctx.fillStyle='rgb('+R+','+G+','+Bb+')';
         ctx.beginPath();ctx.moveTo(o[2][0],o[2][1]);ctx.lineTo(o[3][0],o[3][1]);ctx.lineTo(o[4][0],o[4][1]);ctx.closePath();ctx.fill();}}
     ctx.globalAlpha=1; ctx.globalCompositeOperation='source-over';
     continue;
   }
   let src=emitFrame(p.ei,p.age);
   ctx.globalCompositeOperation=p.additive?'lighter':'source-over';
   // VSS puffs take the per-puff frame (lighting x jitter tint, per-puff rotation sign
   // and frozen-at-spawn phase); the shared per-emitter composite below stays for flat
   // sprites only, byte-identical to before.
   if(p.vol){const _vf=_vssFrame(p); if(_vf)src=_vf;}
   let _pa=Math.min(1,a);
   const _bnd=(emitImg[p.ei]&&emitImg[p.ei].bnd)||null;
   if(p.atest&&src){
     // alpha-tested sprite (see _atestVariant): swap in the thresholded variant for the
     // current fade level and draw it OPAQUE - alpha only gates the test, it never blends.
     // EROSION PATTERN = the launcher's phase-0 STATIC BAKE (base x noise - rec.erode),
     // the exact threshold input of the version whose granular per-texel dissipation was
     // verified frame-by-frame against in-game footage. The granular speckle in that
     // dissolve IS the noise alpha; the base's own alpha alone thresholds into smooth
     // rounded blobs. The pattern never scrolls/spins (in-game reference); the animated
     // bundle drives RGB grain only (_bundleFrame + _maskApply below).
     const _ei=emitImg[p.ei], _er=(_ei&&_ei.erode)||null;
     const _ms=(_er&&_er._ok)?(_er._tinted||_er):src;
     const _v=_atestVariant(_ms,p.atest,_pa);
     if(_v===undefined)continue;              // fully eroded - engine draws nothing
     if(_v){
       let _f=_v;
       if(_bnd&&_bnd.img._ok){
         const _mod=_bundleFrame(src,_bnd);
         if(_mod){const _mm=_maskApply(_mod,_v); if(_mm)_f=_mm;}
       }
       src=_f;_pa=1;
     }
   }else if(_bnd&&_bnd.img._ok&&src&&!p.vol){
     const _mod=_bundleFrame(src,_bnd,true);  // non-tested sprite: drifting grain + noise alpha
     if(_mod)src=_mod;
   }
   ctx.globalAlpha=_pa;
   if(src){
     // Screen budget: the engine has NO per-sprite size cap - electric_panelmelt's drop1
     // corona (scale 0.3, scalerate 5) legitimately grows to ~115u, nearly the whole
     // emitter, before dying. The old 0.55*minDim cap pinned it a few frames before death
     // ("grows, stalls, disappears"). Match the VSS allowance: a sprite may fill the view.
     const cap=Math.min(W,H)*1.6;
     const unit=scl*sp[3];                           // world-scale -> screen px per world unit
     // ALIGNSTRETCH SCOPE (tr_sprite.c:103-133 + tr_shader.c:3424): a shader without
     // spritegen defaults to SPRITE_PARALLEL, whose quad is built purely from VIEW axes -
     // the entity axis that T2_ALIGNSTRETCH scales never reaches it, so alignstretch is a
     // no-op for these sprites in-game (welding sparksflash: corona_util + alignstretch 1
     // stays a round, growing corona). Only MESH tempmodels (RT_MODEL refEntities) visibly
     // stretch, so the along-velocity path is gated to basesize>0.
     let longSz, shortSz, alongVel=(p.basesize>0);
     if(p.vol){
       // ENGINE-EXACT VSS puff size (tr_sprite.c RB_DrawSprite): the quad's world width =
       // texW_px * entScale * spritescale, and for volumetric smoke the refEntity scale is
       // radius/5 (cg_volumetricsmoke AddVSSSources). So world size = texpx * (radius/5) *
       // spritescale - NOT 2*radius. With a 32px vsssource at spritescale 1 a radius-10 puff is
       // ~64u across (vs the old ~20u), so puffs overlap into a continuous stack like in-game.
       // VSS puff world size = VSS_UNIT * (radius/5) * spritescale. Texture PIXELS only set
       // the aspect ratio (vsssource is square, so this is symmetric); the absolute size
       // comes from VSS_UNIT, tunable independently of SPR_UNIT. Lowering VSS_UNIT trims
       // oversized smoke columns (tanksmoke/thin_black_short) and dense smoke balls
       // (explosion_mine, higgins_mushroom) without touching flat-sprite effects.
       const entS=scl/5.0, ss=(p.sscale||1);          // scl = world radius (1..32)
       const _tw=p.texw>0?p.texw:1, _th=p.texh>0?p.texh:1, _asp=_tw/_th;
       const wW=VSS_UNIT*entS*ss*(_asp>=1?1:_asp), wH=VSS_UNIT*entS*ss*(_asp>=1?1/_asp:1);
       const vcap=Math.min(W,H)*1.6;                   // VSS puffs may legitimately fill the view
       longSz =Math.max(2,Math.min(vcap, Math.max(wW,wH)*sp[3]));
       shortSz=Math.max(2,Math.min(vcap, Math.min(wW,wH)*sp[3]));
       alongVel=false;
     } else if(p.basesize>0){
       // MESH particle (e.g. a spark = splinter.skd sliver): size as its TRUE geometry and
       // keep its real aspect ratio so it reads as a thin streak, not a fat square blob.
       // x0.8 on the short axis sharpens it toward the in-game ~6:1 sliver.
       // NO pixel floor here: the alignstretch multiplier is applied to this raw length
       // below, and flooring first turned distant hyper-fast sparks (electrical_fire
       // sparks1b at friction -40, millions of u/s, projecting near screen centre at a
       // tiny px-per-unit) into 2px x hugeMultiplier = full-screen capped bars. Distant
       // sparks must stay subpixel and be culled, like the engine's perspective gives.
       longSz =Math.min(cap, unit*p.basesize);
       shortSz=Math.max(1.2, longSz/(p.baseaspect>1?p.baseaspect:1)*0.8);
     } else {
       // SPRITE particle world size. The engine quad is origin_x * ent.scale (RB_DrawSprite,
       // tr_sprite.c:152-155) where origin_x is the .spr file's NATIVE half-size - NOT the
       // texture pixel count. A fully-authored MOHAA sprite renders ~22 world units across at
       // scale 1.0 (measured in-game: corona_util.tik / corona_red.tik at scale 1 = 22u
       // diameter), which is why tik authors use tiny scales like .0625 on top of a big base.
       // The .spr files aren't in the extracted data, so use the measured 22u constant times
       // ent.scale (scl already folds in scale*(1+scalerate*age)) and the shader spritescale.
       // Texture PIXELS only set the aspect ratio, never the absolute size - sizing by pixels
       // (the old formula) made scale-.0625 sprites ~16x too small (mortar/mine dirt effects).
       // texture-proportional: world size = texturePx * SPR_K * scale * spritescale, with the
       // long axis carrying the full texture dimension and the short axis its aspect fraction.
       // scl already folds in scale*(1+scalerate*age); unit = scl*sp[3] (px per world unit).
       const tw=p.texw>0?p.texw:32, th=p.texh>0?p.texh:32;
       const kk=unit*SPR_K*(p.sscale||1);
       let lw=kk*tw, lh=kk*th;
       // ASPECT-PRESERVING cap: clamp both axes by the SAME factor so an oversized sprite
       // clips at the frame edge (as in-game) instead of stretching. Clamping each axis
       // independently against `cap` squashed a non-square sprite toward the cap on its long
       // axis while the short axis kept growing - the "vertical down-stretch to stay in view"
       // seen on mortar_dirthit (256x512) as it bloomed past the screen via scalerate 16.
       const _big=Math.max(lw,lh);
       if(_big>cap){const f=cap/_big; lw*=f; lh*=f;}
       longSz =Math.max(2,Math.max(lw,lh));
       shortSz=Math.max(2,Math.min(lw,lh));
     }
     ctx.save(); ctx.translate(sp[0],sp[1]);
     if(alongVel){
       // WORLD-ENDPOINT PROJECTION: the engine stretches the model's forward axis in WORLD
       // space (T2_ALIGNSTRETCH, cg_tempmodels.cpp:531-538: fScale = |origin - oldorigin| *
       // scale2, one 10 Hz physics step of travel - cg_effect_physicsrate defaults to 10,
       // cg_commands.cpp:3107 + docstring :253) and the GPU's projection then foreshortens
       // it. So compute the stretched WORLD length, place the streak's two endpoints
       // +-worldLen/2 along the velocity, and project BOTH: screen length, orientation and
       // foreshortening all fall out exactly. The previous screen-angle sample had a fatal
       // blind spot: a spark flying PARALLEL TO THE VIEW AXIS projects ~zero screen motion
       // at ANY camera orientation, tripped the low-dl fallback (-pi/2), and drew its full
       // world-speed length as a camera-facing VERTICAL bar (electrical_fire's sphere
       // emitters launch such sparks constantly). In-game those foreshorten to dots.
       const spd=Math.hypot(p.vx,p.vy,p.vz);
       const _fs=(p.stretch>0)?Math.max(0.05, spd*0.1*p.stretch):1;
       const wLen=(p.basesize>0?p.basesize:0)*scl*_fs;   // stretched length, world units
       let L=0, ang=0, havedir=false;
       if(spd>0.01 && wLen>0){
         const ux=p.vx/spd,uy=p.vy/spd,uz=p.vz/spd,h=wLen*0.5;
         const pa=project([p.x-ux*h,p.y-uy*h,p.z-uz*h]);
         const pb=project([p.x+ux*h,p.y+uy*h,p.z+uz*h]);
         if(pa[2]>1&&pb[2]>1){
           const ddx=pb[0]-pa[0],ddy=pb[1]-pa[1];
           L=Math.hypot(ddx,ddy);
           if(L>0.5){ang=Math.atan2(ddy,ddx);havedir=true;}
         }
       }
       if(!havedir){
         if(p.stretch>0){
           // stretched streak foreshortened below drawable size (view-axis spark, or an
           // endpoint past the near plane): invisible in-engine - cull, don't floor.
           ctx.restore();continue;
         }
         // static mesh fallback (bare `align`, ~zero velocity): base length, upright
         // (-pi/2) - matching the identity-axis pose in-game where MOHAA Z=up
         // (aircraft_explosion `exploder`: metal_section.tik, align, no velocity).
         L=longSz; ang=(p.basesize>0?-Math.PI/2:p.roll);
       }
       L=Math.min(cap,L);
       // subpixel cull AFTER stretch+projection: a distant or foreshortened spark whose
       // streak projects under ~1.5px is invisible in-engine; never floor it into view.
       if(L<1.5){ctx.restore();continue;}
       // map the texture's LONG axis onto the velocity direction. The spark texture is
       // 8x32 (its bright streak runs vertically), so a tall texture needs an extra 90deg
       // or the streak would be drawn ACROSS the motion and read as a fat smear.
       if(p.texh>p.texw){ ctx.rotate(ang+Math.PI/2); ctx.drawImage(src,-shortSz*0.5,-L*0.5,shortSz,L); }
       else             { ctx.rotate(ang);           ctx.drawImage(src,-L*0.5,-shortSz*0.5,L,shortSz); }
     } else if(p.sprtype==='upright'){
       // SPRITE_PARALLEL_UPRIGHT (tr_sprite.c:135-160): build the quad in WORLD space with
       //   up    = world Z   (render +Y) - fixed vertical, never tilts
       //   right = normalize(camFwd.y, -camFwd.x, 0) - horizontal, perpendicular to the
       //           camera's horizontal facing (tr_sprite.c:151-153)
       // so the quad only YAWS to face the camera. Rendering always goes through
       // drawQuadPersp: exact projected corners, adaptively subdivided perspective
       // strips, analytic near clipping. ONE continuous path for every camera angle - the previous
       // fast-affine/strip gate (depth ratio 1.08) visibly re-seated the texture whenever
       // slow camera motion crossed the threshold or stepped the coarse strip count: the
       // "briefly stretches, then snaps flat" jitter.
       const b=camBasis();                              // b.f = camera forward, render Y-up
       // engine cull (tr_sprite.c:139-146): axis[0][2] beyond +/-0.999 - looking almost
       // straight up/down leaves no horizontal component to build `right` from; the
       // engine returns without drawing, so must we. b.f[1] (render Y) IS MOHAA fwd Z.
       if(b.f[1]>0.999||b.f[1]<-0.999){ctx.restore();continue;}
       // horizontal right = camForward rotated 90 deg about world-up, normalized
       let rx=b.f[2], rz=-b.f[0]; const rl=Math.hypot(rx,rz)||1; rx/=rl; rz/=rl;
       // WORLD half-extents from scl (camera-independent). world = scl*SPR_K*texPx*spritescale.
       // (the old long/short remap here was an identity - hw always got texw, hh texh)
       const _kw=scl*SPR_K*(p.sscale||1);
       const hw=_kw*(p.texw>0?p.texw:32)*0.5, hh=_kw*(p.texh>0?p.texh:32)*0.5;
       const px0=p.x, py0=p.y, pz0=p.z;
       drawQuadPersp(src,
         [px0-rx*hw, py0+hh, pz0-rz*hw],    // TL = origin - right*hw + worldUp*hh
         [px0+rx*hw, py0+hh, pz0+rz*hw],    // TR
         [px0-rx*hw, py0-hh, pz0-rz*hw],    // BL
         [px0+rx*hw, py0-hh, pz0+rz*hw]);   // BR
     } else if(p.sprtype==='oriented'&&p.opy&&!p.lglow){
       // SPRITE_ORIENTED (tr_sprite.c:131-133): quad axes = axis[1] (right) / axis[2] (up)
       // from the entity's Euler angles - a WORLD-FIXED quad. EXCEPT when the shader also has
       // `deformVertexes lightglow` (p.lglow): LightGlowDeform (tr_shade_calc.c:809-895) rebuilds
       // the quad from the CAMERA's right/up every frame, overriding the oriented axes into a
       // camera-facing glow. Those fall through to the camera-facing branch below (fire_ring).
       // Two sub-cases based on T_ALIGN:
       //
       // WITH T_ALIGN (alignstretch/align → cg_commands.cpp:1815, 2231):
       //   cg_tempmodels.cpp:596-599 resets cgd.angles = velocity.toAngles() EACH FRAME
       //   before T2_AMOVE adds avelocity*dt (cg_tempmodels.cpp:604-608). Because angles
       //   reset every frame the avelocity contribution is non-cumulative (~1-3°/frame).
       //   Net: sprite tracks velocity direction, no spin. vectoangles from current
       //   velocity; roll = 0 (velocity.toAngles() always returns roll=0).
       //
       // WITHOUT T_ALIGN (flat rings, glass shards, etc.):
       //   angles accumulate from initial opy + opyr*age; roll from p.roll.
       //
       // Port of q_shared AngleVectors: axis[1]=-right, axis[2]=up, MOHAA coords.
       let _pi, _ya, _ro;
       if(p.algn){
         // vectoangles: p.vx=MOHAA vx, p.vz=MOHAA vy (render Z), p.vy=MOHAA vz (vertical)
         const _mh=Math.hypot(p.vx,p.vz);        // horizontal mag in MOHAA xy-plane
         const _mv=Math.hypot(p.vx,p.vy,p.vz);
         if(_mv>0.001){_pi=-Math.atan2(p.vy,_mh);_ya=Math.atan2(p.vz,p.vx);}
         else{_pi=p.opy[0];_ya=p.opy[1];}        // stationary: fall back to initial angles
         _ro=0;
       }else{
         _pi=p.opy[0]+p.opyr[0]*p.age;_ya=p.opy[1]+p.opyr[1]*p.age;_ro=p.roll;
       }
       const _sy=Math.sin(_ya),_cy=Math.cos(_ya),_sp=Math.sin(_pi),_cp=Math.cos(_pi),
             _sr=Math.sin(_ro),_cr=Math.cos(_ro);
       const R3=[_sr*_sp*_cy-_cr*_sy, _sr*_sp*_sy+_cr*_cy, _sr*_cp];   // axis[1] (right)
       const U3=[_cr*_sp*_cy+_sr*_sy, _cr*_sp*_sy-_sr*_cy, _cr*_cp];   // axis[2] (up)
       // engine size (RB_DrawSprite :152-155): org_x = width*0.5*scale along right,
       // org_y = height*0.5*scale along up - NO long/short axis remap for oriented quads.
       const _kw=scl*SPR_K*(p.sscale||1);
       const _tw=p.texw>0?p.texw:32, _th=p.texh>0?p.texh:32;
       const hw=_kw*_tw*0.5, hh=_kw*_th*0.5;
       // MOHAA (x,y,z-up) -> render (x, y=up, z): [m0, m2, m1] - same swap the particle
       // positions/velocities use at spawn. Project centre + the four half-vector
       // endpoints and draw via setTransform, exactly like the upright branch (project()
       // is non-linear, so anchoring at sp would drift as the camera orbits).
// Same continuous path as the upright branch: exact corners + 1/z strips, no gate.
       // An oriented quad at a grazing angle (flat water ring near the camera) spans a
       // large depth range too; the old single affine both smeared it and vanished it when
       // one corner crossed the near plane. Engine rasterization = tr_sprite.c:162-186.
       const _rw=[R3[0]*hw,R3[2]*hw,R3[1]*hw], _uw=[U3[0]*hh,U3[2]*hh,U3[1]*hh]; // render coords
       drawQuadPersp(src,
         [p.x-_rw[0]+_uw[0], p.y-_rw[1]+_uw[1], p.z-_rw[2]+_uw[2]],   // TL
         [p.x+_rw[0]+_uw[0], p.y+_rw[1]+_uw[1], p.z+_rw[2]+_uw[2]],   // TR
         [p.x-_rw[0]-_uw[0], p.y-_rw[1]-_uw[1], p.z-_rw[2]-_uw[2]],   // BL
         [p.x+_rw[0]-_uw[0], p.y+_rw[1]-_uw[1], p.z+_rw[2]-_uw[2]]);  // BR
     } else {
       // camera-facing quad. SPRITE_PARALLEL_ORIENTED (tr_sprite.c:105-121) rotates the
       // view axes by the sprite's roll (cr/sr from ent.axis[1], which AnglesToAxis built
       // from the avelocity-integrated angles); plain SPRITE_PARALLEL (:123-130) copies the
       // view axes with right NEGATED and never rolls - the engine ignores angles/avelocity
       // for it, so an explicit `spritegen parallel` must not spin here. Emitters with no
       // resolved spritegen (sprtype null) default to SPRITE_PARALLEL in-engine (tr_shader.c
       // :2989 zero-inits sprite.type) but keep the legacy roll path here: parallel_oriented
       // is by far the most common authored type, and effects signed off under the old
       // behaviour stay pixel-identical.
       //
       // COUNTER-ROTATING tcMod BUNDLE (explosed / explosed2, sprites.shader: `tcmod rotate
       // 40` + nextbundle `tcmod rotate -40`) - the double-texture churn lives in _bundleFrame
       // (brot vs rotate). Whether the WHOLE sprite ALSO rolls depends purely on spritegen:
       //   - explosed (explosion_bridge): NO spritegen -> SPRITE_PARALLEL -> never rolls, so
       //     `avelocity 0 0 300` is a no-op; the entity roll must be SUPPRESSED or it spins
       //     the whole sprite and hides the churn (the bridge fix).
       //   - explosed2 (explosion_conflagration): `spritegen parallel_oriented` -> DOES roll,
       //     so `avelocity 0 0 range 60 600` genuinely spins each puff at a random 60-660 deg/s
       //     ON TOP of the ±40 churn (slow puffs read as double-spin, fast ones spin visibly
       //     clockwise). The entity roll must be KEPT.
       // So _crb only suppresses roll for the SPRITE_PARALLEL family (null / 'parallel'),
       // never for parallel_oriented.
       const _crb=_bnd&&(_bnd.brot||_bnd.rotate);              // counter-rotating tcMod bundle
       const _noRoll=(p.sprtype==='parallel')||(_crb&&p.sprtype!=='parallel_oriented');
       if(_noRoll) ctx.scale(-1,1);   // VectorNegate(view right), no roll
       else ctx.rotate(p.roll);
       const w=(p.texw>=p.texh)?longSz:shortSz, h=(p.texw>=p.texh)?shortSz:longSz;
       ctx.drawImage(src,-w*0.5,-h*0.5,w,h);
     }
     ctx.restore();
   } else {                                // no sprite resolved: soft additive blob fallback
     // FIRST-PLAY WHITE FLASH FIX: `src` is null both when an emitter has NO sprite (draw the
     // soft blob, as designed) AND when it simply hasn't decoded yet on the very first play.
     // For bh_carpet_* the bulletimpact VSS puff (a big, near-white smoke texture) hit this on
     // frame 1 before its data-url loaded, so the fallback painted a screen-filling soft WHITE
     // sphere for ~0.5s - the reported flash - which vanished once the image loaded and the
     // real (small) sprite took over. If the emitter HAS a sprite/frames that are just pending,
     // skip this frame; the image onload calls draw() the instant it is ready. Only genuinely
     // sprite-less emitters still get the blob.
     const _er=emitImg[p.ei];
     const _sprPending=_er&&((_er.img&&!_er.img._ok)||(_er.frames&&_er.frames.length&&!_er.frames.some(f=>f&&f._ok)));
     if(_sprPending){ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';ctx.restore();continue;}
     const rpx=Math.max(1.5,scl*sp[3]*4);
     let R=(p.r*255)|0,G=(p.g*255)|0,B=(p.b*255)|0;
     if(!p.additive){R=Math.max(R,90);G=Math.max(G,90);B=Math.max(B,98);a*=0.7;}
     const grad=ctx.createRadialGradient(sp[0],sp[1],0,sp[0],sp[1],rpx);
     grad.addColorStop(0,'rgba('+Math.min(255,R)+','+Math.min(255,G)+','+Math.min(255,B)+','+a.toFixed(3)+')');
     grad.addColorStop(1,'rgba('+Math.min(255,R)+','+Math.min(255,G)+','+Math.min(255,B)+',0)');
     ctx.fillStyle=grad;ctx.beginPath();ctx.arc(sp[0],sp[1],rpx,0,7);ctx.fill();}
 }
 ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';ctx.restore();
}
function project(p){const ca=Math.cos(yaw),sa=Math.sin(yaw),ce=Math.cos(pitch),se=Math.sin(pitch);
 let dx=p[0]-cx,dy=p[1]-cy,dz=p[2]-cz;
 let x1=ca*dx+sa*dz, z1=-sa*dx+ca*dz, y1=dy;
 let y2=ce*y1-se*z1, z2=se*y1+ce*z1, x2=x1;
 // camera roll: rotate the view plane about the forward axis (tilt / head-toward-shoulder)
 const cr=Math.cos(roll),sr=Math.sin(roll); let xr=cr*x2-sr*y2, yr=sr*x2+cr*y2;
 let zc=z2+dist; const focal=Math.min(W,H)*0.9;
 const s=focal/(zc>0.001?zc:0.001);
 return[W/2+xr*s+panX*(W/2),H/2-yr*s+panY*(H/2),zc,s];}
function shade(hex,m){const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);
 return'rgb('+Math.round(r*m)+','+Math.round(g*m)+','+Math.round(b*m)+')';}
// PERSPECTIVE-CORRECT QUAD SPRITE (near-plane clipped). The engine hands RB_DrawSprite's
// four world corners (tr_sprite.c:162-186) to the tessellator as REAL 3D geometry, so the
// GPU clips them against the near plane and rasterizes perspective-correct. One canvas
// affine can do neither: when a tall SPRITE_PARALLEL_UPRIGHT quad (mortar_dirthit, 256x512,
// scalerate 8 -> hh grows to hundreds of world units) has its TOP corner swing close to the
// eye - orbiting ABOVE the emitter - project() magnifies that endpoint enormously and one
// affine smears the WHOLE texture across that span. So: subdivide into strips, project each
// strip's EXACT corners, draw each as two affine triangles, SKIP strips at/behind the near
// plane (= the clip).
// CONTINUITY (anti-jitter): every quantity here must vary SMOOTHLY with camera motion, or
// the texture visibly re-seats itself frame to frame ("jitters/flickers"):
//   - NO fast-path/strip-path gate: strips run at every depth ratio and converge exactly to
//     the plain affine as the ratio -> 1, so there is no threshold to pop across.
//   - strips are subdivided ADAPTIVELY: bisect while the projected edge midpoints deviate
//     from the affine midpoints by more than 0.4px (on-screen only). Error is bounded at
//     0.4px by construction, and split transitions under camera motion re-seat the
//     texture by at most that threshold - imperceptible.
//   - strips are composited SEAM-FREE: drawn opaque into a shared offscreen canvas first
//     (the ~0.5px anti-gap overlaps resolve against themselves, not the scene), then
//     blended onto the main canvas ONCE with the particle's alpha + blend mode - overlap
//     lines no longer double-blend and crawl with the camera.
let _sqC=null,_sqX=null;                 // shared offscreen for seam-free strip compositing
function _sqCtx(){
 if(!_sqC){_sqC=document.createElement('canvas');_sqX=_sqC.getContext('2d');}
 const w=Math.max(1,Math.round(W*DPR)),h=Math.max(1,Math.round(H*DPR));
 if(_sqC.width!==w||_sqC.height!==h){_sqC.width=w;_sqC.height=h;}
 return _sqX;
}
function _triTex(tc,src,x0,y0,x1,y1,x2,y2,u0,v0,u1,v1,u2,v2){
 // affine mapping tex(u,v)->screen(x,y) from 3 correspondences; clip to the (slightly
 // expanded) screen triangle so adjacent strips overlap ~0.5px instead of leaving gaps.
 const d=(u1-u0)*(v2-v0)-(u2-u0)*(v1-v0); if(Math.abs(d)<1e-9)return;
 const a=((x1-x0)*(v2-v0)-(x2-x0)*(v1-v0))/d,
       b=((y1-y0)*(v2-v0)-(y2-y0)*(v1-v0))/d,
       c=((x2-x0)*(u1-u0)-(x1-x0)*(u2-u0))/d,
       e=((y2-y0)*(u1-u0)-(y1-y0)*(u2-u0))/d,
       f=x0-a*u0-c*v0, g=y0-b*u0-e*v0;
 tc.save();
 tc.setTransform(DPR,0,0,DPR,0,0);
 const cx3=(x0+x1+x2)/3, cy3=(y0+y1+y2)/3, pts=[[x0,y0],[x1,y1],[x2,y2]];
 tc.beginPath();
 for(let k=0;k<3;k++){const dx=pts[k][0]-cx3,dy=pts[k][1]-cy3,l=Math.hypot(dx,dy)||1,m=(l+0.5)/l;
   const X=cx3+dx*m,Y=cy3+dy*m; if(k)tc.lineTo(X,Y);else tc.moveTo(X,Y);}
 tc.closePath();tc.clip();
 tc.transform(a,b,c,e,f,g);
 tc.drawImage(src,0,0);
 tc.restore();
}
function drawQuadPersp(src,TL,TR,BL,BR){
 // TL/TR/BL/BR: WORLD corners (render coords, y-up) mapping to the image's top-left /
 // top-right / bottom-left / bottom-right. Strips run along whichever image axis spans
 // more DEPTH (vertical for an upright wall seen from above, along-ground for a flat
 // oriented ring seen at grazing angle); the other axis stays affine within a strip
 // (exactly uniform-depth for SPRITE_PARALLEL_UPRIGHT, whose right vector is horizontal
 // and perpendicular to the camera's horizontal forward - tr_sprite.c:151-153).
 const iw=src.width||1, ih=src.height||1, NEAR=1.0;
 const zTL=project(TL)[2],zTR=project(TR)[2],zBL=project(BL)[2],zBR=project(BR)[2];
 const dv=Math.abs(zTL-zBL)+Math.abs(zTR-zBR), du=Math.abs(zTL-zTR)+Math.abs(zBL-zBR);
 let La,Lb,Ra,Rb,texL,texR;
 if(dv>=du){ La=TL;Lb=BL;Ra=TR;Rb=BR; texL=t=>[0,t*ih];  texR=t=>[iw,t*ih]; }
 else      { La=TL;Lb=TR;Ra=BL;Rb=BR; texL=t=>[t*iw,0];  texR=t=>[t*iw,ih]; }
 // NEAR-PLANE CLIP OF THE STRIP RANGE: z is LINEAR in the world-space strip parameter t,
 // so the visible sub-range [tlo,thi] where both edges satisfy z > NEAR is solved exactly.
 // Clipping the RANGE (instead of skipping strips off a fixed grid) keeps the subdivision
 // continuous as a corner crosses the plane and concentrates every strip in the visible
 // part of the quad - this near clip IS the engine's near-plane clip of the real quad.
 const zLa=zTL, zLb=(dv>=du)?zBL:zTR, zRa=(dv>=du)?zTR:zBL, zRb=zBR;  // edge depths per axis pick
 const clipEdge=(z0,z1)=>{
   if(z0>NEAR&&z1>NEAR)return[0,1];
   if(z0<=NEAR&&z1<=NEAR)return null;
   const tX=(NEAR-z0)/(z1-z0);
   return z0>NEAR?[0,tX]:[tX,1];
 };
 const eL=clipEdge(zLa,zLb), eR=clipEdge(zRa,zRb);
 if(!eL||!eR)return;                              // whole quad at/behind the eye
 let tlo=Math.max(eL[0],eR[0]), thi=Math.min(eL[1],eR[1]);
 if(thi-tlo<1e-5)return;
 const _ins=(thi-tlo)*1e-3; tlo+=_ins; thi-=_ins;  // never sample exactly on the plane
 const lp=(P,Q,t)=>[P[0]+(Q[0]-P[0])*t,P[1]+(Q[1]-P[1])*t,P[2]+(Q[2]-P[2])*t];
 const tc=_sqCtx();
 tc.setTransform(1,0,0,1,0,0); tc.clearRect(0,0,_sqC.width,_sqC.height);
 tc.globalAlpha=1; tc.globalCompositeOperation='source-over';
 let bx0=1e9,by0=1e9,bx1=-1e9,by1=-1e9,drawn=false;
 const _M=64, _vx0=-_M, _vy0=-_M, _vx1=W+_M, _vy1=H+_M;   // expanded viewport, CSS px
 const emit=(t0,t1,l0,r0,l1,r1)=>{
   const a0=texL(t0), a1=texL(t1), b0=texR(t0), b1=texR(t1);
   // TRAPEZOID DEFECT: a strip's two affine triangles are exact at all four corners, but
   // when its near edge projects WIDER than its far edge the mapping at the strip's centre
   // deviates from true perspective by ~|w0-w1|/4 px (this was the residual 5-12px error
   // the strip-axis midpoint test could never see). Split the strip into columns until the
   // per-column defect is subpixel. Along the width axis depth is CONSTANT for an upright
   // sprite (right is perpendicular to the camera's forward, tr_sprite.c:151-153), so
   // linear interpolation of the screen corners IS the exact perspective mapping and the
   // columns cost no extra project() calls. Off-screen strips stay at one column.
   const w0=Math.hypot(r0[0]-l0[0],r0[1]-l0[1]), w1=Math.hypot(r1[0]-l1[0],r1[1]-l1[1]);
   let ex0=1e9,ey0=1e9,ex1=-1e9,ey1=-1e9;
   for(const q of [l0,l1,r0,r1]){ if(q[0]<ex0)ex0=q[0]; if(q[0]>ex1)ex1=q[0];
                                  if(q[1]<ey0)ey0=q[1]; if(q[1]>ey1)ey1=q[1]; }
   const vis=!(ex1<_vx0||ex0>_vx1||ey1<_vy0||ey0>_vy1);
   const k=vis?Math.min(24,Math.max(1,Math.ceil(Math.abs(w0-w1)/1.6))):1;
   for(let j=0;j<k;j++){
     const s0=j/k, s1=(j+1)/k;
     const LX0=l0[0]+(r0[0]-l0[0])*s0, LY0=l0[1]+(r0[1]-l0[1])*s0;
     const RX0=l0[0]+(r0[0]-l0[0])*s1, RY0=l0[1]+(r0[1]-l0[1])*s1;
     const LX1=l1[0]+(r1[0]-l1[0])*s0, LY1=l1[1]+(r1[1]-l1[1])*s0;
     const RX1=l1[0]+(r1[0]-l1[0])*s1, RY1=l1[1]+(r1[1]-l1[1])*s1;
     const AU0=a0[0]+(b0[0]-a0[0])*s0, AV0=a0[1]+(b0[1]-a0[1])*s0;
     const BU0=a0[0]+(b0[0]-a0[0])*s1, BV0=a0[1]+(b0[1]-a0[1])*s1;
     const AU1=a1[0]+(b1[0]-a1[0])*s0, AV1=a1[1]+(b1[1]-a1[1])*s0;
     const BU1=a1[0]+(b1[0]-a1[0])*s1, BV1=a1[1]+(b1[1]-a1[1])*s1;
     _triTex(tc,src,LX0,LY0,RX0,RY0,LX1,LY1, AU0,AV0,BU0,BV0,AU1,AV1);
     _triTex(tc,src,RX0,RY0,RX1,RY1,LX1,LY1, BU0,BV0,BU1,BV1,AU1,AV1);
   }
   drawn=true;
   if(ex0<bx0)bx0=ex0; if(ex1>bx1)bx1=ex1;
   if(ey0<by0)by0=ey0; if(ey1>by1)by1=ey1;
 };
 // ADAPTIVE PERSPECTIVE SUBDIVISION (anti-jitter): bisect a strip only while the TRUE
 // projected midpoints of its edges deviate from the strip's affine midpoints by more
 // than 0.4px AND the strip touches the (expanded) viewport. This bounds the on-screen
 // texture-placement error at 0.4px by construction, wherever the camera is - fixed strip
 // counts could not: uniform-1/z spacing starved the far half of a near-clipped quad (one
 // strip covered 75% of the texture at depth ratio 13 -> 1500px smear), while a fixed
 // per-strip depth ratio explodes strip screen sizes at the near plane. And because a
 // split only engages when the error crosses 0.4px, the discrete split/merge transitions
 // under camera motion re-seat the texture by <=0.4px - imperceptible, unlike the old
 // strip-count steps and the fast-path/strip gate that caused the visible flicker.
 let _budget=512;                                          // strip cap per quad (safety)
 const rec=(t0,t1,l0,r0,l1,r1,d)=>{
   const tm=(t0+t1)*0.5;
   const lm=project(lp(La,Lb,tm)), rm=project(lp(Ra,Rb,tm));
   let sx0=1e9,sy0=1e9,sx1=-1e9,sy1=-1e9;
   for(const q of [l0,r0,l1,r1,lm,rm]){ if(q[0]<sx0)sx0=q[0]; if(q[0]>sx1)sx1=q[0];
                                        if(q[1]<sy0)sy0=q[1]; if(q[1]>sy1)sy1=q[1]; }
   const onscreen=!(sx1<_vx0||sx0>_vx1||sy1<_vy0||sy0>_vy1);
   const errL=Math.hypot(lm[0]-(l0[0]+l1[0])*0.5, lm[1]-(l0[1]+l1[1])*0.5);
   const errR=Math.hypot(rm[0]-(r0[0]+r1[0])*0.5, rm[1]-(r0[1]+r1[1])*0.5);
   // depth 9 (<=512 strips) is only reachable for a near-plane-crossing, screen-filling
   // quad; ordinary views terminate at depth 0-3. The budget is a hard safety net.
   if(d<9 && _budget>1 && onscreen && Math.max(errL,errR)>0.4){
     _budget--;
     rec(t0,tm,l0,r0,lm,rm,d+1);
     rec(tm,t1,lm,rm,l1,r1,d+1);
   } else emit(t0,t1,l0,r0,l1,r1);
 };
 rec(tlo,thi, project(lp(La,Lb,tlo)), project(lp(Ra,Rb,tlo)),
              project(lp(La,Lb,thi)), project(lp(Ra,Rb,thi)), 0);
 if(!drawn)return;
 // composite the finished sprite ONCE with the caller's alpha + blend mode (main ctx
 // already carries them); bbox-limited, in device pixels on both sides.
 bx0=Math.max(0,Math.floor((bx0-1)*DPR)); by0=Math.max(0,Math.floor((by0-1)*DPR));
 bx1=Math.min(_sqC.width, Math.ceil((bx1+1)*DPR)); by1=Math.min(_sqC.height,Math.ceil((by1+1)*DPR));
 if(bx1<=bx0||by1<=by0)return;
 ctx.save();
 ctx.setTransform(1,0,0,1,0,0);
 ctx.drawImage(_sqC, bx0,by0,bx1-bx0,by1-by0, bx0,by0,bx1-bx0,by1-by0);
 ctx.restore();
}
function draw(){if(camMode==='free')syncCenterFromEye();
 // HYBRID SPLIT: WebGL draws the grid + skinned model (textures, flat mesh, wire,
 // pulse overlays) with a real per-pixel depth buffer; the 2D canvas on top keeps
 // everything that was always painted OVER the model anyway - autosprite billboards,
 // particles, bone nodes/labels, the setsize box. When no GL context exists (GLR
 // null) draw2DScene() runs the original painter's-algorithm path unchanged.
 if(GLR)GLR.render();
 ctx.clearRect(0,0,W,H);
 if(!GLR)draw2DScene(); else drawBillboards2D();
 drawTagOverlay();
 drawSetsizeBox();_buildOcclusionDepth();drawParticles();
 drawSelectedTagTop();}
// autosprite billboard pass for the GL path (the 2D fallback keeps its inline copy
// inside draw2DScene - that function is frozen byte-for-byte, so the engine-exact
// deform below applies to the GL overlay only).
// deformVertexes autoSprite / autoSprite2 (tr_shade_calc.c AutospriteDeform :578-646,
// Autosprite2Deform :665-807; parsed as DISTINCT deforms, tr_shader.c ParseDeform
// :1837-1845). Both operate on INDEPENDENT QUADS - groups of 4 verts / 6 indexes:
//   autoSprite  - each quad becomes a camera-facing square at its own midpoint,
//                 half-size = |corner0 - mid| * 0.707 (:608-616), full texture
//                 (RB_AddQuadStamp writes fresh 0..1 texcoords).
//   autoSprite2 - each quad PIVOTS ABOUT ITS LONG AXIS: the midpoints of the two
//                 shortest of the 6 edges define the major axis, which stays FIXED
//                 in world space; minor = normalize(major x viewForward) (:755-760)
//                 and the corners re-project as mid[j] +/- minor*shortEdgeHalfLen
//                 (:793-807). A flame stays rooted base-to-tip and only swivels
//                 toward the camera instead of floating as a free billboard.
// The engine trusts the quad layout (odd counts only WARN, :585-591); a surface here
// that is not quad-structured falls back to the old whole-surface stamp. Image top is
// oriented toward the major axis's upper (render +Y) end - the engine keeps the
// authored texcoords, which the billboard pass never had, and flame textures burn
// upward, so this matches the common authoring.
// ---- DEFORM_LIGHTGLOW center displacement (tr_shade_calc.c LightGlowDeform :809-897) ----
// The engine pushes each glow's midpoint TOWARD THE EYE by `radius` (clamped to
// dist=|eye-mid|-4 when very close, :880-890), while the billboard left/up axes come from the
// camera and are inverse-transformed into entity-local space (GlobalVectorToLocal, :827-836).
// The push is NOT inverse-transformed, so at render the entity placement rotation R rotates it
// off the view ray: R=I -> push lies along the ray (screen-STABLE, only depth/size change);
// R!=I -> the glow center swings off-origin and ORBITS as the camera moves - the in-game
// artifact the user saw. The real R lives in the .bsp/.map QUAKED spawn (absent from the
// .tik/.skd/.skc/.shader here), so the orbit is exposed behind an off-by-default illustrative
// toggle (view.tilt) with a synthetic R. Toggle off -> coronas render exactly centered as before.
function camEye(){ if(eye)return eye; const b=camBasis();
  return [cx-dist*b.f[0], cy-dist*b.f[1], cz-dist*b.f[2]]; }
function placementR(){
  // synthetic illustrative placement orientation: fixed 30 deg about an oblique axis. NOT read
  // from any asset (no map present); purely to make the LightGlow push land off the view ray so
  // the orbit is visible. Rodrigues rotation matrix, row-major 3x3.
  const th=30*Math.PI/180, c=Math.cos(th), s=Math.sin(th), t=1-c;
  let ax=0.40,ay=1.0,az=0.25; const al=Math.hypot(ax,ay,az); ax/=al;ay/=al;az/=al;
  return [t*ax*ax+c,    t*ax*ay-s*az, t*ax*az+s*ay,
          t*ax*ay+s*az, t*ay*ay+c,    t*ay*az-s*ax,
          t*ax*az-s*ay, t*ay*az+s*ax, t*az*az+c];
}
// mid: world center of the glow quad; radius: engine half-size (=|corner-mid|*0.707, the push
// length). Returns the displaced center mid + R*forward. Only called when view.tilt is on.
function lightGlowCenter(mid,radius){
  const e=camEye();
  const ex=e[0]-mid[0], ey=e[1]-mid[1], ez=e[2]-mid[2];
  const d=Math.hypot(ex,ey,ez)||1e-6, ux=ex/d, uy=ey/d, uz=ez/d;   // unit toward-eye
  const sc=(DATA.setsizeScale&&DATA.setsizeScale>1e-6)?DATA.setsizeScale:1;
  // REAL-OBJECT scaling: the glow is a fixed-size billboard at its true center, so its on-screen
  // size follows ordinary perspective (radius*focal/dist via project(mid)) and reaches maximum
  // only at the camera's CLOSEST approach - exactly like a physical object. The engine's LightGlow
  // toward-eye pull (mid += forward, pinned ~4u in front) both over-inflates the growth rate (zc =
  // dist - radius grows faster than dist) and CAPS apparent size once the pin engages (~19 game-u
  // here). We intentionally drop that pull so the corona keeps growing all the way in, per in-game
  // calibration. Center therefore stays at the true origin; only the orbit offsets it (below).
  let px=0, py=0, pz=0;
  if(view.tilt){
    // Illustrative placement orbit. The real placement rotation R lives in the .bsp/.map QUAKED
    // spawn (absent from .tik/.skd/.skc/.shader), so this is synthetic. Modeled as a PURE
    // screen-space swing: apply the synthetic R to the view ray, drop the on-ray component (so it
    // never touches size/depth), and gate its MAGNITUDE on the camera->corona distance in GAME
    // units (d*load_scale) to match in-game - zero beyond ORBIT_START, then logarithmic (slow,
    // then faster), capped near the origin. The swing DIRECTION still sweeps with the camera, so
    // it reads as orbiting; only the distance-gated magnitude is synthetic. Tuning knobs:
    // ORBIT_START (game-u where it begins), ORBIT_CAP (game-u where it saturates), ORBIT_MAX
    // (capped swing, as a fraction of the glow radius).
    const ORBIT_START=50.0, ORBIT_CAP=8.0, ORBIT_MAX=0.5;
    const R=placementR();
    const rx=R[0]*ux+R[1]*uy+R[2]*uz, ry=R[3]*ux+R[4]*uy+R[5]*uz, rz=R[6]*ux+R[7]*uy+R[8]*uz;
    const rd=rx*ux+ry*uy+rz*uz;                             // on-ray part of R*u
    const qx=rx-rd*ux, qy=ry-rd*uy, qz=rz-rd*uz;            // perpendicular swing direction
    const ql=Math.hypot(qx,qy,qz);
    const dGame=d*sc;
    if(ql>1e-3 && dGame<ORBIT_START){
      let f=Math.log(ORBIT_START/Math.max(dGame,ORBIT_CAP))/Math.log(ORBIT_START/ORBIT_CAP);
      f=Math.max(0,Math.min(1,f));                          // logarithmic 0->1 over START..CAP
      const m=f*(radius*ORBIT_MAX)/ql;                      // capped swing = ORBIT_MAX*radius
      px+=qx*m; py+=qy*m; pz+=qz*m;
    }
  }
  return [mid[0]+px, mid[1]+py, mid[2]+pz];
}
// ---- alphaGen distFade / oneMinusDistFade (tr_shade.c ComputeColors, AGEN_DIST_FADE
// :1098-1151, AGEN_ONE_MINUS_DIST_FADE :1153-1205; operands parsed in tr_shader.c
// ParseStage :1168-1194 into shader.fDistNear / fDistRange, defaulting to 256/256) ----
// The engine builds org = vertex - (viewOrigin - entityOrigin) projected onto the entity
// axes, i.e. the vertex measured from the eye in entity space; for a static prop with an
// identity placement that is just |eye - point|. Then len=(|org|-near)/range and
//   distFade         : len<0 -> 255, len>1 -> 0,   else (1-len)*255
//   oneMinusDistFade : len<0 -> 0,   len>1 -> 255, else len*255
// evaluated PER VERTEX; a billboard is one quad drawn as a unit here, so its centre is
// the correct single sample. Returns 0..1, and 1 for any surface with no fade declared.
function distFadeAlpha(tex,C){
 if(!tex||!tex.distfade)return 1;
 const df=tex.distfade,e=camEye();
 // UNIT CORRECTION. fDistNear/fDistRange are WORLD-space, but the renderer scales a static
 // model's verts by the tik `scale` (tr_staticmodels.cpp:450-451, vMins[k]=mins[k]*load_scale)
 // while this viewer renders the UNSCALED model space. So a viewer-space distance must be
 // multiplied by load_scale before it can be compared against the shader's thresholds - the
 // same correction rev 9 applied to the LightGlow pin (DATA.setsizeScale).
 const sc=(DATA.setsizeScale&&DATA.setsizeScale>1e-6)?DATA.setsizeScale:1;
 const L=Math.hypot(C[0]-e[0],C[1]-e[1],C[2]-e[2])*sc;
 let t=(L-df.near)/(df.range||256);
 if(t<0)t=0;else if(t>1)t=1;
 return df.inv?t:(1-t);}
function drawAutospriteSurf(si,tex,img){
 const s=DATA.surfRanges[si], V=model;
 const nv=s.vend-s.vstart;
 const quads=(nv>0&&nv%4===0&&(s.end-s.start)===(nv>>2)*2)?(nv>>2):0;
 ctx.globalCompositeOperation=tex.additive?'lighter':'source-over';
 if(!quads){                                   // not independent quads: legacy stamp
   const cr=surfCenterRadius(si);if(!cr)return;
   const sp=project([cr[0],cr[1],cr[2]]);if(sp[2]<=0)return;
   const size=Math.max(4,Math.min(Math.min(W,H)*0.95,cr[3]*sp[3]*1.41));
   ctx.drawImage(img,sp[0]-size/2,sp[1]-size/2,size,size);
   return;}
 const AS2=!!tex.autosprite2, b=AS2?camBasis():null;
 const iw=img.naturalWidth||img.width||1, ih=img.naturalHeight||img.height||1;
 for(let q=0;q<quads;q++){
   const base=(s.vstart+q*4)*3;
   const P=[0,1,2,3].map(k=>[V[base+k*3],V[base+k*3+1],V[base+k*3+2]]);
   if(!AS2){
     const mid=[(P[0][0]+P[1][0]+P[2][0]+P[3][0])*0.25,
                (P[0][1]+P[1][1]+P[2][1]+P[3][1])*0.25,
                (P[0][2]+P[1][2]+P[2][2]+P[3][2])*0.25];
     const r=Math.hypot(P[0][0]-mid[0],P[0][1]-mid[1],P[0][2]-mid[2])*0.707;
     // DEFORM_LIGHTGLOW toward-eye push + synthetic placement R (see lightGlowCenter), opt-in
     // via view.tilt so the default centered look is unchanged. r is already the engine
     // half-size (|corner-mid|*0.707) = the push length.
     // push always on for lightglow (pins center in front -> grows/fills, never vanishes);
     // the synthetic-R orbit inside lightGlowCenter is what view.tilt gates. Cap lifted for
     // lightglow so the glow can fill / overflow the screen (naturally bounded by the ~4-unit
     // pin); non-lightglow flames/arcs keep the 0.95*min screen cap.
     const C=tex.lightglow?lightGlowCenter(mid,r):mid;
     const sp=project(C);if(sp[2]<=0)continue;
     const size=Math.max(4,Math.min(tex.lightglow?Math.max(W,H)*8:Math.min(W,H)*0.95,r*2*sp[3]));
     ctx.drawImage(img,sp[0]-size/2,sp[1]-size/2,size,size);
     continue;}
   // autoSprite2: engine edge table (edgeVerts, tr_shade_calc.c :661-668)
   const EV=[[0,1],[0,3],[0,2],[1,3],[1,2],[3,2]];
   let s0=1e30,s1=1e30,n0=0,n1=0;
   for(let j=0;j<6;j++){const a=P[EV[j][0]],c=P[EV[j][1]];
     const l=(a[0]-c[0])*(a[0]-c[0])+(a[1]-c[1])*(a[1]-c[1])+(a[2]-c[2])*(a[2]-c[2]);
     if(l<s0){s1=s0;n1=n0;s0=l;n0=j;}
     else if(l<s1){s1=l;n1=j;}}
   const _m=(e)=>{const a=P[EV[e][0]],c=P[EV[e][1]];
     return[(a[0]+c[0])*0.5,(a[1]+c[1])*0.5,(a[2]+c[2])*0.5];};
   const m0=_m(n0),m1=_m(n1);
   const MJ=[m1[0]-m0[0],m1[1]-m0[1],m1[2]-m0[2]];        // major axis, world-fixed
   const f=b.f;                                            // camera forward
   let mnx=MJ[1]*f[2]-MJ[2]*f[1],
       mny=MJ[2]*f[0]-MJ[0]*f[2],
       mnz=MJ[0]*f[1]-MJ[1]*f[0];                          // minor = major x forward
   const ml=Math.hypot(mnx,mny,mnz);
   if(ml<1e-6)continue;                                    // major parallel to view
   mnx/=ml;mny/=ml;mnz/=ml;
   const h0=Math.sqrt(s0)*0.5, h1=Math.sqrt(s1)*0.5;       // short-edge half lengths
   // image top -> the major axis end that is higher in render space (+Y = world up)
   let T=m1,B2=m0,hT=h1,hB=h0;
   if(m0[1]>m1[1]){T=m0;B2=m1;hT=h0;hB=h1;}
   const TL=project([T[0]-mnx*hT, T[1]-mny*hT, T[2]-mnz*hT]);
   const TR=project([T[0]+mnx*hT, T[1]+mny*hT, T[2]+mnz*hT]);
   const BL=project([B2[0]-mnx*hB,B2[1]-mny*hB,B2[2]-mnz*hB]);
   const BR=project([B2[0]+mnx*hB,B2[1]+mny*hB,B2[2]+mnz*hB]);
   if(TL[2]<=0||TR[2]<=0||BL[2]<=0||BR[2]<=0)continue;
   const ux=(TR[0]-TL[0])/iw, uy=(TR[1]-TL[1])/iw;
   const vx=(BL[0]-TL[0])/ih, vy=(BL[1]-TL[1])/ih;
   if(Math.abs(ux*vy-vx*uy)<1e-6)continue;                 // degenerate on screen
   ctx.save();
   ctx.transform(ux,uy,vx,vy,TL[0],TL[1]);
   ctx.drawImage(img,0,0,iw,ih);
   ctx.restore();}}
function drawBillboards2D(){
 if(DATA.dontdraw||!view.tex||!view.sprite)return;
 let any=false;
 for(let si=0;si<LTEX.length;si++){const tex=LTEX[si];
   if(!tex||!tex.autosprite||hiddenSurf.has(si))continue;
   if(view.treesprite&&!isLodSprite(si))continue;
   const img=curImg(tex);if(!img)continue;
   if(!any){ctx.save();any=true;}
   drawAutospriteSurf(si,tex,img);}
 if(any){ctx.globalCompositeOperation='source-over';ctx.restore();}}
// ---- legacy Canvas-2D scene (grid + painter-sorted mesh): fallback when GL is
// unavailable. Byte-for-byte the pre-hybrid renderer - do not "improve" it; its
// job is to behave exactly as the shipped 2D viewer did.
function draw2DScene(){ctx.clearRect(0,0,W,H);
 // grid is anchored to the model's fixed ground position (cx0/cy0/cz0), not the live
 // camera center - otherwise in free-look it slides around with the look-at point.
 ctx.strokeStyle=TH.grid;ctx.lineWidth=1;const g=rad,gy=groundY;ctx.beginPath();
 for(let i=-4;i<=4;i++){let a=project([cx0+i*g/4,gy,cz0-g]),b=project([cx0+i*g/4,gy,cz0+g]);
   if(a[2]>0&&b[2]>0){ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);}
   let c=project([cx0-g,gy,cz0+i*g/4]),d=project([cx0+g,gy,cz0+i*g/4]);
   if(c[2]>0&&d[2]>0){ctx.moveTo(c[0],c[1]);ctx.lineTo(d[0],d[1]);}}
 ctx.stroke();
 const V=model,T=LT,UV=LUV;
 const fast=interacting;   // while orbiting/zooming/panning, skip the costly texture fill
 // effect-dummy anchors (rendereffects +dontdraw, e.g. dummy3 under smoke/spark/arc
 // emitters) are never drawn in-game - only their particles are. Skip the placeholder
 // mesh entirely. Real mesh effects (fire.tik, no +dontdraw) fall through and render.
 if(!DATA.dontdraw && (view.tex||view.mesh||view.wire)){const cache={};
   function pr(i){let c=cache[i];if(c)return c;c=project([V[i*3],V[i*3+1],V[i*3+2]]);cache[i]=c;return c;}
   const order=[];
   for(let t=0;t<T.length;t++){const tr=T[t];const a=pr(tr[0]),b=pr(tr[1]),c=pr(tr[2]);
     if(a[2]<=0||b[2]<=0||c[2]<=0)continue;order.push([(a[2]+b[2]+c[2]),t,a,b,c]);}
   order.sort((p,q)=>q[0]-p[0]);
   const L=[0.4,0.8,0.45],Ln=Math.hypot(L[0],L[1],L[2]);const sr=LSR;
   const billboards=[];   // autosprite surfaces (flame/arc) deferred to a camera-facing pass
   // alphaGen distFade, sampled ONCE PER SURFACE PER FRAME. The engine evaluates it per
   // vertex (tr_shade.c:1098-1151); the surface centre is the cheap equivalent here and keeps
   // the painter loop free of a hypot per triangle.
   const _dfa=[];
   for(const o of order){const t=o[1],a=o[2],b=o[3],c=o[4],tr=T[t];
     let si=0;for(let q=0;q<sr.length;q++){if(t>=sr[q].start&&t<sr[q].end){si=q;break;}}
     if(hiddenSurf.has(si))continue;   // surface +nodraw (server anim command) - not drawn
     const tex=LTEX[si];
     // "Tree Sprite" preview: jump straight to the far-LOD look by dropping every surface
     // that is not the billboard stand-in. Placed BEFORE the autosprite deferral so the
     // stand-in itself still routes to the billboard pass.
     if(view.treesprite&&!isLodSprite(si))continue;
     // deformVertexes-autosprite surfaces always face the player in-game: when the
     // Sprite toggle is on, draw them as billboards (collected here, drawn once each
     // below); when off they fall through and render as ordinary flat planes.
     if(tex&&tex.autosprite&&view.sprite){if(billboards.indexOf(si)<0)billboards.push(si);continue;}
     // deformVertexes autoSprite2 that is NOT a tree-LOD stand-in (no distFade) is a pure
     // always-camera-facing effect sprite - bh_wood_puff / bh_stone_puff (the bullet-hit puff
     // .tik viewed DIRECTLY: `surface all shader bh_wood_puff`, animmap + autoSprite2). It has
     // autosprite2 but NOT autosprite, so it missed the billboard deferral above and drew as a
     // flat oriented quad. Defer it to the camera-facing pass unconditionally (it always faces
     // the player in-game; not gated on the Sprite toggle, since it is the whole effect). LOD
     // stand-ins (autosprite2 + distFade) keep their own distance-gated path below.
     if(tex&&tex.autosprite2&&!(tex.distfade&&tex.distfade.inv)){if(billboards.indexOf(si)<0)billboards.push(si);continue;}
     // LOD cull: leaf/branch cards carry `alphaGen distFade`, so past near+range the engine
     // draws nothing at all and only the billboard stand-in is left - the far-distance look.
     let _fa=_dfa[si];
     if(_fa===undefined){const _cc=surfCenterRadius(si);_fa=_dfa[si]=(_cc?distFadeAlpha(tex,_cc):1);}
     if(_fa<=0.004)continue;
     const i0=tr[0],i1=tr[1],i2=tr[2];
     const ux=V[i1*3]-V[i0*3],uy=V[i1*3+1]-V[i0*3+1],uz=V[i1*3+2]-V[i0*3+2];
     const vx=V[i2*3]-V[i0*3],vy=V[i2*3+1]-V[i0*3+1],vz=V[i2*3+2]-V[i0*3+2];
     let nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx;const nn=Math.hypot(nx,ny,nz)||1;
     let dot=(nx*L[0]+ny*L[1]+nz*L[2])/(nn*Ln);const sh=0.35+0.65*Math.abs(dot);
     const add=tex&&tex.additive;const img=tex?curImg(tex):null;
     const textured=view.tex&&!fast&&img&&UV&&UV.length;
     // BACKFACE CULL. Painter's centroid sort can't order a long convex shell: at grazing
     // angles the far wall sorts in front of the near wall and its back faces (the inside
     // of the cylinder) bleed through. Dropping camera-facing-away tris leaves the convex
     // front half, which never self-occludes. Skip additive / pulse-only / autosprite
     // (two-sided FX) and pure-wireframe. Sign: skin() emits (X,Z,Y) - a Y<->Z reflection
     // - so a MOHAA CCW front face projects to NEGATIVE screen area here; >0 is back-facing.
     // two-sided (cull_* / cull disable) surfaces must render both faces. The flag lives on
     // DATA.surfRanges (always populated), NOT surfTex (which is null for any surface without a
     // loaded texture - e.g. mesh mode or an unresolved garment shader), so read it from sr[si].
     const _two = (tex&&tex.twosided) || (sr[si]&&sr[si].twosided);
     if(!add&&!(tex&&(tex.pulseOnly||tex.autosprite))&&!_two&&(view.tex||view.mesh)){
       const _a2=(b[0]-a[0])*(c[1]-a[1])-(c[0]-a[0])*(b[1]-a[1]);
       if(_a2<0)continue;}
     if(textured){
       // affine (per-triangle) texture map: solve texel-space -> screen-space transform
       const iw=img.naturalWidth,ih=img.naturalHeight;
       // base-stage `tcmod rotate <deg/sec>` (RB_CalcRotateTexMatrix, tr_shade_calc.c:809-826:
       // degs=-degsPerSecond*shaderTime, texcoords rotated about (0.5,0.5)) - the spinning
       // aircraft propeller discs (prop / c47prop). This is the ONLY 2D-path surface type that
       // carries texrotate, so every other surface keeps its byte-for-byte-identical UVs below.
       // These shaders are single-stage `clampmap` (NOT repeat): the disc sits inside a fully
       // transparent border, so rotated UVs that leave [0,1] must read as transparent, not tile.
       // Below (see _spin) the prop takes the single-drawImage branch (transparent outside the
       // one tile = clamp) instead of the repeat pattern, and skips the flat-shade darken pass -
       // otherwise the black shade triangle paints the transparent corners into a grey SQUARE and
       // the repeat wrap flashes opaque blade pixels into the corners as it turns. effT is the
       // shared effect clock (frozen while paused), advanced by effLoop because hasTexRot is set.
       let _u0=UV[i0*2],_v0=UV[i0*2+1],_u1=UV[i1*2],_v1=UV[i1*2+1],_u2=UV[i2*2],_v2=UV[i2*2+1];
       if(tex&&tex.texrotate){const _th=-tex.texrotate*effT*Math.PI/180.0,_c=Math.cos(_th),_s=Math.sin(_th);
         const _rot=(u,v)=>{const du=u-0.5,dv=v-0.5;return[_c*du-_s*dv+0.5,_s*du+_c*dv+0.5];};
         let _r;_r=_rot(_u0,_v0);_u0=_r[0];_v0=_r[1];_r=_rot(_u1,_v1);_u1=_r[0];_v1=_r[1];_r=_rot(_u2,_v2);_u2=_r[0];_v2=_r[1];}
       const p0x=_u0*iw,p0y=_v0*ih,p1x=_u1*iw,p1y=_v1*ih,p2x=_u2*iw,p2y=_v2*ih;
       const e1x=p1x-p0x,e1y=p1y-p0y,e2x=p2x-p0x,e2y=p2y-p0y;
       const det=e1x*e2y-e2x*e1y;
       if(Math.abs(det)>1e-6){
         const f1x=b[0]-a[0],f1y=b[1]-a[1],f2x=c[0]-a[0],f2y=c[1]-a[1];
         const A00=(f1x*e2y-f2x*e1y)/det,A01=(-f1x*e2x+f2x*e1x)/det;
         const A10=(f1y*e2y-f2y*e1y)/det,A11=(-f1y*e2x+f2y*e1x)/det;
         const dx=a[0]-(A00*p0x+A01*p0y),dy=a[1]-(A10*p0x+A11*p0y);
         // a repeating pattern (not a single drawImage) so UVs outside [0,1] tile -
         // tire tread (u up to ~9) and body panels (u up to ~5) wrap instead of vanishing.
         if(img._pat===undefined){try{img._pat=ctx.createPattern(img,'repeat');}catch(e){img._pat=null;}}
         // _spin = a `tcmod rotate` propeller disc: clamp it (single drawImage -> transparent
         // outside the one tile) so the rotating corners never wrap, and skip the flat-shade
         // darken below so its transparent border stays clear instead of a grey square.
         const _spin=!!(tex&&tex.texrotate);
         // alphaFunc is a BINARY test, not a blend (tr_shader.c:1129-1146): a texel either
         // passes at full opacity or is discarded. Drawing the raw RGBA instead alpha-BLENDS
         // the sub-threshold texels, and - far worse - the flat-shade darken below fills the
         // WHOLE triangle with black regardless of texel alpha, which is what printed a grey
         // box behind every leaf card. _spin already carried that exemption for exactly this
         // reason ("transparent border stays clear instead of a grey square"); alpha-tested
         // surfaces need it too, plus the clamp branch so nothing wraps into the corners.
         // The distFade ramp is fed to the TEST as vertex alpha rather than to globalAlpha,
         // because rgbGen vertex + alphaGen distFade modulate the texel BEFORE alphaFunc sees
         // it - so a distant canopy erodes from its soft edges inward, which is the in-game
         // behaviour, instead of washing out uniformly.
         const _atk=(tex&&tex.atest)?tex.atest:null;
         let _src=img,_hard=false,_drop=false;
         if(_atk){const _v=_atestVariant(img,_atk,_fa);
           if(_v===undefined)_drop=true;               // fully eroded - engine draws nothing
           else if(_v){_src=_v;_hard=true;}}           // null -> not decoded yet, use raw img
         ctx.save();
         if(_fa<1&&!_hard)ctx.globalAlpha=_fa;            // blended stages ramp; tested ones do not
         if(add)ctx.globalCompositeOperation='lighter';   // blendfunc add: flame glows, black->transparent
         ctx.setTransform(A00*DPR,A10*DPR,A01*DPR,A11*DPR,dx*DPR,dy*DPR);
         ctx.beginPath();ctx.moveTo(p0x,p0y);ctx.lineTo(p1x,p1y);ctx.lineTo(p2x,p2y);ctx.closePath();
         if(_drop){}
         else if(img._pat&&!_spin&&!_hard){ctx.fillStyle=img._pat;ctx.fill();}
         else{try{ctx.clip();ctx.drawImage(_src,0,0,iw,ih);}catch(e){}}
         ctx.setTransform(DPR,0,0,DPR,0,0);
         if(!add&&sh<0.99&&!_spin&&!_hard&&!_drop){ctx.fillStyle='rgba(0,0,0,'+(1-sh)*0.55+')';ctx.beginPath();
           ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.lineTo(c[0],c[1]);ctx.closePath();ctx.fill();}
         ctx.restore();
       }
     }
     // PULSE OVERLAY pass: an additive stage (pulse.tga) modulated by rgbGen wave, drawn over
     // the same triangle. For bangalore_pulsating it sits on top of the solid base; for
     // ..._ghosting (pulseOnly) it is the only thing drawn, so the model is a faint pulsing
     // ghost that vanishes at the wave trough - exactly the in-game look (bangalores.mp4).
     if(tex&&tex.pulse&&view.tex&&!fast&&UV&&UV.length){
       const P=tex.pulse,pim=P.img;
       if(pim&&pim._ok){
         const g=pulseGlow(P);
         if(g>0.003){
           const piw=pim.naturalWidth||2,pih=pim.naturalHeight||2;
           const q0x=UV[i0*2]*piw,q0y=UV[i0*2+1]*pih,q1x=UV[i1*2]*piw,q1y=UV[i1*2+1]*pih,q2x=UV[i2*2]*piw,q2y=UV[i2*2+1]*pih;
           const g1x=q1x-q0x,g1y=q1y-q0y,g2x=q2x-q0x,g2y=q2y-q0y;
           const pdet=g1x*g2y-g2x*g1y;
           if(Math.abs(pdet)>1e-6){
             const h1x=b[0]-a[0],h1y=b[1]-a[1],h2x=c[0]-a[0],h2y=c[1]-a[1];
             const B00=(h1x*g2y-h2x*g1y)/pdet,B01=(-h1x*g2x+h2x*g1x)/pdet;
             const B10=(h1y*g2y-h2y*g1y)/pdet,B11=(-h1y*g2x+h2y*g1x)/pdet;
             const bx=a[0]-(B00*q0x+B01*q0y),by=a[1]-(B10*q0x+B11*q0y);
             if(pim._pat===undefined){try{pim._pat=ctx.createPattern(pim,'repeat');}catch(e){pim._pat=null;}}
             ctx.save();
             ctx.globalCompositeOperation='lighter';     // GL_SRC_ALPHA GL_ONE (additive)
             ctx.globalAlpha=g;                           // rgbGen-wave brightness * distFade
             ctx.setTransform(B00*DPR,B10*DPR,B01*DPR,B11*DPR,bx*DPR,by*DPR);
             ctx.beginPath();ctx.moveTo(q0x,q0y);ctx.lineTo(q1x,q1y);ctx.lineTo(q2x,q2y);ctx.closePath();
             if(pim._pat){ctx.fillStyle=pim._pat;ctx.fill();}
             else{try{ctx.clip();ctx.drawImage(pim,0,0);}catch(e){}}
             ctx.setTransform(DPR,0,0,DPR,0,0);
             ctx.globalAlpha=1;
             ctx.restore();
           }
         }
       }
     }
     ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.lineTo(c[0],c[1]);ctx.closePath();
     // flat-shaded fill only when the Mesh toggle is on. If Texture is on but Mesh is off,
     // surfaces simply disappear while the camera moves and snap back to textures on settle.
     // A pulse-only ghost (..._ghosting) has no solid base, so it must NOT get a flat fill.
     if(!textured&&view.mesh&&!(tex&&tex.pulseOnly)){ctx.fillStyle=shade(palette[si%palette.length],sh);ctx.fill();}
     if(view.wire){ctx.strokeStyle=(view.mesh||textured)?'rgba(0,0,0,0.18)':'#3a4654';ctx.lineWidth=0.6;ctx.stroke();}}
   // camera-facing billboard pass for autosprite effect surfaces (flames, arcs).
   // additive is order-independent, so a simple per-surface draw is correct. Drawn
   // every frame (even while the camera moves): a few billboards are cheap, and an
   // autosprite flame must keep facing the camera instead of blinking out on motion.
   if(view.tex&&billboards.length){ctx.save();
     for(const si of billboards){const tex=LTEX[si];const img=curImg(tex);if(!img)continue;
       const cr=surfCenterRadius(si);if(!cr)continue;
       // DOCUMENTED EXCEPTION to the frozen 2D path (2nd, after texrotate): DEFORM_LIGHTGLOW
       // coronas may displace their center via the engine toward-eye push + synthetic placement
       // R (lightGlowCenter). Gated on tex.lightglow && view.tilt, so flames/arcs and the
       // default corona look are byte-identical to before. cr[3]=|corner-mid|, engine push
       // length = cr[3]*0.707.
       let C=[cr[0],cr[1],cr[2]];
       // push always on for lightglow (see lightGlowCenter): pins the center in front so the
       // corona keeps growing / fills the screen as the camera nears and never vanishes; the
       // orbit-only R is gated on view.tilt inside the helper. Cap lifted for lightglow so it can
       // fill / overflow (bounded by the ~4-unit pin); flames/arcs keep the 0.95*min screen cap.
       if(tex.lightglow)C=lightGlowCenter(C,cr[3]*0.707);
       // DOCUMENTED EXCEPTION to the frozen 2D path (3rd, after texrotate and lightglow):
       // alphaGen (oneMinus)DistFade. static_tree*sprite carries `deformVertexes autoSprite2`
       // + `alphaGen oneMinusDistFade <near> <range>`, so in-game the billboard is fully
       // TRANSPARENT until the eye is `near` units out and only then ramps in as the real
       // leaf cards (alphaGen distFade) ramp out. Without it this pass drew the stand-in
       // permanently - the blurry square sitting inside the canopy. Surfaces that declare no
       // fade get 1 from the helper and render byte-identically to before.
       // in Tree-Sprite preview the stand-in is pinned opaque: the point of the toggle is to
       // inspect it at any zoom, not only past its oneMinusDistFade threshold.
       const _fa=view.treesprite?1:distFadeAlpha(tex,[cr[0],cr[1],cr[2]]);
       if(_fa<=0.004)continue;                       // under 1/255 - the engine draws nothing
       // autoSprite2 pivots the quad about the midpoints of its two SHORTEST edges - the
       // long axis stays fixed in world space and only the minor axis swings toward the eye
       // (tr_shade_calc.c Autosprite2Deform :665-807). On a tree card that long axis is the
       // vertical trunk, which is exactly the observed in-game behaviour: dead upright, yaw
       // only. Route to the engine-exact quad path instead of the centroid square stamp,
       // which is what made the sprite look low-res (one square at the surface radius,
       // ignoring the card's real aspect).
       // The card is built on SPRITE_PARALLEL_UPRIGHT axes (tr_sprite.c:151-157) rather than
       // autoSprite2's minor=major x forward. With a perfectly vertical major axis the two are
       // algebraically identical - (0,1,0) x f has a zero vertical component either way - so this
       // is engine-faithful, but pinning `up` to world-up makes it structurally impossible for the
       // card to acquire roll, and it sidesteps the major-parallel-to-view degeneracy. The visible
       // tilt was NOT the axes though: it came from mapping the quad with ONE ctx.transform, an
       // affine that cannot represent perspective, so a tall card away from screen centre sheared
       // its bottom edge. drawQuadPersp is the mortar_dirthit path - depth-adaptive strips, exact
       // near-plane clip, seam-free compositing - so the card stays upright under any pitch.
       if(tex.autosprite2){
         const s2=DATA.surfRanges[si],V2=model,nv2=s2.vend-s2.vstart;
         const q2=(nv2>0&&nv2%4===0&&(s2.end-s2.start)===(nv2>>2)*2)?(nv2>>2):0;
         if(q2){
           ctx.globalAlpha=_fa;
           ctx.globalCompositeOperation=tex.additive?'lighter':'source-over';
           const f2=camBasis().f;
           let rx=f2[2],rz=-f2[0];const rl=Math.hypot(rx,rz)||1;rx/=rl;rz/=rl;   // horizontal right
           const EV2=[[0,1],[0,3],[0,2],[1,3],[1,2],[3,2]];                      // tr_shade_calc.c:661-668
           for(let q=0;q<q2;q++){
             const bs=(s2.vstart+q*4)*3;
             const Q=[0,1,2,3].map(k=>[V2[bs+k*3],V2[bs+k*3+1],V2[bs+k*3+2]]);
             let a0=1e30,a1=1e30,k0=0,k1=0;
             for(let j=0;j<6;j++){const u=Q[EV2[j][0]],w=Q[EV2[j][1]];
               const l=(u[0]-w[0])*(u[0]-w[0])+(u[1]-w[1])*(u[1]-w[1])+(u[2]-w[2])*(u[2]-w[2]);
               if(l<a0){a1=a0;k1=k0;a0=l;k0=j;}else if(l<a1){a1=l;k1=j;}}
             const md=(e2)=>{const u=Q[EV2[e2][0]],w=Q[EV2[e2][1]];
               return[(u[0]+w[0])*0.5,(u[1]+w[1])*0.5,(u[2]+w[2])*0.5];};
             const g0=md(k0),g1=md(k1);
             let TP=g1,BP=g0,hT=Math.sqrt(a1)*0.5,hB=Math.sqrt(a0)*0.5;
             if(g0[1]>g1[1]){TP=g0;BP=g1;hT=Math.sqrt(a0)*0.5;hB=Math.sqrt(a1)*0.5;}
             drawQuadPersp(img,
               [TP[0]-rx*hT,TP[1],TP[2]-rz*hT],[TP[0]+rx*hT,TP[1],TP[2]+rz*hT],
               [BP[0]-rx*hB,BP[1],BP[2]-rz*hB],[BP[0]+rx*hB,BP[1],BP[2]+rz*hB]);
           }
           ctx.globalAlpha=1;
         }
         continue;
       }
       const sp=project(C);if(sp[2]<=0)continue;
       const size=Math.max(4,Math.min(tex.lightglow?Math.max(W,H)*8:Math.min(W,H)*0.95,cr[3]*sp[3]*1.41));
       ctx.globalCompositeOperation=tex.additive?'lighter':'source-over';
       ctx.globalAlpha=_fa;
       ctx.drawImage(img,sp[0]-size/2,sp[1]-size/2,size,size);ctx.globalAlpha=1;}
     ctx.globalCompositeOperation='source-over';ctx.restore();}}}
// bone/tag markers + name labels (2D overlay in both render paths)
function drawTagOverlay(){
 const BP=bonePts(curWorld);const items=[];
 for(const tg of DATA.tags){
   const isTag=(tg.kind==='tag'||tg.origin);
   const isBone=(tg.kind==='bone'&&!tg.origin);
   if(filterMode==='tag'&&!isTag)continue;
   if(filterMode==='bone'&&!isBone)continue;
   if(!view.nodes&&!view.labels)continue;
   if(hidden.has(tg.idx))continue;
   const i=tg.idx;const sp=project([BP[i*3],BP[i*3+1],BP[i*3+2]]);
   if(sp[2]<=0)continue;items.push([sp[2],sp,tg]);}
 items.sort((p,q)=>{const ps=(p[2].idx===selectedIdx),qs=(q[2].idx===selectedIdx);
   if(ps!==qs)return ps?1:-1;   // selected marker always drawn last (on top)
   return q[0]-p[0];});
 for(const it of items){const sp=it[1],tg=it[2];
   const col=(tg.idx===selectedIdx)?TH.sel:(tg.origin?TH.origin:TH.tag);
   const r=(tg.idx===selectedIdx)?5.5:((tg.kind==='bone'&&!tg.origin)?2.5:4.5);
   if(view.nodes){ctx.beginPath();ctx.arc(sp[0],sp[1],r,0,7);ctx.fillStyle=col;ctx.fill();
     ctx.lineWidth=1;ctx.strokeStyle='rgba(0,0,0,.6)';ctx.stroke();}
   if(view.labels){ctx.font='11px ui-monospace,monospace';
     const tw=ctx.measureText(tg.name).width;ctx.fillStyle='rgba('+TH.labelbg+',.82)';
     ctx.fillRect(sp[0]+7,sp[1]-9,tw+8,15);ctx.fillStyle=col;ctx.fillText(tg.name,sp[0]+11,sp[1]+2);}}}
// SELECTED node always-on-top pass: the green (selected) tag/bone marker + its label are
// re-drawn AFTER drawParticles() at the end of draw(), so a highlighted node stays visible
// through every mesh, texture, emitter sprite and smoke puff (particles composite over the
// tag overlay in draw(), which otherwise hides the selection behind dense effects).
// Unselected markers keep the old occlusion behaviour. Viewer-UI aid only - no in-game
// equivalent, so no engine parity implications.
function drawSelectedTagTop(){
 if(selectedIdx<0||(!view.nodes&&!view.labels))return;
 let tg=null;for(const t of DATA.tags){if(t.idx===selectedIdx){tg=t;break;}}
 if(!tg||hidden.has(tg.idx))return;
 const isTag=(tg.kind==='tag'||tg.origin),isBone=(tg.kind==='bone'&&!tg.origin);
 if(filterMode==='tag'&&!isTag)return;     // same visibility rules as drawTagOverlay
 if(filterMode==='bone'&&!isBone)return;
 const BP=bonePts(curWorld);
 const sp=project([BP[tg.idx*3],BP[tg.idx*3+1],BP[tg.idx*3+2]]);
 if(sp[2]<=0)return;
 ctx.save();ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';
 if(view.nodes){ctx.beginPath();ctx.arc(sp[0],sp[1],5.5,0,7);ctx.fillStyle=TH.sel;ctx.fill();
   ctx.lineWidth=1;ctx.strokeStyle='rgba(0,0,0,.6)';ctx.stroke();}
 if(view.labels){ctx.font='11px ui-monospace,monospace';
   const tw=ctx.measureText(tg.name).width;ctx.fillStyle='rgba('+TH.labelbg+',.82)';
   ctx.fillRect(sp[0]+7,sp[1]-9,tw+8,15);ctx.fillStyle=TH.sel;ctx.fillText(tg.name,sp[0]+11,sp[1]+2);}
 ctx.restore();}
// SETSIZE wireframe: the object's world-space bounding box (setsize command or sibling .map).
// setsize/.map are in engine WORLD space (Z-up), and so is the model once its .skc bind pose is
// applied (the bind quat rotates the authored mesh into that world orientation - e.g. indycrate's
// Box02 carries [0.5,0.5,0.5,-0.5], a 120 deg turn about (1,1,1)). So the box needs only the same
// two operations the vertices already get: divide by load_scale (the viewer renders the .skd
// UNSCALED, whereas in-game verts/bounds are x load_scale - openmohaa tr_staticmodels.cpp:450-451),
// then the viewer's own Z-up->Y-up swap done in skin() (out=[x,z,y]). Hence world (x,y,z) -> viewer
// [x,z,y]/scale, with no per-model rotation: the bind pose already put the mesh in world space.
const SS_SCALE=(DATA.setsizeScale&&DATA.setsizeScale>1e-6)?DATA.setsizeScale:1;
function ssCorner(gx,gy,gz){
 // ...plus, whenever the placement dial is off zero, the same entity rotation the mesh picked
 // up at the skeleton root - otherwise the box would sit square while the model turned inside
 // it and stop reading as that model's bounds.
 if(EROT){const _c=erotV(gx,gy,gz);gx=_c[0];gy=_c[1];gz=_c[2];}
 return[gx/SS_SCALE,gz/SS_SCALE,gy/SS_SCALE];}                             // world (Z-up) -> viewer (Y-up)
function drawSetsizeBox(){if(!view.setsize||!DATA.setsize)return;
 const mn=DATA.setsize[0],mx=DATA.setsize[1];
 const C=[[mn[0],mn[1],mn[2]],[mx[0],mn[1],mn[2]],[mx[0],mx[1],mn[2]],[mn[0],mx[1],mn[2]],
          [mn[0],mn[1],mx[2]],[mx[0],mn[1],mx[2]],[mx[0],mx[1],mx[2]],[mn[0],mx[1],mx[2]]];
 const P=C.map(c=>project(ssCorner(c[0],c[1],c[2])));
 const E=[[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];
 ctx.save();ctx.strokeStyle=TH.setsize||'#ff5b6e';ctx.lineWidth=1.5;ctx.setLineDash([]);ctx.beginPath();
 for(const[a,b]of E){const pa=P[a],pb=P[b];if(pa[2]>0&&pb[2]>0){ctx.moveTo(pa[0],pa[1]);ctx.lineTo(pb[0],pb[1]);}}
 ctx.stroke();ctx.restore();}
let drag=false,lx=0,ly=0;
// coalesce redraws to one per animation frame, and render the fast (flat) view while
// the camera is moving, snapping back to full textures shortly after it settles.
let interacting=false,_drawReq=false,_settle=null;
function requestDraw(){if(_drawReq)return;_drawReq=true;requestAnimationFrame(()=>{_drawReq=false;draw();});}
function poke(){interacting=true;requestDraw();if(_settle)clearTimeout(_settle);
 _settle=setTimeout(()=>{interacting=false;draw();},150);}
cv.addEventListener('mousedown',e=>{drag=true;lx=e.clientX;ly=e.clientY;});
window.addEventListener('mouseup',()=>{if(drag){drag=false;interacting=false;if(_settle)clearTimeout(_settle);draw();}});
window.addEventListener('mousemove',e=>{if(!drag)return;
 const mdx=e.clientX-lx, mdy=e.clientY-ly;
 // rotate the drag by the camera roll so screen up/down always maps to look up/down (and
 // left/right to yaw) in the tilted view, regardless of how far Q/E have rolled the camera.
 const cr=Math.cos(roll),sr=Math.sin(roll), rdx=cr*mdx-sr*mdy, rdy=sr*mdx+cr*mdy;
 yaw-=rdx*0.01;
 pitch+=(camMode==='free'?-1:1)*rdy*0.01;
 // full free orbit: no vertical clamp - the model rolls continuously over the top/bottom
 // poles and can be spun in any direction as many times as wanted (no hemisphere cap).
 lx=e.clientX;ly=e.clientY;interacting=true;requestDraw();});
cv.addEventListener('wheel',e=>{e.preventDefault();
 if(camMode==='free'&&eye){const b=camBasis(),step=-Math.sign(e.deltaY)*rad*0.12;
   eye[0]+=b.f[0]*step;eye[1]+=b.f[1]*step;eye[2]+=b.f[2]*step;}  // dolly along view
 else{dist*=(1+Math.sign(e.deltaY)*0.1);dist=Math.max(rad*1.1,Math.min(rad*18,dist));}
 poke();},{passive:false});
const keysDown=new Set();
let panX=0,panY=0;
// keys the fly camera consumes (so the page doesn't scroll on Space etc.)
const FLY_KEYS=['w','a','s','d','q','e','c',' ',
                'W','A','S','D','Q','E','C',
                'ArrowUp','ArrowDown','ArrowLeft','ArrowRight'];
window.addEventListener('keydown',e=>{
 if(e.key==='r'||e.key==='R'){yaw=0.7;pitch=-0.4;roll=0;dist=rad*2.6;panX=0;panY=0;cx=cx0;cy=cy0;cz=cz0;
   eye=null;if(camMode==='free')enterFreeLook();selectedIdx=-1;if(typeof restyle==='function')restyle();draw();return;}
 keysDown.add(e.key);
 if(view.wasd&&FLY_KEYS.includes(e.key))e.preventDefault();
});
window.addEventListener('keyup',e=>keysDown.delete(e.key));
window.addEventListener('blur',()=>keysDown.clear());
// MOHRadiant-style fly camera: W/S forward-back, A/D strafe, Q/E roll (tilt),
// Space/C rise-lower. Runs while keys are held; renders fast (flat) during motion.
let _wasFlying=false;
(function flyLoop(){
 requestAnimationFrame(flyLoop);
 if(view.wasd&&keysDown.size){
  if(!eye)enterFreeLook();
  const mv=rad*0.02, tn=0.03, k=s=>keysDown.has(s), b=camBasis();
  const F=(k('w')||k('W')||k('ArrowUp'))?1:(k('s')||k('S')||k('ArrowDown'))?-1:0;
  const R=(k('d')||k('D'))?1:(k('a')||k('A'))?-1:0;
  const U=(k(' ')?1:0)-((k('c')||k('C'))?1:0);
  // roll the strafe (right) and rise (up) axes about the forward axis so A/D and Space/C move along
  // the tilted screen's horizontal/vertical (matching the mouse-look roll compensation). Forward is
  // unaffected by roll; at roll 0 this reduces exactly to the old horizontal-strafe / world-up.
  const cr=Math.cos(roll),sr=Math.sin(roll);
  const rollv=v=>{const fx=b.f,cx=fx[1]*v[2]-fx[2]*v[1],cy=fx[2]*v[0]-fx[0]*v[2],cz=fx[0]*v[1]-fx[1]*v[0],
    d=(fx[0]*v[0]+fx[1]*v[1]+fx[2]*v[2])*(1-cr);
    return[v[0]*cr-cx*sr+fx[0]*d,v[1]*cr-cy*sr+fx[1]*d,v[2]*cr-cz*sr+fx[2]*d];};
  const rr=rollv(b.r), uu=rollv([0,1,0]);
  if(F){eye[0]+=b.f[0]*mv*F;eye[1]+=b.f[1]*mv*F;eye[2]+=b.f[2]*mv*F;}
  if(R){eye[0]+=rr[0]*mv*R;eye[1]+=rr[1]*mv*R;eye[2]+=rr[2]*mv*R;}
  if(U){eye[0]+=uu[0]*mv*U;eye[1]+=uu[1]*mv*U;eye[2]+=uu[2]*mv*U;}
  if(k('ArrowLeft'))yaw+=tn;
  if(k('ArrowRight'))yaw-=tn;
  if(k('q')||k('Q'))roll-=tn;   // tilt left
  if(k('e')||k('E'))roll+=tn;   // tilt right
  interacting=true;_wasFlying=true;draw();}
 else if(_wasFlying){_wasFlying=false;interacting=false;draw();}
})();
function tbtn(id,key){const el=document.getElementById(id);el.onclick=()=>{view[key]=!view[key];el.classList.toggle('on',view[key]);draw();};}
tbtn('bTex','tex');tbtn('bMesh','mesh');tbtn('bWire','wire');tbtn('bNodes','nodes');tbtn('bLbl','labels');tbtn('bSize','setsize');tbtn('bGlow','tilt');tbtn('bTreeSpr','treesprite');
// Face Anims re-skins rather than just redrawing: the toggle changes vertex positions,
// not what is painted, so it has to go back through applyFrame().
(function(){const el=document.getElementById('bFace');if(!el)return;
  el.onclick=()=>{view.face=!view.face;el.classList.toggle('on',view.face);applyFrame();};})();
// Corona orbit / Tree Sprite are shader-specific: each only means anything on a model that
// actually carries the surface it acts on. Rather than greying them out they are REMOVED from
// the row, so the Display panel only ever offers controls that do something to what is loaded.
(function(){
  const drop=(id,keep)=>{const el=document.getElementById(id);
    if(el&&!keep){el.classList.remove('on');el.style.display='none';}};
  drop('bGlow',    DATA.surfRanges.some(s=>s.lightglow));   // DEFORM_LIGHTGLOW corona
  drop('bTreeSpr', hasLodSprite);                           // autoSprite2 + oneMinusDistFade
})();
// disable the Setsizes toggle when there's no box to show. rev 62: that is no longer a
// permanent verdict - the setsize line's pencil can grow a box on a model that ships without
// one, so the greyed tooltip points at it and ssSyncBtn() (below) re-runs this decision
// whenever the synthetic box appears or is discarded.
(function(){const bs=document.getElementById('bSize');if(bs&&!DATA.setsize){bs.disabled=true;bs.style.opacity=0.4;bs.title='No setsize or .map bounding box for this model \u2013 use the pencil on the setsize line to add one';}})();
// disable the Texture toggle when NO surface resolved to a texture (e.g. models/miscobj/hammer,
// whose `surface all shader hammer` points at textures/models/items/hammer.tga - a texture that
// isn't shipped in any pak). hasTex is DATA.surfRanges.some(s=>s.tex||s.pulse); strip the default
// 'on' class too so the greyed button reads as off, matching the disabled Setsizes button.
//
// rev 63: not a verdict for the whole session any more. view.tex starts as hasTex - the HOST's
// own textures - so on an untextured host the fill was off AND unreachable, and an ATTACHED
// sprite could never paint however well its own texture resolved. texSyncBtn re-derives the
// state from the LIVE surface list, so attaching a muzzle flash to a bare .skd un-greys the
// button and switches the fill on; removing it puts both back.
function texSyncBtn(){
  const bt=document.getElementById('bTex');if(!bt)return;
  const live=(typeof LTEX!=='undefined'&&LTEX)?LTEX.some(t=>t&&(t.img||t.pulse)):hasTex;
  if(!hasTex){                       // host brought none: the attachment owns this button
    bt.disabled=!live;
    bt.style.opacity=live?'':'0.4';
    bt.title=live?'Show / hide resolved skin textures (1) \u2013 from the attached model; this one has none of its own'
                 :'No resolved texture for this model';
    if(view.tex&&!live)view.tex=false;
    else if(!view.tex&&live)view.tex=true;   // a texture nothing can show is not worth resolving
  }
  bt.classList.toggle('on',!!view.tex);
}
(function(){const bt=document.getElementById('bTex');if(bt&&!hasTex){bt.disabled=true;bt.style.opacity=0.4;bt.classList.remove('on');bt.title='No resolved texture for this model';}})();
// camera mode: free-look (fly) vs tag-lock (orbit a clicked tag)
(function(){
  const bf=document.getElementById('bFree'), bl=document.getElementById('bLock');
  function setMode(m){camMode=m;view.wasd=(m==='free');
    bf.classList.toggle('on',m==='free');bl.classList.toggle('on',m==='lock');
    const hl=document.getElementById('camHelpLock'),hf=document.getElementById('camHelpFree');
    if(hl)hl.style.display=(m==='lock')?'':'none';
    if(hf)hf.style.display=(m==='free')?'':'none';
    if(m==='free'){enterFreeLook();}
    else{eye=null;panX=0;panY=0;const bp=bonePts(curWorld);
      if(selectedIdx>=0){cx=bp[selectedIdx*3];cy=bp[selectedIdx*3+1];cz=bp[selectedIdx*3+2];}
      else{cx=cx0;cy=cy0;cz=cz0;}}
    draw();}
  bf.onclick=()=>setMode('free');
  bl.onclick=()=>setMode('lock');
  setMode('lock');   // tag-lock (orbit) is the default camera
})();
// tag/bone filter tab buttons
(function(){
  const ftag=document.getElementById('bFilterTag');
  const fbone=document.getElementById('bFilterBone');
  ftag.onclick=()=>{filterMode='tag';ftag.classList.add('on');fbone.classList.remove('on');refreshList();draw();};
  fbone.onclick=()=>{filterMode='bone';fbone.classList.remove('on');fbone.classList.add('on');
    filterMode='bone';ftag.classList.remove('on');fbone.classList.add('on');refreshList();draw();};
})();
document.getElementById('ttl').textContent=__TITLE_JS__;
const nTags=DATA.tags.filter(t=>t.kind==='tag'||t.origin).length,nOrig=DATA.tags.filter(t=>t.origin).length;window.__amStats=function(){document.getElementById('stats').innerHTML=DATA.bones.length+' bones \u00b7 '+DATA.verts.length+' verts \u00b7 '+DATA.tris.length+' tris<br>'+((window.ACAT?ACAT.anims.length:DATA.anims.length))+' anims \u00b7 '+nTags+' tags ('+nOrig+' origin)'+((DATA.emitters&&DATA.emitters.length)?' \u00b7 '+DATA.emitters.length+' fx':'')+((DATA.morphNames&&DATA.morphNames.length)?' \u00b7 '+DATA.morphNames.length+' morph targets':'')+(DATA.classname?'<br>classname: '+String(DATA.classname).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):'');};
// ---- SETSIZE editor -------------------------------------------------------
// setsize used to be the last <br> line inside #stats. It now lives in its own
// #setsizeLine element so an __amStats re-render (which fires whenever an
// animation streams in from the launcher) can never wipe an open editor. By
// default it reads as plain text with a small pencil toggle after it; toggled
// on (green .on, like the Display toggles) it swaps the two ( x y z ) triples
// for number fields styled like the attach-to-bone offset/angles inputs and
// live-edits DATA.setsize, so the red Setsizes box (drawSetsizeBox, painted
// only while that toggle is on) tracks every keystroke. Toggled off it discards
// the edits and restores the file-original values captured once here at load.
// rev 62: a model that declares no `setsize` - and has no sibling .map to borrow a box
// from - is no longer a dead line. It reads a DIMMED `setsize ( 0 0 0 ) ( 0 0 0 )` (dim
// because those zeros are the viewer's placeholder, not something the file said) and its
// pencil MATERIALISES that box: DATA.setsize is created, the Display > Setsizes toggle is
// un-greyed and switched on so the red wireframe tracks every keystroke, and the numbers
// can be dialled in and copied straight out as a `setsize` line for the .tik. Closing the
// pencil takes the synthetic box away again and re-greys the toggle - the same "discard"
// contract the revert path gives a model that shipped with one.
const SS_ORIG=DATA.setsize?JSON.parse(JSON.stringify(DATA.setsize)):null;
const SS_SYNTH=!DATA.setsize;               // no box in the file: the pencil creates one
let ssEdit=false;
// Set when opening the editor found the Setsizes toggle OFF and switched it on, so closing
// can hand the view back exactly as it found it. Only ever undoes the viewer's OWN auto-on:
// a toggle the user pressed themselves while editing is left alone.
let ssAutoOn=false;
// Keep the Display panel's Setsizes toggle honest about whether there is a box to draw.
// `on` undefined = just re-derive the enabled/disabled state; true/false also drives the
// view flag, so opening the editor on a boxless model shows the box without a second click.
function ssSyncBtn(on){
  const bs=document.getElementById('bSize');if(!bs)return;
  bs.disabled=!DATA.setsize;
  bs.style.opacity=DATA.setsize?'':'0.4';
  bs.title=DATA.setsize
    ?(SS_SYNTH?'Wireframe box of the setsize you are editing (4) \u2013 this model declares none of its own'
              :'Wireframe box of the model\u2019s setsize / .map bounding box (4)')
    :'No setsize or .map bounding box for this model \u2013 use the pencil on the setsize line to add one';
  if(on!==undefined)view.setsize=!!on&&!!DATA.setsize;
  else if(!DATA.setsize)view.setsize=false;
  bs.classList.toggle('on',view.setsize);
}
function renderSetsize(){
  const host=document.getElementById('setsizeLine');
  if(!host)return;
  host.innerHTML='';
  // boxless model: fall back to the ( 0 0 0 ) ( 0 0 0 ) placeholder so there is always a
  // line to read and a pencil to press. DATA.setsize itself stays null until that press.
  const mn=DATA.setsize?DATA.setsize[0]:[0,0,0],mx=DATA.setsize?DATA.setsize[1]:[0,0,0];
  if(!ssEdit){
    const t=document.createElement('span');
    t.textContent='setsize ('+mn.join(' ')+') ('+mx.join(' ')+') ';
    if(!DATA.setsize){
      t.style.opacity='0.55';
      t.title='This model declares no setsize, and no sibling .map supplies one. '
             +'Click the pencil to start a box at ( 0 0 0 ) ( 0 0 0 ).';}
    host.appendChild(t);
  }else{
    // number field + nowrap group, mirroring attPanelRender's num()/grp() so it
    // matches the attach-to-bone offset / angles editors exactly.
    const num=(val,set)=>{
      const e=document.createElement('input');e.type='text';e.value=String(val);
      e.style.cssText='width:30px';
      e.title='setsize value \u2013 edits the red box live; reverts when you close the editor';
      e.onchange=()=>{const v=parseFloat(e.value);const nv=isFinite(v)?v:0;
        set(nv);e.value=String(nv);draw();};   // draw() repaints the Setsizes box
      return e;};
    const grp=()=>{const g=document.createElement('span');
      g.style.cssText='white-space:nowrap;margin-right:4px';host.appendChild(g);return g;};
    host.appendChild(document.createTextNode('setsize '));
    const g1=grp();g1.appendChild(document.createTextNode('('));
    for(let k=0;k<3;k++)g1.appendChild(num(mn[k],v=>{DATA.setsize[0][k]=v;}));
    g1.appendChild(document.createTextNode(')'));
    const g2=grp();g2.appendChild(document.createTextNode('('));
    for(let k=0;k<3;k++)g2.appendChild(num(mx[k],v=>{DATA.setsize[1][k]=v;}));
    g2.appendChild(document.createTextNode(')'));
  }
  const b=document.createElement('button');
  b.textContent='\u270e';                       // lower-right pencil = the edit glyph
  b.className=ssEdit?'on':'';                    // green while editing
  b.style.cssText='padding:0 6px;margin-left:2px;line-height:1.5;font-size:12px';
  b.title=ssEdit
    ?(SS_SYNTH?'Editing a setsize this model does not declare \u2013 click to discard it again'
              :'Editing setsize \u2013 click to discard changes and restore the file-original values')
    :(SS_SYNTH?'Add a setsize to this model \u2013 starts at ( 0 0 0 ) ( 0 0 0 ), un-greys the Setsizes toggle and shows the red box'
              :'Edit this model\u2019s setsize \u2013 shows the red Setsizes box and updates it live');
  b.onclick=()=>{
    ssEdit=!ssEdit;
    if(ssEdit){
      // OPENING. A boxless model first gets a zero box to type into; then - for every model,
      // declared box or not - the Setsizes toggle is un-greyed and switched on, because a box
      // you cannot see is not worth dialling numbers into. This used to fire only for the
      // synthetic case, which made the pencil behave differently depending on whether the .tik
      // happened to carry a setsize.
      if(!DATA.setsize)DATA.setsize=[[0,0,0],[0,0,0]];
      ssAutoOn=!view.setsize;                    // remember whether the box was ours to show
      ssSyncBtn(true);
    }else{
      // CLOSING. Values revert (file-original) or the synthetic box goes away entirely, and
      // the red box is hidden again IF opening is what revealed it - leaving a toggle the user
      // never pressed switched on would be the same inconsistency in the other direction.
      if(SS_ORIG){for(let i=0;i<2;i++)for(let k=0;k<3;k++)DATA.setsize[i][k]=SS_ORIG[i][k];}
      else DATA.setsize=null;                    // synthetic: nothing left to draw
      ssSyncBtn((ssAutoOn&&view.setsize)?false:undefined);
      ssAutoOn=false;
    }
    draw();
    renderSetsize();
  };
  host.appendChild(b);
}
// Highlighting a row of these editor fields and copying it pastes VERTICALLY, because
// Chrome serialises a selection that spans <input> controls with a line break after
// every field. This handler catches copy (Ctrl+C and right-click Copy both fire it)
// whenever the selection actually spans one of the editors, and hands the clipboard a
// flat one-line string built from the live field values instead, in MOHAA .tik spacing:
//   * setsize (while its editor is open) -> 'setsize ( x y z ) ( x y z )'
//   * the placement angles (ditto)       -> 'angles ( pitch yaw roll )'
//   * each attach-to-bone row touched    -> 'scale s offset ( x y z ) angles ( x y z )'
// A selection inside a single field reads as collapsed to the Selection API, and copies
// anywhere else on the page never intersect these elements, so both are left untouched.
document.addEventListener('copy',ev=>{
  const sel=window.getSelection?window.getSelection():null;
  if(!sel||!sel.rangeCount||sel.isCollapsed||!ev.clipboardData)return;
  const inRange=node=>{if(!node)return false;
    for(let i=0;i<sel.rangeCount;i++){const r=sel.getRangeAt(i);
      if(r.intersectsNode?r.intersectsNode(node):node.contains(r.commonAncestorContainer))return true;}
    return false;};
  // setsize editor (only while it is open)
  const ss=document.getElementById('setsizeLine');
  if(ssEdit&&DATA.setsize&&inRange(ss)){
    const mn=DATA.setsize[0],mx=DATA.setsize[1];
    ev.clipboardData.setData('text/plain','setsize ( '+mn.join(' ')+' ) ( '+mx.join(' ')+' )');
    ev.preventDefault();return;}
  // placement-angle editor (only while its pencil is open, i.e. the readout holds 3 inputs)
  const agv=document.getElementById('angslv');
  if(agv&&inRange(agv)){
    const ai=agv.getElementsByTagName('input');
    if(ai.length===3){
      ev.clipboardData.setData('text/plain',
        'angles ( '+ai[0].value+' '+ai[1].value+' '+ai[2].value+' )');
      ev.preventDefault();return;}}
  // attach-to-bone rows: one flat line per attachment the selection touches. The 7 text
  // inputs in a box are, in DOM order, scale then offset(x,y,z) then angles(pitch,yaw,roll).
  const al=document.getElementById('attList');
  if(inRange(al)){
    const boxes=al.getElementsByClassName('attBox'),lines=[];
    for(let b=0;b<boxes.length;b++){if(!inRange(boxes[b]))continue;
      const ins=boxes[b].getElementsByTagName('input');
      if(ins.length>=7)lines.push('scale '+ins[0].value
        +' offset ( '+ins[1].value+' '+ins[2].value+' '+ins[3].value+' )'
        +' angles ( '+ins[4].value+' '+ins[5].value+' '+ins[6].value+' )');}
    if(lines.length){ev.clipboardData.setData('text/plain',lines.join('\n'));ev.preventDefault();}}
});
renderSetsize();
// (tag count replaced by filter tabs)
const tl=document.getElementById('taglist');
const sorted=DATA.tags.slice().sort((a,b)=>{const k=t=>t.origin?0:(t.kind==='tag'?1:2);return k(a)-k(b)||a.name.localeCompare(b.name);});
for(const tg of sorted){
const d=document.createElement('div');d.className='tag';
 d.dataset.tagview=(tg.kind==='tag'||tg.origin)?'1':'';   // origins live in the Tags view
 d.dataset.boneview=(tg.kind==='bone'&&!tg.origin)?'1':''; // bones only (origins excluded)
 const t=curWorld.T[tg.idx];
 const dot=document.createElement('span');dot.className='dot';
 const nm=document.createElement('span');nm.className='nm';nm.textContent=tg.name;
 nm.insertBefore(dot,nm.firstChild);
 const co=document.createElement('span');co.className='co';
 co.textContent=t[0].toFixed(0)+' '+t[1].toFixed(0)+' '+t[2].toFixed(0);
 d.appendChild(nm);d.appendChild(co);
 d.title='MOHAA coords (x y z): '+t.map(v=>v.toFixed(1)).join(' ');
 d._tg=tg;d._dot=dot;d._nm=nm;
 // click the dot -> toggle this item's visibility; shift-click -> hide/show ALL
 dot.onclick=(ev)=>{ev.stopPropagation();
   if(ev.shiftKey){
     const set=DATA.tags.filter(t=>filterMode==='tag'?(t.kind==='tag'||t.origin):(t.kind==='bone'&&!t.origin)).map(t=>t.idx);
     const vis=set.filter(i=>!hidden.has(i)).length, hid=set.length-vis;
     if(vis>hid){set.forEach(i=>hidden.add(i));}      // mostly visible -> hide all
     else{set.forEach(i=>hidden.delete(i));}           // mostly/all hidden -> show all
   } else {
     if(hidden.has(tg.idx))hidden.delete(tg.idx);else hidden.add(tg.idx);
   }
   restyle();draw();};
 // click the row -> select (recenter in tag-lock); click again -> deselect
 d.onclick=()=>{
   if(selectedIdx===tg.idx){selectedIdx=-1;restyle();draw();return;}
   selectedIdx=tg.idx;const bp=bonePts(curWorld);
   cx=bp[tg.idx*3];cy=bp[tg.idx*3+1];cz=bp[tg.idx*3+2];panX=0;panY=0;
   restyle();draw();};
 tl.appendChild(d);}
function restyle(){
 tl.querySelectorAll('.tag').forEach(el=>{
   const tg=el._tg;const sel=(tg.idx===selectedIdx);const hid=hidden.has(tg.idx);
   const col=hid?'var(--hidden)':sel?'var(--sel)':tg.origin?'var(--origin)':'var(--tag)';
   el._dot.style.background=col;
   el._nm.style.color=hid?'var(--dim)':sel?'var(--sel)':tg.origin?'var(--origin)':'var(--txt)';
   el.classList.toggle('sel',sel);
 });
}
function refreshList(){tl.querySelectorAll('.tag').forEach(el=>el.style.display=((filterMode==='tag'?el.dataset.tagview:el.dataset.boneview))?'':'none');}
restyle();refreshList();
const animBtn=document.getElementById('animBtn'),animMenu=document.getElementById('animMenu'),
      animPath=document.getElementById('animPath');
const scrub=document.getElementById('scrub'),frlab=document.getElementById('frlab');
const playBtn=document.getElementById('play'),speed=document.getElementById('speed'),fpsl=document.getElementById('fps');
// Default to the FIRST animation (index 0, usually `idle`) instead of the bind pose, so
// models whose whole look lives in init{client{}} / an idle anim (grenexp_base and the other
// fx dummies) come up on a real, replayable anim - not the -1 "bind pose (rest)" sentinel,
// which let the effect auto-run once but left Play unable to restart it. The bind-pose row is
// only offered (and -1 only used) when the model has NO animations at all (see amRender).
let curAnim=(DATA.anims&&DATA.anims.length)?0:-1,curFrame=0,playing=false,acc=0,last=0;
// GLOBAL freeze: when true, both the animation tick and the effect/emitter clock stop
// advancing, so the whole model (frames + particles) holds in place. Independent of the
// Play toggle (which only starts/stops frame playback).
let paused=false;
function animHasBody(a){
 // A face-only record is built with empty pose overrides on every frame, so "does any
 // frame drive a bone" separates the two kinds without needing a flag in the payload.
 if(!a||!a.frames)return false;
 for(let i=0;i<a.frames.length;i++){for(const k in a.frames[i])return true;}
 return false;}

function updateFaceBtn(){
 const el=document.getElementById('bFace');if(!el)return;
 const a=curAnim<0?null:DATA.anims[curAnim];
 // Shown only while a BODY animation is carrying a face layer. On a face-only track the
 // morph data IS the animation - switching it off would leave a still head and look broken -
 // and on a model with no morph targets the control means nothing at all.
 el.style.display=(a&&a.mw&&animHasBody(a))?'':'none';}

function applyFrame(){
 // Facial tracks carry "mw" (per-frame blend-shape weights). Two shapes reach here: a
 // face-ONLY record (empty pose overrides, so the skeleton holds its bind pose) and a
 // BODY record with a face layer attached - either from the same .skc's own morph
 // channels or from its MORPH sibling. The engine plays exactly this way, filling
 // separate blend slots and accumulating morph weights across both
 // (skeletor.cpp:409-503, GetMorphWeightFrame :1105-1146).
 const _a=curAnim<0?null:DATA.anims[curAnim];
 const _faceOnly=!!(_a&&_a.mw&&!animHasBody(_a));
 curMorphW=(_a&&_a.mw&&(view.face||_faceOnly))?(_a.mw[curFrame]||_a.mw[0]||null):null;
 updateFaceBtn();
 if(curAnim<0){curWorld=worldFromPose(null);}
 else{const fr=_a.frames[curFrame];const over={};for(const k in fr)over[+k]=fr[k];curWorld=worldFromPose(over);}
 // Surface state is a pure function of the displayed frame, so it is recomputed HERE -
 // the one place every frame change goes through (playback tick, scrub drag, arrow-key
 // step, selectAnim, Reset). Cheap: a fold over one animation's command list.
 try{const _hb=hiddenSurf.size;animSurfFold();surfApply();
     if(hiddenSurf.size!==_hb||surfEl){surfCountRender();if(surfEl)surfMenuRender();}}catch(e){}
 modelBase=skin(curWorld);buildNormals();model=attAppend(modelBase);applyFlap();if(GLR)GLR.markDirty();frlab.textContent='frame '+curFrame;draw();}
// ---- ANIMATION CATALOG + DRILL-DOWN MENU -----------------------------------
// DATA.animCat is the model's full animation reach as resolved by
// mohaa_textures.build_anim_catalog: every $include chain, every per-file $path
// scope and every `includes <map>{}` group, with nodes referenced BY INDEX so a
// file pulled in by forty mission groups is stored once and shown forty times.
// DATA.anims holds only the animations whose pose data is actually in memory;
// a catalogue entry gains `.ai` (its index into DATA.anims) the moment it is
// built. Everything else is a name plus a .skc path until it is clicked.
// A bare .skd (or any model opened without a catalogue) synthesises a flat
// one-node catalogue so there is a single code path below.
//
// ONE panel, ever. Opening a category replaces the list in place and pushes the
// node on a stack; Up One Level pops it. A cascade of side-by-side panels was
// unusable once a model reached forty groups deep in mission includes - the
// submenus covered the panel they grew out of.
const ACAT=(DATA.animCat&&DATA.animCat.anims&&DATA.animCat.anims.length)?DATA.animCat:{
  anims:DATA.anims.map((a,i)=>({n:a.name,s:'',ai:i})),
  nodes:[{n:'animations',a:DATA.anims.map((a,i)=>i),k:[],c:DATA.anims.length}],root:0};
if(!DATA.animCat){ACAT.anims.forEach((e,i)=>{e.ai=i;});}
// published so the header's stats line (defined further up, before the catalogue
// exists) can read the CATALOGUE total rather than the baked subset; calling it
// here is also the line's first render.
window.ACAT=ACAT;if(window.__amStats)window.__amStats();
const ANIM_DIR=DATA.animDir||'';
const AM_W=300, AM_GAP=6, AM_MAXHITS=400;
let amEl=null,amBody=null,amSearch=null,amHeadTxt=null,amHeadCnt=null,amUpBtn=null;
let amStack=[],amFilter='',amRows=[],amHot=-1;
// id -> why it failed. Session-scoped, so a red dot survives closing and reopening
// the menu or browsing away and back; an id is cleared only when it finally loads.
const AM_FAIL={};

// ===== attachmodels =======================================================
// Rigid models hung off a bone. Geometry is resolved by the LAUNCHER out of the paks
// (MOHAA binds the whole entity to a tag, so an attachment is never skinned - one tag
// matrix carries it) and arrives as at<key>.js, cached beside the page: picking the same
// weapon for a second bone costs nothing the second time.
//
// Launcher-only by construction. The page asks for the model list over the WebView2
// bridge on boot; opened straight in a browser there is no bridge, nothing answers, and
// the panel never appears.
const ATTGEO={};        // key -> {n,v,t,uv,sr,bb}   resolved geometry
const ATT=[];           // live attachments: {tag, key, path, scale, off:[x,y,z]}
let ATT_MODELS=null;    // model paths from the launcher; null = no bridge = panel hidden
const ATT_MAX=8;        // the engine's own ceiling on attached models
let ATT_VN=0;           // attachment vertices appended after the host's
const ATT_PEND={};      // path -> true while the launcher resolves it
const ATT_BUILT={};     // path -> key, for models already resolved this session
const ATT_KEYPATH={};   // key -> the pak path the launcher resolved it from
function attHost(){try{return window.chrome&&window.chrome.webview?window.chrome.webview:null;}catch(e){return null;}}
function attPost(m){const h=attHost();if(h){try{h.postMessage(m);return true;}catch(e){}}return false;}

window.MOHAA_ATTACH=function(key,rec){if(key&&rec)ATTGEO[key]=rec;};
window.MOHAA_ATTACH_MODELS=function(list){
  ATT_MODELS=Array.isArray(list)?list:[];
  try{attPanelInit();}catch(e){}};
window.MOHAA_ATTACH_LOAD=function(key,path,scale){
  // the sidecar is a plain <script src>, exactly like a built animation
  if(path)ATT_KEYPATH[key]=String(path).toLowerCase();
  if(ATTGEO[key]){attGeomReady(key);return;}
  if(!ANIM_DIR){attGeomFail(key,'no cache folder for this page');return;}
  const s=document.createElement('script');
  s.src=ANIM_DIR+'/at'+key+'.js?'+Date.now();
  s.onload=()=>{s.remove();ATTGEO[key]?attGeomReady(key)
                          :attGeomFail(key,'attachment file held no geometry');};
  s.onerror=()=>{s.remove();attGeomFail(key,'could not read the attachment file');};
  document.head.appendChild(s);};

function attGeomReady(key){
  // Bind on the PATH the launcher named. The old guess - turn "x.tik" into "x.skd" and
  // compare basenames - only held when a tik happened to share its model's name.
  // models/static/static_airtank.tik points at submodels/AIRTANK.skd, so nothing ever
  // matched: the geometry arrived and no slot claimed it, and the model simply never
  // appeared. The launcher knows the path it was asked for, so it just says so.
  const want=ATT_KEYPATH[key]||'';
  for(const a of ATT){
    if(a.key===key){a.ready=true;continue;}
    if(a.key||!a.path)continue;
    if(want&&a.path.toLowerCase()===want){
      a.key=key;a.ready=true;ATT_BUILT[a.path]=key;}}
  for(const p in ATT_PEND){if(ATT_PEND[p]===key)delete ATT_PEND[p];}
  attRebuild();
  try{attPanelRender();}catch(e){}}

function attGeomFail(key,msg){
  for(let i=ATT.length-1;i>=0;i--){if(ATT[i].key===key&&!ATT[i].ready)ATT.splice(i,1);}
  for(const p in ATT_PEND){if(ATT_PEND[p]===key)delete ATT_PEND[p];}
  try{amNote('attachment: '+(msg||'could not be built'),true);}catch(e){}
  try{attPanelRender();}catch(e){}}

// --- Stage 3/4 integration points -----------------------------------------
// attRebuild() recomputes each attachment's world vertices from its bone matrix and
// feeds them to the draw paths; attPanelInit/attPanelRender build the ANIMATION-section
// panel. Both land next. Until then ATT stays empty, nothing calls attRequest(), and the
// page renders exactly as it does today - the bridge and cache below are live and
// testable on their own.
// Shader render hints an attached surface carries over from its sidecar. Same names
// build_payload writes on a HOST surface, so mkSurfTex and every draw path treat the two
// identically - an attachment is just more surfaces once it is in LSR/LTEX.
const ATT_SR_KEYS=['additive','autosprite','autosprite2','lightglow','twosided',
                   'clamp','texrotate','fps','frames','atest','distfade','pulse'];
function attRebuild(){
  // Rebuild the LIVE arrays: base geometry first, then every ready attachment appended as
  // extra surfaces with their indices shifted past the host's vertices. Everything
  // downstream - painter sort, texture fill, wireframe, GL buffers - then treats an
  // attached weapon as just more of the model.
  const ready=ATT.filter(a=>a.ready&&ATTGEO[a.key]);
  if(!ready.length){
    LT=DATA.tris;LUV=DATA.uvs;LSR=DATA.surfRanges;LTEX=surfTex;ATT_VN=0;
  }else{
    const T=DATA.tris.slice(),UV=DATA.uvs?DATA.uvs.slice():[],SR=DATA.surfRanges.slice(),TX=surfTex.slice();
    let vbase=DATA.verts.length;
    for(const a of ready){
      const g=ATTGEO[a.key];
      a.vbase=vbase;a.vn=g.v.length;
      for(const s of (g.sr||[])){
        const st=T.length;
        for(let t=s.start;t<s.end;t++){const tr=g.t[t];T.push([tr[0]+vbase,tr[1]+vbase,tr[2]+vbase]);}
        const rec={name:s.name,start:st,end:T.length};
        if(s.tex)rec.tex=s.tex;
        // rev 63: forward the shader hints the sidecar now carries. This rebuild is the ONLY
        // path an attachment's surface takes into LSR/LTEX, so anything not copied here is
        // invisible to the renderer no matter what the sidecar holds - which is the second
        // half of why an attached muzzle flash drew as a flat opaque quad.
        for(const k of ATT_SR_KEYS)if(s[k])rec[k]=s[k];
        SR.push(rec);TX.push(mkSurfTex(rec));
      }
      for(const uv of (g.uv||[]))UV.push(uv[0],uv[1]);
      vbase+=g.v.length;
    }
    LT=T;LUV=UV;LSR=SR;LTEX=TX;ATT_VN=vbase-DATA.verts.length;
    // an attachment may have brought the page its first effect surface
    try{if(liveEffectSurf())startEffLoop();}catch(e){}
  }
  // ...and its first TEXTURE, on a host that resolved none of its own
  try{texSyncBtn();}catch(e){}
  applyFrame();                                  // re-skin so `model` gets the new tail
  if(typeof GLR!=='undefined'&&GLR&&GLR.rebuildSurfaces)GLR.rebuildSurfaces();
  try{attPanelRender();}catch(e){}
  try{draw();}catch(e){}}

// world = R_tag . (scale . local + offset) + T_tag. An attached entity is RIGID - MOHAA
// binds the whole thing to a tag - so one matrix carries it, and the final [X,Z,Y] swap
// matches skin() exactly so attachment and host end up in the same frame.
// MOHAA angle triple (pitch, yaw, roll in degrees) -> local->world rotation, built the
// engine's way: AngleVectors gives forward/right/up, AnglesToAxis negates right to get
// left, and the local->world matrix has those as its COLUMNS (q_math.c AngleVectors /
// AnglesToAxis).
//
// (0,-90,90) reproduces WEAPON_ATTACH_ROT = [0.5,-0.5,-0.5,0.5] EXACTLY - verified to
// 0.000000 against the quaternion solved in the first attempt, which mapped a weapon's
// muzzle to +X (character forward) and its magazine to -Z (straight down) through the
// tag_weapon_right orientation. MOHAA weapon meshes are authored muzzle-down-(-Y), so
// that correction is a property of the MODEL's authoring space, not of the tag - hence
// it is seeded for models/weapons/* and left at zero for everything else.
function attAngMat(a){
  const d=Math.PI/180,p=(a&&a[0]||0)*d,y=(a&&a[1]||0)*d,r=(a&&a[2]||0)*d;
  const sy=Math.sin(y),cy=Math.cos(y),sp=Math.sin(p),cp=Math.cos(p),sr=Math.sin(r),cr=Math.cos(r);
  const f =[cp*cy, cp*sy, -sp];
  const rt=[-sr*sp*cy+cr*sy, -sr*sp*sy-cr*cy, -sr*cp];
  const u =[cr*sp*cy+sr*sy, cr*sp*sy-sr*cy, cr*cp];
  return [f[0],-rt[0],u[0], f[1],-rt[1],u[1], f[2],-rt[2],u[2]];}

// Authoring-axis correction for weapon models, applied UNDER whatever the user types so
// the boxes read 0/0/0 when a rifle already sits correctly in the hand - which is what a
// script sees in-game, where attachmodel needs no angles at all.
//
// Measured at (90, 90, 0) on tag_weapon_right, not the (0,-90,90) that the first attempt's
// WEAPON_ATTACH_ROT converts to. Both are right for where they were applied: that quat went
// on the weapon's ROOT BONE inside a merged skeleton, so it was composed with the weapon's
// own bone chain; this one rotates the finished rigid mesh in tag space, which is a
// different point in the chain and therefore a different rotation.
// One frame conversion for EVERY model, now that each is posed by its own idle .skc.
// Solved from the mp44: it needed (90,90,0) against an identity bind, and its idle poses
// the mesh by (0,-90,90), so once that is applied the remainder is (90,90,0)*(0,-90,90)^-1
// = (180,90,-90). What is left is the difference between how this viewer composes the tag
// transform and how the engine does - a property of the renderer, not of any model, so it
// belongs here rather than in a per-model table.
// MEASURED, not derived. Predicting this from the idle pose did not survive contact with
// the viewer: after posing the mp44 by its own idle .skc the arithmetic said (180,90,-90)
// would leave it reading 0/0/0, and it still wanted (90,90,0) on top. Folding that in
// gives (-180,180,-180) - so the two 90s the prediction accounted for were already being
// carried elsewhere in the chain. The number that matters is the one a rifle actually sits
// correctly at, so this is calibrated against the mp44 in the hand and applied to every
// model; per-model differences stay the angle boxes' job.
const ATT_BASE_ANG=[-180,180,-180];
function attBaseAng(path){ return ATT_BASE_ANG.slice(); }
function attDefaultAng(path){ return [0,0,0]; }
function attMat3Mul(A,B){
  const o=new Array(9);
  for(let i=0;i<3;i++)for(let j=0;j<3;j++)
    o[i*3+j]=A[i*3]*B[j]+A[i*3+1]*B[3+j]+A[i*3+2]*B[6+j];
  return o;}

// ---- OFFSET UNITS ---------------------------------------------------------------------
// The offset boxes hold the number a .tik / script `attachmodel ... offset ( x y z )` line
// carries, which is in engine WORLD units. The viewer, though, renders the host .skd
// UNSCALED, so its world is 1/load_scale LARGER than the game's - the same mismatch
// drawSetsizeBox already corrects, and for the same reason (openmohaa
// tr_staticmodels.cpp:450-451 multiplies verts by the tik's setup `scale` at load). Dividing
// the offset by that factor is what makes a placement dialled in here paste straight into the
// game and land in the same spot; before this the boxes read ~1/load_scale too large and
// every number the viewer produced had to be converted by hand.
//
// CALIBRATED against two turrets, each placed by eye in the viewer and then in-game:
//   15cmcannon (tik `scale 0.52`)  viewer ( -4  233 -498 ) -> game ( -2   120  -257 )
//   20mmflak   (tik `scale 0.35`)  viewer ( 2.1 -512 185 ) -> game ( 0.7 -182.5 66.2 )
// Every axis of both lands within ~2 units of viewer*load_scale, and the two models' residuals
// fall on OPPOSITE sides of that prediction (cannon under, flak over) - eyeball error in the
// in-game placement rather than a second factor. The angles were IDENTICAL in both columns for
// both models, so the rotation chain was already right and only the offset was ever wrong.
//
// The attachment MESH deliberately gets no such correction: in-game the engine draws an
// attached model at the PARENT entity's scale, i.e. scale*load_scale*verts in game units,
// which is scale*verts in the viewer's own units - already what attAppend does below, and why
// the same `scale` value was correct in both places throughout the calibration.
const ATT_OFS=(DATA.setsizeScale&&DATA.setsizeScale>1e-6)?DATA.setsizeScale:1;
function attAppend(base){
  if(!ATT_VN||!curWorld)return base;
  const out=new Float32Array(base.length+ATT_VN*3);
  out.set(base,0);
  for(const a of ATT){
    const g=(a.ready&&ATTGEO[a.key])?ATTGEO[a.key]:null;
    if(!g||a.vbase==null)continue;
    const R=curWorld.R[a.tag],T2=curWorld.T[a.tag];
    if(!R||!T2)continue;
    // user angles ON TOP of the model's own authoring correction
    // world units in the boxes -> the viewer's unscaled model units for the maths
    const ao=a.off||[0,0,0],o=[ao[0]/ATT_OFS,ao[1]/ATT_OFS,ao[2]/ATT_OFS];
    const s=(+a.scale)||1,
          M=attMat3Mul(attAngMat(a.ang),attAngMat(a.bang||[0,0,0]));
    let w=a.vbase*3;
    for(let i=0;i<g.v.length;i++){
      const p=g.v[i];
      // scale, then the model's own angle correction, then a TAG-SPACE offset: the offset
      // should nudge along the bone's axes no matter how the model is spun, which is what
      // makes it usable for dialling a position in by hand.
      const lx=p[0]*s,ly=p[1]*s,lz=p[2]*s;
      const ox=M[0]*lx+M[1]*ly+M[2]*lz+o[0];
      const oy=M[3]*lx+M[4]*ly+M[5]*lz+o[1];
      const oz=M[6]*lx+M[7]*ly+M[8]*lz+o[2];
      out[w]  =R[0]*ox+R[1]*oy+R[2]*oz+T2[0];
      out[w+2]=R[3]*ox+R[4]*oy+R[5]*oz+T2[1];
      out[w+1]=R[6]*ox+R[7]*oy+R[8]*oz+T2[2];
      w+=3;
    }
  }
  return out;}

// Boot handshake. Only a launcher-hosted page has chrome.webview, so a page opened
// straight from disk never asks, never receives a list, and never shows the panel.
try{if(attHost())attPost('mohaa-attach-models');}catch(e){}

// Folder browser over the pak model tree, using the animation menu's own panel chrome
// (amPanel/amHead/amSearch/amBody/amItem) so it looks and drives the same: search at the
// top, green folders to drill through, Back to climb out, and a green dot on any model
// already resolved this session.
let attBrowseEl=null,attBrowseSlot=-1,attBrowseStack=[],attBrowseFilter='';
let attBack=null;       // full-window click catcher, mirroring #animMenu
let attBrowseBtn=null;  // the button the panel is anchored to, for re-fitting
function attTree(){
  if(attTree._t)return attTree._t;
  const root={d:{},f:[]};
  for(const p of (ATT_MODELS||[])){
    const parts=p.split('/');let n=root;
    for(let i=0;i<parts.length-1;i++){const k=parts[i];n.d[k]=n.d[k]||{d:{},f:[]};n=n.d[k];}
    n.f.push(p);
  }
  attTree._t=root;return root;}
function attStackOK(stack){
  if(!stack||!stack.length)return false;
  let n=attTree();
  for(const k of stack){if(!n.d[k])return false;n=n.d[k];}
  return true;}
function attNodeAt(stack){
  let n=attTree();for(const k of stack){if(!n.d[k])return n;n=n.d[k];}return n;}

function attBrowseClose(){
  if(attBrowseEl){attBrowseEl.remove();attBrowseEl=null;}
  if(attBack){attBack.remove();attBack=null;}
  attBrowseBtn=null;
  document.removeEventListener('keydown',attBrowseKey,true);
  attBrowseSlot=-1;attBrowseFilter='';}
function attBrowseKey(ev){
  if(ev.key==='Escape'){attBrowseClose();ev.preventDefault();ev.stopPropagation();return;}
  if(ev.key==='Backspace'&&attBrowseFilter===''){
    if(attBrowseStack.length){attBrowseStack.pop();attBrowseRender();}
    ev.preventDefault();ev.stopPropagation();return;}
  ev.stopPropagation();}

function attBrowsePlace(btn){
  // Same geometry as amPlace(): hang the panel off the LEFT edge of its button, tops
  // aligned, and fall back to the right side only if there is no room. position:fixed
  // rather than absolute-in-#attList, so it floats clear of the right-hand column
  // instead of being clipped by it and shoving the panel's own content around.
  if(!attBrowseEl||!btn)return;
  const r=btn.getBoundingClientRect(),vw=window.innerWidth,vh=window.innerHeight;
  let left=r.left-AM_GAP-AM_W;
  if(left<4)left=Math.min(r.right+AM_GAP,Math.max(4,vw-4-AM_W));
  if(left+AM_W>vw-4)left=Math.max(4,vw-4-AM_W);
  attBrowseEl.style.left=left+'px';
  mnFit(attBrowseEl,r,vh);}

function attBrowseOpen(idx,btn){
  attBrowseClose();
  attBrowseBtn=btn||null;
  if(!ATT_MODELS)return;
  attBrowseSlot=idx;attBrowseFilter='';
  // Reopen where we left off, like the animation menu - drilling into models/weapons,
  // closing to look at the model, and reopening lands back in weapons. Only when the
  // trail is empty or stale do we auto-descend: every pak path starts "models/", so the
  // raw root is one lone folder and opening on it wastes a click.
  if(!attStackOK(attBrowseStack)){
    attBrowseStack=[];
    for(;;){
      const n=attNodeAt(attBrowseStack),ks=Object.keys(n.d);
      if(ks.length===1&&n.f.length===0)attBrowseStack.push(ks[0]);
      else break;}}
  // Full-window backdrop, exactly like #animMenu. It is what makes a click anywhere else
  // close the menu - INCLUDING a click back on the button that opened it, which is how
  // the animation menu toggles. Doing this with a document mousedown watch instead meant
  // the close fired on mousedown and the button's own click then reopened it.
  attBack=document.createElement('div');
  attBack.style.cssText='position:fixed;left:0;top:0;width:100%;height:100%;z-index:70';
  attBack.onclick=(ev)=>{if(!attBrowseEl||!attBrowseEl.contains(ev.target))attBrowseClose();};
  document.body.appendChild(attBack);
  const host=attBack;
  attBrowseEl=document.createElement('div');attBrowseEl.className='amPanel';
  attBrowseEl.style.cssText='position:fixed;z-index:71';
  const h=document.createElement('div');h.className='amHead';
  const up=document.createElement('button');up.className='amUp';up.innerHTML='\u2190 Back';
  up.title='Go up one folder (Backspace)';
  up.onclick=(e)=>{e.stopPropagation();if(attBrowseStack.length){attBrowseStack.pop();attBrowseRender();}};
  const pt=document.createElement('span');pt.className='amPathTxt';pt.id='attPathTxt';
  const pc=document.createElement('span');pc.className='amCnt';pc.id='attPathCnt';
  h.appendChild(up);h.appendChild(pt);h.appendChild(pc);attBrowseEl.appendChild(h);
  const se=document.createElement('input');se.className='amSearch';se.type='text';
  se.placeholder='search all models\u2026';se.id='attSearch';
  se.oninput=()=>{attBrowseFilter=se.value.trim();attBrowseRender();};
  attBrowseEl.appendChild(se);
  const bd=document.createElement('div');bd.className='amBody';bd.id='attBrowseBody';
  attBrowseEl.appendChild(bd);
  attBrowseEl.addEventListener('mousedown',(ev)=>{
    if(ev.target===se||ev.target===bd)return;ev.preventDefault();});
  host.appendChild(attBrowseEl);
  attBrowsePlace(btn);
  document.addEventListener('keydown',attBrowseKey,true);
  attBrowseRender();se.focus();}

function attBrowseRender(){
  const bd=document.getElementById('attBrowseBody');if(!bd)return;
  bd.innerHTML='';
  const pt=document.getElementById('attPathTxt'),pc=document.getElementById('attPathCnt');
  const f=attBrowseFilter.toLowerCase();
  const mk=(cls,label,count,arrow,onclick)=>{
    const d=document.createElement('div');d.className='amItem'+(cls?' '+cls:'');
    const l=document.createElement('span');l.className='lbl';l.textContent=label;d.appendChild(l);
    if(count!=null&&count!==''){const c=document.createElement('span');c.className='cnt';
      c.textContent=count;d.appendChild(c);}
    if(arrow){const a=document.createElement('span');a.className='arw';a.textContent=arrow;d.appendChild(a);}
    d.onclick=onclick;bd.appendChild(d);return d;};
  const pick=(p)=>{
    const a=ATT[attBrowseSlot];if(!a){attBrowseClose();return;}
    a.path=p;a.ready=false;a.key=null;a.ang=attDefaultAng(p);a.bang=attBaseAng(p);
    attBrowseClose();
    if(ATT_BUILT[p]){          // resolved earlier this session - reuse, no rebuild
      a.key=ATT_BUILT[p];a.ready=!!ATTGEO[a.key];
      if(a.ready){attRebuild();return;}}
    amNote('resolving '+p+' \u2026');
    attRequest(p);attPanelRender();};
  if(f){
    const hits=(ATT_MODELS||[]).filter(p=>p.toLowerCase().indexOf(f)>=0).slice(0,400);
    if(pt)pt.textContent='search';
    if(pc)pc.textContent=hits.length+(hits.length>=400?'+':'');
    for(const p of hits)
      mk(ATT_BUILT[p]?'have':'',p.replace(/^models\//,''),
         p.toLowerCase().endsWith('.tik')?'tik':'skd',null,()=>pick(p));
    if(!hits.length)mk('','no model matches that','',null,()=>{});
    return;}
  const n=attNodeAt(attBrowseStack);
  if(pt)pt.textContent='models'+(attBrowseStack.length?'/'+attBrowseStack.join('/'):'');
  if(pc)pc.textContent=String(Object.keys(n.d).length+n.f.length);
  for(const k of Object.keys(n.d).sort())
    mk('grp',k,String(Object.keys(n.d[k].d).length+n.d[k].f.length),'\u203a',
       ()=>{attBrowseStack.push(k);attBrowseRender();});
  for(const p of n.f.slice().sort())
    mk(ATT_BUILT[p]?'have':'',p.split('/').pop(),
       p.toLowerCase().endsWith('.tik')?'tik':'skd',null,()=>pick(p));
  // the list just changed height - re-fit so a deep folder cannot run off the bottom
  if(attBrowseBtn)attBrowsePlace(attBrowseBtn);}

// ===== surface visibility =================================================
// `surface <name> +nodraw` in script, e.g. local.engineer surface hedgebomb "+nodraw" -
// the surface disappears entirely, mesh and texture both. hiddenSurf already drives every
// draw path (2D fill, autosprite, GL); this just gives it a UI.
//
// THREE sources feed hiddenSurf and they have to stay separable, because Reset has to put
// each one back the way it was:
//   TIK_NODRAW  - what the .tik turns off at SPAWN (dday_ranger_private: the twelve bang*
//                 surfaces). Seeded up where surfIdxByName is defined, before first draw.
//   USER_NODRAW - surfaces the user turned off by hand.
//   USER_SHOW   - surfaces in TIK_NODRAW the user turned back ON to look at them.
// User hides are tracked SEPARATELY from hiddenSurf because resetModel() wipes that set to
// restore the surface state an animation's own +nodraw commands may have changed. Without
// their own record, pressing Reset (or switching animation) would silently un-hide
// everything the user had turned off - and, now, silently re-hide anything they revealed.
const USER_NODRAW=new Set();
const USER_SHOW=new Set();
// ---- animation-owned surface state -------------------------------------------
// An animation's own `surface <n> +/-nodraw` server commands OUTRANK both the tik's spawn
// state and the user's hides, for as long as that animation is the selected one.
// bangalore_assembly is a pure stage machine - 32 commands across 12 surfaces turning three
// loose pipe sections into a double, then a triple, then the planted charge - so whatever
// was set before has to give way or the assembly renders as every stage at once.
//
// The state is FOLDED from frame 0 on every applyFrame rather than accumulated as frames
// tick past. Incremental firing is only correct if each frame is visited in order exactly
// once; scrubbing, seeking, Loop wrap and dropped frames all break that, and nothing puts
// it back. Folding makes the surface state a pure function of the displayed frame, which is
// also what the engine has - it re-evaluates from the animation's command list, not from
// whatever happened to fire.
const ANIM_SURF=new Map();      // surface index -> nodraw, as the CURRENT frame dictates
const ANIM_SURF_OVR=new Map();  // index -> the folded value the user overrode by hand
// Every surface the animation names ANYWHERE in its command list, whether or not a command
// for it has fired yet. This is the group the animation choreographs, and the user's own
// hides are suspended across the whole group for the whole run - not just from the frame
// each surface is first mentioned.
//
// It has to be the whole group, because these command lists are written against the tik's
// spawn state and only say what CHANGES. bangalore_assembly never turns bang01 off at frame
// 0; it just assumes bang01 is off, because `surface bang* +nodraw` in init{server{}}
// already made it so. A user who had switched bang01 on by hand would otherwise see the
// finished triple hanging in the air through the whole first half of the assembly.
const ANIM_OWNED=new Set();
// An index the animation is choreographing AND the user has not taken back by hand.
function animOwns(i){return ANIM_OWNED.has(i)&&!ANIM_SURF_OVR.has(i);}
function animSurfTrigger(at,nf){
  // TIKI frame keys (TIKI_ParseAnimationCommands, tiki_parse.cpp:192-226): entry/first fire
  // as the animation starts, every on all frames, last/end on the final one.
  if(typeof at==='number')return at;
  if(at==='entry'||at==='first'||at==='every')return 0;
  if(at==='last'||at==='end')return nf-1;
  return null;}                 // 'exit' never fires while the animation is displayed
function animSurfFold(){
  ANIM_SURF.clear();ANIM_OWNED.clear();
  const a=(curAnim>=0)?DATA.anims[curAnim]:null;
  const sf=a&&a.fx&&a.fx.surf;
  if(sf&&sf.length){
    const nf=a.frames.length;
    for(const c of sf){         // file order, so a later line wins on the same frame
      const t=animSurfTrigger(c.at,nf);
      const fired=(t!==null&&t<=curFrame);
      for(const i of surfIdxByName(c.name)){
        ANIM_OWNED.add(i);                            // claimed for the whole run
        if(fired)ANIM_SURF.set(i,!!c.nodraw);}}}
  // A surface the user clicked while the animation held it stays THEIRS until the animation
  // issues a genuinely new command for it - i.e. until the folded value changes. Without
  // this, clicking a bangalore row mid-animation looked like a dead control: the click
  // landed, and the next frame's fold silently overwrote it.
  for(const [i,v] of [...ANIM_SURF_OVR]){
    if(ANIM_SURF.has(i)&&ANIM_SURF.get(i)===v)ANIM_SURF.delete(i);
    else ANIM_SURF_OVR.delete(i);}}

// hiddenSurf <- tik spawn state, then the user's overrides, then the animation on top.
// Rebuilt from empty every time so it can never accumulate stale entries. Does NOT draw;
// callers that already redraw (applyFrame) do not need a second pass.
function surfApply(){
  // Built into a scratch set and swapped in at the END. applyFrame() can run during page
  // boot, before the const bindings above have left their temporal dead zone; clearing
  // hiddenSurf first and then throwing would un-hide every tik-nodraw surface for the rest
  // of the session, with applyFrame's try/catch swallowing the reason.
  const nxt=new Set();
  // Baseline: the tik's spawn state. USER_SHOW lifts it - except on a surface the animation
  // is choreographing, where the tik's spawn state is the baseline the command list was
  // written against and the user's reveal is suspended.
  for(const i of TIK_NODRAW)if(animOwns(i)||!USER_SHOW.has(i))nxt.add(i);
  for(const i of USER_NODRAW)if(!animOwns(i))nxt.add(i);
  // The animation on top of both.
  for(const [i,nd] of ANIM_SURF){if(nd)nxt.add(i);else nxt.delete(i);}
  hiddenSurf.clear();for(const i of nxt)hiddenSurf.add(i);}
function surfRedraw(){
  if(typeof GLR!=='undefined'&&GLR)GLR.markDirty();
  try{draw();}catch(e){}
  surfCountRender();if(surfEl)surfMenuRender();}

// The toggle reads the LIVE hiddenSurf, not the persistent sets, so what a click does always
// matches what the row shows. An animation may already have revealed a tik-hidden surface
// (bangalore_assembly fires `surface bang* -nodraw`); clicking it then hides it again, and
// dropping it from USER_SHOW is what makes that stick through the next surfApply().
function surfToggle(i){
  // Taking a surface off the animation, if it currently owns it: remember WHICH value was
  // being imposed, so the fold can hand it back the moment the animation moves on.
  if(ANIM_SURF.has(i)){ANIM_SURF_OVR.set(i,ANIM_SURF.get(i));ANIM_SURF.delete(i);}
  if(hiddenSurf.has(i)){                                  // -> show it
    USER_NODRAW.delete(i);
    if(TIK_NODRAW.has(i))USER_SHOW.add(i);                // override the tik's spawn nodraw
    hiddenSurf.delete(i);
  }else{                                                  // -> hide it
    USER_SHOW.delete(i);
    if(!TIK_NODRAW.has(i))USER_NODRAW.add(i);             // tik-hidden ones need no user flag
    hiddenSurf.add(i);
  }
  surfRedraw();}

// ---- the list ----------------------------------------------------------------
// A real popup panel, NOT a <select>. An <option> commit closes the native popup every
// single time and nothing in the DOM can hold it open, so hiding twelve bangalore surfaces
// meant twelve reopenings. This reuses the animation / attachmodels menu chrome
// (.amPanel/.amItem/.amSearch, mnFit, full-window backdrop) and simply does not close on a
// pick. It closes on exactly what the other two menus close on: the button again, a click
// off the panel, Esc, a resize, or a scroll/wheel outside itself.
let surfEl=null,surfBack=null,surfFilter='';
const surfBtn=document.getElementById('surfBtn');

function surfMenuClose(){
  if(surfEl){surfEl.remove();surfEl=null;}
  if(surfBack){surfBack.remove();surfBack=null;}
  surfFilter='';
  document.removeEventListener('keydown',surfMenuKey,true);}

// Capture-phase, and it swallows every key while the list is up. The old control was a
// <select>, which the global hotkey handler skips by tagName; a <button> is NOT skipped, so
// without this "1"/"2"/"3" would toggle Texture/Mesh/Wire while the user types in the filter.
function surfMenuKey(ev){
  if(ev.key==='Escape'){surfMenuClose();ev.preventDefault();ev.stopPropagation();return;}
  ev.stopPropagation();}

function surfMenuPlace(){
  // Same geometry as amPlace()/attBrowsePlace(): hang the panel off the LEFT edge of its
  // button, tops aligned, falling back to the right side only if there is no room.
  if(!surfEl||!surfBtn)return;
  const r=surfBtn.getBoundingClientRect(),vw=window.innerWidth,vh=window.innerHeight;
  let left=r.left-AM_GAP-AM_W;
  if(left<4)left=Math.min(r.right+AM_GAP,Math.max(4,vw-4-AM_W));
  if(left+AM_W>vw-4)left=Math.max(4,vw-4-AM_W);
  surfEl.style.left=left+'px';
  mnFit(surfEl,r,vh);}

function surfMenuOpen(){
  surfMenuClose();
  if(!(DATA.surfRanges||[]).length)return;
  // Full-window backdrop, exactly like #animMenu and the attachmodels browser. It is what
  // makes a click anywhere else close the list - INCLUDING a click back on the button that
  // opened it, which is how the button toggles. A document mousedown watch instead would
  // close on mousedown and the button's own click would immediately reopen it.
  surfBack=document.createElement('div');
  surfBack.style.cssText='position:fixed;left:0;top:0;width:100%;height:100%;z-index:70';
  surfBack.onclick=(ev)=>{if(!surfEl||!surfEl.contains(ev.target))surfMenuClose();};
  document.body.appendChild(surfBack);
  surfEl=document.createElement('div');surfEl.className='amPanel';
  surfEl.style.cssText='position:fixed;z-index:71';
  const h=document.createElement('div');h.className='amHead';
  const pt=document.createElement('span');pt.className='amPathTxt';pt.textContent='surfaces';
  const pc=document.createElement('span');pc.className='amCnt';pc.id='surfHeadCnt';
  h.appendChild(pt);h.appendChild(pc);surfEl.appendChild(h);
  const se=document.createElement('input');se.className='amSearch';se.type='text';
  se.placeholder='filter surfaces\u2026';se.id='surfSearch';
  se.oninput=()=>{surfFilter=se.value.trim();surfMenuRender();};
  surfEl.appendChild(se);
  const bd=document.createElement('div');bd.className='amBody';bd.id='surfBody';
  surfEl.appendChild(bd);
  // Keep focus in the filter box while clicking rows: a mousedown on a row would otherwise
  // blur it. preventDefault on mousedown does not stop the row's click from firing.
  surfEl.addEventListener('mousedown',(ev)=>{
    if(ev.target===se||ev.target===bd)return;ev.preventDefault();});
  surfBack.appendChild(surfEl);
  surfMenuPlace();
  document.addEventListener('keydown',surfMenuKey,true);
  surfMenuRender();se.focus();}

// Display name per surface, numbering duplicates. A merged model can repeat a surface name
// across its parts (german_misc_worker has "head" from both the body and the head .skd), so
// without numbering two identical rows toggle different things with no way to tell which.
function surfNames(){
  const sr=DATA.surfRanges||[],dup={},seen={},out=[];
  sr.forEach(s=>{const k=(s.name||'').toLowerCase();dup[k]=(dup[k]||0)+1;});
  sr.forEach((s,i)=>{const raw=s.name||('surface '+i),k=raw.toLowerCase();
    seen[k]=(seen[k]||0)+1;
    out.push((dup[k]>1)?(raw+' #'+seen[k]):raw);});
  return out;}

function surfMenuRender(){
  const bd=document.getElementById('surfBody');if(!bd)return;
  const sv=bd.scrollTop;              // a toggle re-renders the list; do not jump to the top
  bd.innerHTML='';
  const sr=DATA.surfRanges||[],nms=surfNames(),f=surfFilter.toLowerCase();
  let shown=0,off=0;
  sr.forEach((s,i)=>{
    const hid=hiddenSurf.has(i);
    if(hid)off++;
    const nm=nms[i];
    if(f&&nm.toLowerCase().indexOf(f)<0)return;
    shown++;
    const tik=TIK_NODRAW.has(i),anim=animOwns(i);
    const d=document.createElement('div');d.className='amItem'+(hid?' nod':'');
    const g=document.createElement('span');g.className='arw';
    g.textContent=hid?'\u2715':'\u2713';d.appendChild(g);
    const l=document.createElement('span');l.className='lbl';l.textContent=nm;d.appendChild(l);
    // Who is deciding this row right now. The animation outranks both, so it is shown in
    // preference to the `tik` tag - otherwise a bangalore row would claim the tik owns it
    // while bangalore_assembly is visibly driving it frame by frame.
    const tag=anim?'anim':(tik?(hid?'tik':'tik \u2022 shown'):'');
    if(tag){const c=document.createElement('span');c.className='cnt';c.textContent=tag;
      c.title=anim?'this animation\u2019s own `surface \u2026 +/-nodraw` commands are driving this surface'
                  :'the .tik declares `surface \u2026 +nodraw` for this surface';
      d.appendChild(c);}
    d.title=anim
      ?(nm+' \u2014 driven by the animation right now; click to take it over until the '
        +'animation changes it again')
      :tik
      ?(nm+' \u2014 the .tik turns this off at spawn (`surface \u2026 +nodraw`); click to '
        +(hid?'show':'re-hide')+' it')
      :(nm+(hid?' \u2014 hidden (+nodraw); click to show it'
                :' \u2014 click to hide it (+nodraw)'));
    d.onclick=(ev)=>{ev.stopPropagation();surfToggle(i);};
    bd.appendChild(d);});
  if(!shown){const d=document.createElement('div');d.className='amNote';
    d.textContent='no surface matches that';bd.appendChild(d);}
  const hc=document.getElementById('surfHeadCnt');
  if(hc)hc.textContent=(sr.length-off)+' / '+sr.length+' drawn';
  surfMenuPlace();bd.scrollTop=sv;}

// Counts live hiddenSurf, not the user sets: an animation's own +/-nodraw commands change
// what is actually drawn (bangalore_assembly reveals all twelve bang* surfaces), and the
// readout beside the button has to follow that or it contradicts the model on screen.
// Plain and uncoloured - "8 / 20 surfaces" already says surfaces are hidden, and the longer
// red version wrapped onto its own line.
function surfCountRender(){
  const cnt=document.getElementById('surfCount');if(!cnt)return;
  const n=(DATA.surfRanges||[]).length;
  let off=0;for(const i of hiddenSurf)if(i>=0&&i<n)off++;
  cnt.textContent=(n-off)+' / '+n+' surfaces';}

function surfPanelInit(){
  const row=document.getElementById('surfRow');
  if(!row||!surfBtn)return;
  if(!(DATA.surfRanges||[]).length)return;   // nothing to toggle - leave the row hidden
  row.style.display='';
  surfBtn.onclick=(ev)=>{ev.stopPropagation();if(surfEl)surfMenuClose();else surfMenuOpen();};
  surfCountRender();}

// Called HERE, not up with the bridge handshake: surfPanelInit() and surfCountRender() read
// const/let bindings declared just above, and those are in their temporal dead zone until
// their own lines run. Calling earlier threw ReferenceError *inside* surfPanelInit - after
// it had already un-hidden the row - and the try/catch around it swallowed the error,
// leaving a visible but empty menu still showing the markup's placeholder count.
try{surfPanelInit();}catch(e){}

// ===== attach-to-bone picker =============================================
// Bones AND tags: the engine attaches to any named node, and MOHAA's own scripts use both
// ("Bip01 L Finger11" for the cigarette, tag_weapon_right for a rifle). That is 85 nodes on
// a human rig, and a native <select> offers no way to reach tag_weapon_right except
// scrolling past sixty finger bones - so this is the same popup chrome as the surfaces
// list, for the same reason.
//
// Two deliberate differences from that list. Nothing here is ever "off", so there is no
// hidden state and no strike-through - every row is a plain, equal choice. And picking
// CLOSES it: one pick creates one attachment slot, so there is nothing to toggle
// repeatedly and leaving the panel up would just be in the way.
let attBoneEl=null,attBoneBack=null,attBoneFilter='';
// Which nodes count as TAGS, by the same test the Display panel's Tags/Bones views use
// (kind 'tag', or an origin marker). Only a label - every node is attachable either way -
// but it is what makes tag_weapon_right findable among the Bip01 chain.
const ATT_ISTAG=(function(){const m=[];
  for(const t of (DATA.tags||[]))if(t.kind==='tag'||t.origin)m[t.idx]=1;
  return m;})();

function attBoneClose(){
  if(attBoneEl){attBoneEl.remove();attBoneEl=null;}
  if(attBoneBack){attBoneBack.remove();attBoneBack=null;}
  attBoneFilter='';
  document.removeEventListener('keydown',attBoneKey,true);}

function attBoneHits(){
  const f=attBoneFilter.toLowerCase(),out=[];
  DATA.bones.forEach((b,i)=>{if(!f||(b.name||'').toLowerCase().indexOf(f)>=0)out.push(i);});
  return out;}

// Capture-phase, and it swallows every key while the list is up: the old control was a
// <select>, which the global hotkey handler skips by tagName, but a <button> is not - so
// without this, typing "1" in the filter box would toggle the Texture layer.
function attBoneKey(ev){
  if(ev.key==='Escape'){attBoneClose();ev.preventDefault();ev.stopPropagation();return;}
  // Enter takes the top row still showing, so a search finishes without reaching for the
  // mouse: "weap" then Enter attaches to tag_weapon_left.
  if(ev.key==='Enter'){const h=attBoneHits();if(h.length)attBonePick(h[0]);
    ev.preventDefault();ev.stopPropagation();return;}
  ev.stopPropagation();}

function attBonePlace(){
  // Same geometry as the other three menus: off the LEFT edge of its button, tops aligned,
  // falling back to the right only when there is no room.
  const btn=document.getElementById('attBoneBtn');
  if(!attBoneEl||!btn)return;
  const r=btn.getBoundingClientRect(),vw=window.innerWidth,vh=window.innerHeight;
  let left=r.left-AM_GAP-AM_W;
  if(left<4)left=Math.min(r.right+AM_GAP,Math.max(4,vw-4-AM_W));
  if(left+AM_W>vw-4)left=Math.max(4,vw-4-AM_W);
  attBoneEl.style.left=left+'px';
  mnFit(attBoneEl,r,vh);}

function attBonePick(i){
  attBoneClose();                       // closes FIRST: the ceiling note below is a message
  if(ATT.length>=ATT_MAX){amNote('attachmodels: the engine allows '+ATT_MAX+' at once',true);return;}
  ATT.push({tag:i,key:null,path:'',scale:1,off:[0,0,0],ang:[0,0,0],bang:[0,0,0],ready:false});
  attPanelRender();}

function attBoneOpen(){
  attBoneClose();
  if(!(DATA.bones||[]).length)return;
  // Full-window backdrop, as with #animMenu and the attachmodels browser: a click anywhere
  // else closes the list, INCLUDING a click back on the button, which is how it toggles.
  attBoneBack=document.createElement('div');
  attBoneBack.style.cssText='position:fixed;left:0;top:0;width:100%;height:100%;z-index:70';
  attBoneBack.onclick=(ev)=>{if(!attBoneEl||!attBoneEl.contains(ev.target))attBoneClose();};
  document.body.appendChild(attBoneBack);
  attBoneEl=document.createElement('div');attBoneEl.className='amPanel';
  attBoneEl.style.cssText='position:fixed;z-index:71';
  const h=document.createElement('div');h.className='amHead';
  const pt=document.createElement('span');pt.className='amPathTxt';pt.textContent='tags \u0026 bones';
  const pc=document.createElement('span');pc.className='amCnt';pc.id='attBoneCnt';
  h.appendChild(pt);h.appendChild(pc);attBoneEl.appendChild(h);
  const se=document.createElement('input');se.className='amSearch';se.type='text';
  se.placeholder='filter tags \u0026 bones\u2026';se.id='attBoneSearch';
  se.oninput=()=>{attBoneFilter=se.value.trim();attBoneRender();};
  attBoneEl.appendChild(se);
  const bd=document.createElement('div');bd.className='amBody';bd.id='attBoneBody';
  attBoneEl.appendChild(bd);
  // Keep focus in the filter box while clicking rows; preventDefault on mousedown does not
  // stop the row's click from firing.
  attBoneEl.addEventListener('mousedown',(ev)=>{
    if(ev.target===se||ev.target===bd)return;ev.preventDefault();});
  attBoneBack.appendChild(attBoneEl);
  attBonePlace();
  document.addEventListener('keydown',attBoneKey,true);
  attBoneRender();se.focus();}

function attBoneRender(){
  const bd=document.getElementById('attBoneBody');if(!bd)return;
  bd.innerHTML='';
  // Skeleton order, unchanged from the old drop-down - it reads as the hierarchy (pelvis ->
  // spine -> neck -> head), which is worth keeping. The filter is what makes it navigable.
  const hits=attBoneHits();
  for(const i of hits){
    const d=document.createElement('div');d.className='amItem';
    const l=document.createElement('span');l.className='lbl';
    l.textContent=DATA.bones[i].name;d.appendChild(l);
    if(ATT_ISTAG[i]){const c=document.createElement('span');c.className='cnt';
      c.textContent='tag';
      c.title='a tag node - the kind MOHAA\u2019s own attachmodel calls name';
      d.appendChild(c);}
    d.title='attach a model to '+DATA.bones[i].name;
    d.onclick=(ev)=>{ev.stopPropagation();attBonePick(i);};
    bd.appendChild(d);}
  if(!hits.length){const d=document.createElement('div');d.className='amNote';
    d.textContent='no tag or bone matches that';bd.appendChild(d);}
  const c2=document.getElementById('attBoneCnt');
  if(c2)c2.textContent=hits.length+' / '+DATA.bones.length;
  attBonePlace();}

function attPanelInit(){
  const row=document.getElementById('attRow'),btn=document.getElementById('attBoneBtn');
  if(!row||!btn||!ATT_MODELS)return;
  btn.onclick=(ev)=>{ev.stopPropagation();if(attBoneEl)attBoneClose();else attBoneOpen();};
  row.style.display='';
  attPanelRender();}

function attPanelRender(){
  const list=document.getElementById('attList'),cnt=document.getElementById('attCount');
  if(!list)return;
  if(cnt)cnt.textContent=ATT.length+' / '+ATT_MAX+' attached';
  list.innerHTML='';
  ATT.forEach((a,idx)=>{
    // Two lines per attachment: there is no honest way to fit a bone name, a model
    // picker, scale, a 3-vector offset AND a 3-vector angle triple on one 300px row.
    const box=document.createElement('div');box.className='attBox';
    const r1=document.createElement('div');r1.className='row co';
    const rm=document.createElement('button');rm.textContent='\u00d7';
    rm.title='Remove this attachment';rm.style.cssText='min-width:20px;padding:0 5px';
    rm.onclick=()=>{ATT.splice(idx,1);attBrowseClose();attRebuild();};
    r1.appendChild(rm);
    const nm=document.createElement('span');
    nm.textContent=' '+(DATA.bones[a.tag]?DATA.bones[a.tag].name:'?')+' ';
    nm.style.cssText='min-width:104px;max-width:104px;display:inline-block;overflow:hidden;'
                    +'text-overflow:ellipsis;white-space:nowrap;vertical-align:middle';
    nm.title=(DATA.bones[a.tag]?DATA.bones[a.tag].name:'');
    r1.appendChild(nm);
    const mb=document.createElement('button');mb.className='attMdl';
    const ml=document.createElement('span');ml.className='albl';
    ml.textContent=a.path?a.path.replace(/^models\//,''):'choose model';
    const mc=document.createElement('span');mc.className='acar';mc.textContent='\u25c4';
    mb.appendChild(ml);mb.appendChild(mc);
    mb.title=a.path||'Browse the pak model tree';
    // No toggle bookkeeping needed: while the panel is up its backdrop covers this
    // button, so a click here hits the backdrop and closes - same as the animation menu.
    mb.onclick=(e)=>{e.stopPropagation();attBrowseOpen(idx,mb);};
    r1.appendChild(mb);
    if(a.path&&!a.ready){const w=document.createElement('span');w.className='dim';
      w.textContent=' building\u2026';r1.appendChild(w);}
    box.appendChild(r1);

    const r2=document.createElement('div');r2.className='row co';
    r2.style.cssText='padding-left:24px';
    const num=(val,w,title,set)=>{
      const e=document.createElement('input');e.type='text';e.value=String(val);
      e.style.cssText='width:'+w+'px';e.title=title;
      e.onchange=()=>{const v=parseFloat(e.value);set(isFinite(v)?v:0);
        e.value=String(set.get());attRebuild();};
      return e;};
    // Each label + its brackets is one nowrap group, so a wrap can only happen BETWEEN
    // groups. Without this the row broke wherever it ran out of width and stranded the
    // offset's closing ")" at the start of the angles line.
    const grp=()=>{const g=document.createElement('span');
      g.style.cssText='white-space:nowrap;margin-right:6px';r2.appendChild(g);return g;};
    const g1=grp();
    g1.appendChild(document.createTextNode('scale '));
    g1.appendChild(num(a.scale,32,'Uniform scale',Object.assign(
      (v)=>{a.scale=(v>0)?v:1;},{get:()=>a.scale})));
    const g2=grp();
    g2.appendChild(document.createTextNode('offset ('));
    for(let k=0;k<3;k++)
      g2.appendChild(num(a.off[k],30,'Offset '+'XYZ'[k]+' along the bone\u2019s own axes, in '
        +'engine world units \u2013 the same number a .tik / script attachmodel line carries'
        +(ATT_OFS!==1?' (this model loads at scale '+ATT_OFS+', which the viewer divides out '
                     +'so what you type here is what you type in-game)':''),
        Object.assign((v)=>{a.off[k]=v;},{get:()=>a.off[k]})));
    g2.appendChild(document.createTextNode(')'));
    const g3=grp();
    g3.appendChild(document.createTextNode('angles ('));
    const AN=['Pitch','Yaw','Roll'];
    for(let k=0;k<3;k++)
      g3.appendChild(num((a.ang||[0,0,0])[k],30,AN[k]+' in degrees, MOHAA order. 0/0/0 is '
        +'already correct for weapons - the authoring correction is applied underneath.',
        Object.assign((v)=>{a.ang=a.ang||[0,0,0];a.ang[k]=v;},
                      {get:()=>(a.ang||[0,0,0])[k]})));
    g3.appendChild(document.createTextNode(')'));
    box.appendChild(r2);
    list.appendChild(box);});}

// Ask a model to be resolved. Cached server-side by path, so asking twice is free.
function attRequest(path){
  if(!path)return null;
  if(!attPost('mohaa-attach '+path)){attGeomFail(null,'the attachment panel needs the launcher');return null;}
  ATT_PEND[path]=true;return true;}
window.MOHAA_ATTACH_FAIL=function(key,msg){attGeomFail(key,msg||'could not be built');};

// A saved trail is only reusable if it still describes a real path through THIS
// page's catalogue: rooted at ACAT.root, every index in range, and every step an
// actual child of the one before it. DATA (and so ACAT) is baked per page and the
// launcher navigates for each model, so opening a different model always arrives
// with an empty trail - the validation is belt-and-braces for a catalogue that
// changes under us, not the normal reset path.
function amPathOK(st){
  if(!st||!st.length||st[0]!==ACAT.root)return false;
  for(let i=0;i<st.length;i++){
    const n=ACAT.nodes[st[i]];
    if(!n)return false;
    if(i){const pk=ACAT.nodes[st[i-1]].k;
          if(!pk||pk.indexOf(st[i])<0)return false;}}
  return true;}

function amOpen(){
  if(amEl)return;
  // reopen where we left off: amClose keeps the trail, so drilling four groups
  // deep, closing to look at the model, and reopening lands back in that group.
  // The search box always reopens empty - a stale filter would hide the very
  // category the trail just restored.
  if(!amPathOK(amStack))amStack=[ACAT.root];
  amFilter='';amHot=-1;
  animMenu.classList.add('on');
  amEl=document.createElement('div');amEl.className='amPanel';
  const h=document.createElement('div');h.className='amHead';
  amUpBtn=document.createElement('button');amUpBtn.className='amUp';
  amUpBtn.innerHTML='\u2190 Back';
  amUpBtn.title='Go back to the previous category (Left arrow or Backspace)';
  amUpBtn.onclick=(ev)=>{ev.stopPropagation();amUp();};
  amHeadTxt=document.createElement('span');amHeadTxt.className='amPathTxt';
  amHeadCnt=document.createElement('span');amHeadCnt.className='amCnt';
  h.appendChild(amUpBtn);h.appendChild(amHeadTxt);h.appendChild(amHeadCnt);
  amEl.appendChild(h);
  // the search box is created ONCE and never rebuilt, so drilling in and out
  // never steals the caret out of it
  amSearch=document.createElement('input');amSearch.className='amSearch';amSearch.type='text';
  amSearch.placeholder='search all animations\u2026';
  amSearch.oninput=()=>{amFilter=amSearch.value.trim();amHot=-1;amRender();};
  amEl.appendChild(amSearch);
  amBody=document.createElement('div');amBody.className='amBody';
  amEl.appendChild(amBody);
  animMenu.appendChild(amEl);
  // Clicking a row must NOT pull the caret out of the search box. A plain <div>
  // row isn't focusable, so the browser's default mousedown focus move dumps focus
  // on <body> - at which point the panel stops seeing keys at all and they fall
  // through to the page hotkeys instead (Backspace = resetModel, Escape = close the
  // whole viewer). Cancelling the default keeps the caret put. amSearch is exempt,
  // since clicking into the text has to place the caret, and amBody is exempt
  // because cancelling mousedown on a scrollable element also kills native
  // scrollbar dragging.
  amEl.addEventListener('mousedown',(ev)=>{
    if(ev.target===amSearch||ev.target===amBody)return;
    ev.preventDefault();});
  document.addEventListener('keydown',amKeyGuard,true);
  amRender();amPlace();
  amSearch.focus();}

// The panel is modal while it is up, so its keys are taken on the document CAPTURE
// phase - they work whatever holds focus, not just the search box - and are then
// stopped before they can reach the page hotkeys bound on window (r = reset camera,
// Backspace = reset model, 1-7 = display toggles, Escape = close the viewer).
// Typing is unaffected: stopPropagation blocks delivery to other listeners, not the
// browser's own text insertion into the focused input.
function amKeyGuard(ev){amKey(ev);ev.stopPropagation();}

function amClose(){
  if(amEl){amEl.remove();amEl=null;amBody=amSearch=amHeadTxt=amHeadCnt=amUpBtn=null;}
  document.removeEventListener('keydown',amKeyGuard,true);
  amFilter='';amRows=[];amHot=-1;      // amStack SURVIVES - see amOpen
  animMenu.classList.remove('on');}

// anchored to the LEFT of the button and aligned with its top edge, not dropped
// below it, so the list sits beside the control it belongs to
// Clamp the panel to the window BEFORE measuring it, then clamp its top against that
// measured height. The stylesheet's max-height:78vh is a look-and-feel cap, not a
// guarantee - drilling into a big folder (models/static is 536 entries) grew the list
// past whatever room was left below the button, and the tail ("vehicles" and friends)
// fell off the bottom edge with no way to reach it but closing and scrolling the panel
// behind. Setting an explicit pixel max-height makes .amBody take over and scroll, so the
// menu always fits on screen and always overlaps whatever is beneath it.
function mnFit(el,r,vh){
  const avail=vh-8;
  el.style.maxHeight=avail+'px';
  el.style.top='4px';
  const h=Math.min(el.getBoundingClientRect().height,avail);
  el.style.top=Math.max(4,Math.min(r.top,vh-4-h))+'px';}

function amPlace(){
  if(!amEl)return;
  const r=animBtn.getBoundingClientRect(),vw=window.innerWidth,vh=window.innerHeight;
  let left=r.left-AM_GAP-AM_W;
  if(left<4)left=Math.min(r.right+AM_GAP,Math.max(4,vw-4-AM_W));
  if(left+AM_W>vw-4)left=Math.max(4,vw-4-AM_W);
  amEl.style.left=left+'px';
  mnFit(amEl,r,vh);}

function amTrail(){
  return amStack.slice(1).map(i=>ACAT.nodes[i].n).join(' \u203a ');}
// deep trails keep the tail visible (the category you are actually in); the full
// path stays in the tooltip
function amTrailShort(){
  const t=amStack.slice(1).map(i=>ACAT.nodes[i].n);
  return (t.length>2?'\u2026 \u203a ':'')+t.slice(-2).join(' \u203a ');}

function amRender(){
  if(!amEl)return;
  const node=ACAT.nodes[amStack[amStack.length-1]];
  const root=amStack.length<2;
  amUpBtn.disabled=root&&!amFilter;
  if(amFilter){amHeadTxt.textContent='search results';amHeadCnt.textContent='';}
  else{amHeadTxt.textContent=root?(ACAT.anims.length+' animations'):amTrailShort();
       amHeadCnt.textContent=root?'':String(node.c!=null?node.c:'');}
  amHeadTxt.title=root?'':amTrail();
  amBody.innerHTML='';amRows=[];
  if(amFilter){
    const q=amFilter.toLowerCase();let hits=0;
    for(let i=0;i<ACAT.anims.length;i++){
      const e=ACAT.anims[i];
      if(e.n.toLowerCase().indexOf(q)<0&&(e.s||'').toLowerCase().indexOf(q)<0)continue;
      if(hits>=AM_MAXHITS){const m=document.createElement('div');m.className='amNote';
        m.textContent='\u2026 more matches; refine the search';amBody.appendChild(m);break;}
      amAddLeaf(i);hits++;}
    if(!hits){const m=document.createElement('div');m.className='amNote';
      m.textContent='no animation matches "'+amFilter+'"';amBody.appendChild(m);}
  }else{
    if(root&&ACAT.anims.length===0)amAddRest();   // rest row only when the model has NO anims
    node.k.forEach(ci=>amAddGroup(ci));
    node.a.forEach(ai=>amAddLeaf(ai));
    if(!node.k.length&&!node.a.length){
      const m=document.createElement('div');m.className='amNote';
      m.textContent='(this category is empty)';amBody.appendChild(m);}
  }
  amHi(amHot<0?-1:Math.min(amHot,amRows.length-1));
  amPlace();}

function amRow(cls,label,count,arrow){
  const d=document.createElement('div');d.className='amItem'+(cls?' '+cls:'');
  const l=document.createElement('span');l.className='lbl';l.textContent=label;d.appendChild(l);
  if(count!=null&&count!==''){const c=document.createElement('span');c.className='cnt';
    c.textContent=count;d.appendChild(c);}
  if(arrow){const a=document.createElement('span');a.className='arw';a.textContent=arrow;d.appendChild(a);}
  const idx=amRows.length;
  // mousemove, NOT mouseenter: scrolling the list (arrow keys call scrollIntoView)
  // re-runs hover hit-testing and fires mouseenter on whatever slid under a
  // stationary pointer, which would snatch the highlight back mid-keyboard-nav.
  // mousemove only fires on real pointer motion. The guard keeps this to one DOM
  // pass per row change instead of one per mouse event.
  d.onmousemove=()=>{if(amHot!==idx)amHi(idx);};
  amBody.appendChild(d);
  return d;}

function amAddRest(){
  const d=amRow('','\u2014 bind pose (rest) \u2014','',null);
  const go=()=>{selectAnim(-1,null);amClose();};
  d.onclick=(ev)=>{ev.stopPropagation();go();};
  amRows.push({go:go});}

function amAddGroup(ci){
  const cn=ACAT.nodes[ci];
  const d=amRow('grp',cn.n,String(cn.c!=null?cn.c:''),'\u25b8');
  d.title=cn.n+'  \u2014  '+(cn.c||0)+' animation'+(cn.c===1?'':'s');
  const go=()=>amEnter(ci);
  d.onclick=(ev)=>{ev.stopPropagation();go();};
  amRows.push({go:go});}

// Reverse index: catalogue anim -> the node trail that reaches it. The catalogue is
// a DAG - one .tik pulled in by forty mission groups is stored once and shown forty
// times - so a node can be reached by many trails. The walk keeps the FIRST one in
// declaration order and visits every node exactly once, which is what makes this
// O(nodes + anims) rather than exponential in the sharing. Built on demand and then
// cached: DATA.anims grows as sidecars load, but the node structure never changes.
let amPathMap=null;
function amPaths(){
  if(amPathMap)return amPathMap;
  amPathMap={};
  const seen=new Set();
  (function walk(ni,trail){
    if(seen.has(ni))return; seen.add(ni);
    const n=ACAT.nodes[ni]; if(!n)return;
    const t=trail.concat(ni);
    (n.a||[]).forEach(ai=>{if(amPathMap[ai]===undefined)amPathMap[ai]=t;});
    (n.k||[]).forEach(ci=>walk(ci,t));
  })(ACAT.root,[]);
  return amPathMap;}

// the trail as node indices (root first), or null when the anim is unreachable
function amPathTo(catIdx){const p=amPaths()[catIdx];return p&&p.length?p.slice():null;}

// ...and as the same breadcrumb the header draws, with the root omitted. A model
// whose anims all sit at the root has nothing to show but the root's own name.
function amPathStr(catIdx){
  const p=amPaths()[catIdx];
  if(!p||!p.length)return '';
  const names=p.slice(1).map(i=>ACAT.nodes[i].n);
  return names.length?names.join(' \u203a '):(ACAT.nodes[ACAT.root].n||'');}

function amAddLeaf(catIdx){
  const e=ACAT.anims[catIdx];
  const loaded=(e.ai!=null&&DATA.anims[e.ai]);
  const cached=(!loaded&&e.id&&AM_HAVE[e.id]);   // built on disk, just not loaded yet
  const bad=(!loaded&&!cached&&e.id&&AM_FAIL[e.id])?AM_FAIL[e.id]:null;
  const d=amRow(loaded?'have':(cached?'have':(bad?'failed':'')),e.n,
                loaded?(DATA.anims[e.ai].frames.length+'f'):(cached?'built':(bad?'failed':'.skc')),null);
  // two lines: where this animation sits in the menu, then where it sits on disk.
  // The category line is the only way to place a search hit - search results are
  // flat, so the header breadcrumb just reads "search results".
  const cp=amPathStr(catIdx);
  d.title=(cp?cp+'\n':'')+(e.s||'')+(bad?'\n\u2717 '+bad:'')
          +(e.f&&e.f.length?'   ['+e.f.join(' ')+']':'');
  if(loaded&&e.ai===curAnim)d.classList.add('sel');
  const go=()=>pickAnim(catIdx);
  d.onclick=(ev)=>{ev.stopPropagation();go();};
  amRows.push({go:go});}

function amEnter(ci){amStack.push(ci);amFilter='';amSearch.value='';amHot=-1;amRender();}
function amUp(){
  if(amFilter){amFilter='';amSearch.value='';amHot=-1;amRender();return;}
  if(amStack.length>1){amStack.pop();amHot=-1;amRender();}}

function amHi(i){
  [...amBody.children].forEach(x=>x.classList.remove('hot'));
  amHot=i;
  if(i<0||i>=amRows.length)return;
  const el=amBody.children[i];
  if(el){el.classList.add('hot');
    if(el.scrollIntoView)el.scrollIntoView({block:'nearest'});}}

// Up/Down walk the list, Enter opens a category or plays an animation, and
// Left/Backspace go up a level - but only while the search box is empty, so
// they stay ordinary text editing keys the moment anything is typed.
function amKey(ev){
  const k=ev.key;
  if(k==='ArrowDown'||k==='ArrowUp'){
    ev.preventDefault();
    if(!amRows.length)return;
    let i=amHot+(k==='ArrowDown'?1:-1);
    if(i<0)i=amRows.length-1; if(i>=amRows.length)i=0;
    amHi(i);return;}
  if(k==='Enter'){
    ev.preventDefault();
    if(amHot>=0&&amRows[amHot])amRows[amHot].go();
    else if(amRows.length===1)amRows[0].go();
    return;}
  if(k==='ArrowRight'){
    if(amHot>=0&&amRows[amHot]&&amBody.children[amHot].classList.contains('grp')){
      ev.preventDefault();amRows[amHot].go();}
    return;}
  if(k==='ArrowLeft'||k==='Backspace'){
    if(amSearch&&amSearch.value)return;      // typing: leave text editing alone
    ev.preventDefault();amUp();return;}
  if(k==='Escape'){ev.preventDefault();ev.stopPropagation();amClose();animBtn.focus();return;}
  if(k==='Home'||k==='End'){
    if(amSearch&&amSearch.value)return;
    ev.preventDefault();amHi(k==='Home'?0:amRows.length-1);}}

// ---- selecting / requesting ------------------------------------------------
function animBtnLabel(){
  const lbl=animBtn.querySelector('.albl')||animBtn;
  if(curAnim<0){lbl.textContent='\u2014 bind pose (rest) \u2014';animPath.style.display='none';return;}
  const a=DATA.anims[curAnim];
  lbl.textContent=a.name+'  ('+a.frames.length+'f)';
  const e=ACAT.anims.find(x=>x.ai===curAnim);
  if(e&&e.s){animPath.textContent=e.s;animPath.style.display='';animPath.style.color='';}
  else animPath.style.display='none';}

function amNote(msg,err){animPath.textContent=msg;animPath.style.display='';
  animPath.style.color=err?'var(--err)':'';}

function selectAnim(idx,catIdx){
  attPurgeAnim();
  // Leaving an animation hands every surface it held back to the tik/user state. The
  // incoming animation's own commands are folded in by the applyFrame() below.
  ANIM_SURF.clear();ANIM_SURF_OVR.clear();ANIM_OWNED.clear();
  curAnim=idx;curFrame=0;
  const nf=idx<0?1:DATA.anims[idx].frames.length;
  scrub.max=nf-1;scrub.value=0;playing=false;updatePlayBtn();
  animStreams=[];applyFrame();animBtnLabel();
  if(amEl)amRender();}

// One animation at a time, cached on disk. The page first tries the sidecar the
// launcher writes into the folder beside this HTML (a classic <script> tag - a
// file:// page may load those, unlike fetch/XHR). A miss means it was never
// built, so the page asks the launcher to build it; the launcher extracts the
// .skc from the paks, runs mohaa_view.py --animbuild, logs the result in the
// Output pane and calls MOHAA_ANIM_LOAD() when the sidecar is on disk - at which
// point it loads, is appended to DATA.anims and starts playing, with no second
// trip through the menu.
const AM_PEND={};
function pickAnim(catIdx){
  const e=ACAT.anims[catIdx];
  // Picked from a search hit? Move the saved trail to where that animation actually
  // lives, so reopening the menu shows its neighbours instead of whatever unrelated
  // category happened to be open when the search was typed. Picking from inside a
  // folder leaves the trail alone - the check is what keeps an animation that appears
  // in several groups from yanking you out of the one you were browsing.
  const cn=ACAT.nodes[amStack[amStack.length-1]];
  if(!cn||!cn.a||cn.a.indexOf(catIdx)<0){const jp=amPathTo(catIdx);if(jp)amStack=jp;}
  if(e.ai!=null&&DATA.anims[e.ai]){selectAnim(e.ai,catIdx);amClose();return;}
  if(!e.id){amNote('this animation has no cache id - reopen the model');amClose();return;}
  amClose();
  AM_PEND[e.id]=catIdx;
  amNote('loading '+e.n+' \u2026');
  amLoadSidecar(e.id,()=>{
    if(AM_PEND[e.id]===undefined)return;              // arrived
    if(window.chrome&&window.chrome.webview){
      amNote('building '+e.n+' \u2026  (see Output)');
      try{window.chrome.webview.postMessage('mohaa-anim '+e.id+' '+e.n);}
      catch(_e){amNote('could not reach the launcher to build '+e.n);}
    }else{
      delete AM_PEND[e.id];
      amNote(e.n+' is not built yet - open this model in the launcher and click it there');}
  });}

function amLoadSidecar(id,onMiss){
  if(!ANIM_DIR){if(onMiss)onMiss();return;}
  const s=document.createElement('script');
  s.src=ANIM_DIR+'/a'+id+'.js?'+Date.now();
  s.onerror=()=>{s.remove();if(onMiss)onMiss();};
  s.onload=()=>{s.remove();if(AM_PEND[id]!==undefined&&onMiss)onMiss();};
  document.head.appendChild(s);}

// JSONP callback used by the sidecar files themselves
function MOHAA_ANIM(id,rec){
  const catIdx=AM_PEND[id];
  // Frame commands were resolved at page-build time and keyed by animation name (the
  // emitters they reference already live in DATA.emitters). A sidecar carries no fx of
  // its own, so hand it the baked entry now - this is what makes smoking01 put a
  // cigarette in the hand and smoking04/05 flick one away.
  if(!rec.fx&&DATA.animfx&&rec.name&&DATA.animfx[rec.name])rec.fx=DATA.animfx[rec.name];
  DATA.anims.push(rec);
  const ai=DATA.anims.length-1;
  let e=(catIdx!=null)?ACAT.anims[catIdx]:ACAT.anims.find(x=>x.id===id);
  if(e)e.ai=ai;
  delete AM_PEND[id];
  selectAnim(ai,catIdx);
  if(window.__amStats)window.__amStats();}
window.MOHAA_ANIM=MOHAA_ANIM;
// launcher -> page: the sidecar is on disk now, pull it in and play it
// A body animation and its facial sibling are built together, so the face entry has a
// real cached sidecar the moment the body one finishes. This marks it "already built" in
// the drop-down WITHOUT loading or selecting it - the dot should reflect what is on disk,
// and the user has not asked to play that track.
const AM_HAVE={};
window.MOHAA_ANIM_HAVE=function(id){if(!id)return;AM_HAVE[id]=1;delete AM_FAIL[id];
  if(amEl)amRender();};

window.MOHAA_ANIM_LOAD=function(id){delete AM_FAIL[id];amLoadSidecar(id,()=>{
  delete AM_PEND[id];amNote('built, but the animation file could not be read',true);});};
window.MOHAA_ANIM_FAIL=function(id,msg){
  const catIdx=AM_PEND[id];delete AM_PEND[id];
  const e=(catIdx!=null)?ACAT.anims[catIdx]:ACAT.anims.find(x=>x.id===id);
  const why=msg||'could not be built';
  if(id)AM_FAIL[id]=why;
  // PATH FIRST, then the reason. The .skc path is the part worth selecting and
  // copying (to hand-check the file, or to quote in a report), and this note is the
  // only place the viewer ever shows it - a failure used to replace it with the bare
  // animation name, so the path became unreachable exactly when it was wanted.
  const where=(e&&e.s)?e.s:((e&&e.n)?e.n:'animation');
  amNote(where+'  \u2014  '+why,true);
  if(amEl)amRender();};

animBtn.innerHTML='<span class="albl"></span><span class="acar">\u25c4</span>';
animBtn.onclick=(ev)=>{ev.stopPropagation();if(amEl)amClose();else amOpen();};
// #animMenu is a full-window backdrop layer, so every click inside the panel that
// did not already stopPropagation - the search box, the header, padding, the
// scrollbar - used to bubble up here and shut the menu. Only a click that misses
// the panel entirely closes it; picking an animation closes it from pickAnim().
animMenu.onclick=(ev)=>{if(!amEl||!amEl.contains(ev.target))amClose();};
window.addEventListener('resize',()=>{amClose();
  try{if(attBrowseEl)attBrowseClose();}catch(e){}
  try{if(attBoneEl)attBoneClose();}catch(e){}
  // The surfaces list is the one menu that is MEANT to stay up across interaction, so a
  // resize re-anchors it against the button instead of dismissing it. mnFit re-clamps the
  // height, so it still cannot run off a shortened window.
  try{if(surfEl)surfMenuPlace();}catch(e){}});
// Scroll does NOT bubble, so this has to be a capture-phase listener on the document to
// see the right-hand panel scrolling. Both menus are positioned against where their
// trigger WAS, so leaving them up while the panel moves underneath just strands them
// over unrelated controls.
// Scroll does not bubble, so this is capture-phase to see the right-hand panel move.
// The containment test is the whole point: without it this fired for the menu's OWN list
// scrolling - so a wheel over the list, or a drag of its scrollbar, shut the menu
// instantly. ev.target is the scrolling ELEMENT, except for the document/window scroll
// where it is the document itself, hence the nodeType guard.
function mnScrollWatch(ev){
  const t=ev.target,el=(t&&t.nodeType===1)?t:null;
  if(amEl&&!(el&&amEl.contains(el)))amClose();
  try{if(attBrowseEl&&!(el&&attBrowseEl.contains(el)))attBrowseClose();}catch(e){}
  // Scrolling the right-hand panel moves surfBtn out from under a position:fixed list, so
  // this one DOES close - staying open would strand it over unrelated controls. A wheel
  // over its own body scrolls the list and is excluded by the containment test.
  try{if(surfEl&&!(el&&surfEl.contains(el)))surfMenuClose();}catch(e){}
  try{if(attBoneEl&&!(el&&attBoneEl.contains(el)))attBoneClose();}catch(e){}}
document.addEventListener('scroll',mnScrollWatch,true);

// A backdrop covers the whole window while a menu is up, so the wheel never reaches the
// panel behind it and no scroll event is produced at all. Turning a wheel over the
// backdrop into a close is what makes "scroll away to dismiss" work; a wheel over the
// menu itself falls through untouched and scrolls the list, which is what should happen
// while the menu has the pointer.
function mnWheelWatch(ev){
  if(amEl&&!amEl.contains(ev.target))amClose();
  try{if(attBrowseEl&&!attBrowseEl.contains(ev.target))attBrowseClose();}catch(e){}
  try{if(surfEl&&!surfEl.contains(ev.target))surfMenuClose();}catch(e){}
  try{if(attBoneEl&&!attBoneEl.contains(ev.target))attBoneClose();}catch(e){}}
window.addEventListener('wheel',mnWheelWatch,{passive:true,capture:true});
document.addEventListener('keydown',(e)=>{if(e.key==='Escape'&&amEl)amClose();},true);
animBtnLabel();
scrub.oninput=()=>{curFrame=+scrub.value;applyFrame();};
const _canPlay=()=>(curAnim>=0||EM.length>0);
// Combined Play/Pause. One button drives BOTH frame playback and the global freeze
// (which also halts every emitter/effect clock in effLoop). Label rules:
//   Pause shown while the anim is ticking, or - with no anim selected - while a pure
//   effect model's emitters/animated surfaces are running. Play shown otherwise.
// Click rules: paused -> resume (and (re)start a stopped anim); running -> freeze
// everything in place; stopped anim -> (re)start it (old Play semantics, incl. one-shot
// re-fire with a particle/init-sfx reset).
// hasEffectSurf alone described the HOST only; an attached sprite is an effect the button
// should report on too, so ask the live surface list (rev 63).
const _effRunning=()=>(EM.length>0||hasEffectSurf||liveEffectSurf());
function updatePlayBtn(){const run=!paused&&(playing||(curAnim<0&&_effRunning()));
 playBtn.textContent=run?'\u23f8 Pause':'\u25b6 Play';playBtn.classList.toggle('on',run);}
function startPlayback(){playing=true;last=performance.now();
 if(EM.length)parts=[];animStreams=[];pendingFx=[];
 if(INITFX)fireInitFx();          // pressing Play replays the init sfx one-shot
 if(curAnim>=0){const NF=DATA.anims[curAnim].frames.length;
   // a finished one-shot restarts from frame 0 on the next Play press
   if(!loopAnim&&curFrame>=NF-1&&NF>1){attPurgeAnim();curFrame=0;scrub.value=0;applyFrame();}
   // entry + first-frame commands fire when the anim (re)starts from its head
   if(curFrame===0)fireAnimStart();}
 requestAnimationFrame(tick);}
playBtn.onclick=()=>{
 if(paused){setPaused(false);if(curAnim>=0&&!playing)startPlayback();updatePlayBtn();return;}
 if(playing||(curAnim<0&&_effRunning())){setPaused(true);return;}   // running -> freeze it all
 if(!_canPlay())return;
 startPlayback();updatePlayBtn();};
speed.oninput=()=>fpsl.textContent=speed.value;
// Loop toggle: on = wrap at the last frame (models); off = play once and stop
// (one-shot .tik effects - press Play again or Reset to re-fire, as in-game
// re-triggering). Default follows the opened file type.
const loopBtn=document.getElementById('bLoop');
function setLoop(v){loopAnim=v;loopBtn.classList.toggle('on',v);
  try{localStorage.setItem('mohaaViewerLoop',v?'on':'off');}catch(_e){}}
loopBtn.onclick=()=>setLoop(!loopAnim);
setLoop(loopAnim);
// "(.tik) anims" / "(.skc) anims" tag beside the dropdown, per the opened file
(function(){const k=document.getElementById('animKind');
 if(k)k.textContent=ACAT.anims.length?('(.'+ANIMKIND+') anims'):'';})();
// GLOBAL pause: freezes the animation AND every emitter/effect where they are. Camera
// orbit still works while frozen. Toggling back resumes with no time jump. Driven by
// the combined Play/Pause button above (and the F key).
function setPaused(p){paused=p;
  if(!paused){last=performance.now();_effLast=performance.now();}
  updatePlayBtn();draw();}
updatePlayBtn();   // initial label: pure effect models show Pause (already animating)
// Boot: fully initialise the default anim (curAnim 0 for any model that HAS anims) through
// selectAnim, so the scrubber max, current frame, label and effect streams are set up exactly
// as a manual pick would - fixing grenexp_base & friends, whose look lives in init{client{}}/
// idle: they used to boot on the -1 bind-pose sentinel (effect auto-ran once, Play couldn't
// restart it). Placed here so updatePlayBtn/_effRunning (const arrows) are already defined.
// With no anims at all, curAnim stays -1 and the bind-pose row is the only menu entry.
if(curAnim>=0&&DATA.anims[curAnim]){const _ca=curAnim;curAnim=-1;selectAnim(_ca,null);}
function tick(now){if(!playing)return;
 if(paused){last=now;requestAnimationFrame(tick);return;}   // frozen: keep the loop alive, advance nothing (no resume jump)
 const dt=Math.min(0.05,(now-last)/1000);last=now;
 if(curAnim>=0){acc+=dt;const step=1/(+speed.value);
   const NF=DATA.anims[curAnim].frames.length;
   while(acc>=step){acc-=step;
     if(curFrame+1>=NF){
       if(loopAnim){attPurgeAnim();curFrame=0;
         // Loop wrap re-enters the anim head, so re-fire its entry + first-frame
         // commands too (viewer semantics: Loop replays the one-shot, so e.g.
         // fx_flak88_explosion's `enter originspawn` explosion repeats each cycle).
         // Throttled to >=0.2s between re-fires so an ultra-short/1-frame anim
         // (jeep `skidding` at high fps) can't machine-gun its spawn commands.
         if(effT-_lastWrapFire>=0.20){_lastWrapFire=effT;
           fireAnimAt('entry');fireAnimAt('first');fireAnimAt(0);fireAnimAt('every');}}
       else{fireAnimAt('end');playing=false;updatePlayBtn();acc=0;break;}
     } else {curFrame++;fireAnimFrame(curFrame);}
   }
   scrub.value=curFrame;}
 if(curAnim>=0)applyFrame(); else draw();   // applyFrame redraws; otherwise draw directly
 requestAnimationFrame(tick);}
// Continuous effect driver: emitters and animated surfaces (flames, arcs) run on their
// own clock so they animate even when the model itself is at rest / not "playing".
let _effLast=0;
function effLoop(now){
  const dt=paused?0:(_effLast?Math.min(0.05,(now-_effLast)/1000):0); _effLast=now;
  effT+=dt;                       // frozen when paused: dt=0 -> clock holds, particles are not re-stepped
  if(!paused){
    runPendingFx();               // due commanddelay / delayedsfx commands
    if(INITFX){                   // init sfx one-shots: once at load, and (Loop on) each period
      if(_initfxLast<-1e8)fireInitFx();
      else if(loopAnim&&(effT-_initfxLast)>=INITFX.period)fireInitFx();
    }
    if(EM.length)stepParts(dt);
    if(hasFlap){applyFlap();if(GLR)GLR.markDirty();}   // wind re-deforms every frame
  }
  if(!interacting)requestDraw();  // still redraw so the frozen scene follows camera orbit
  requestAnimationFrame(effLoop);}
if(EM.length||hasEffectSurf||hasTexRot||hasFlap)startEffLoop();
// MODEL section: Light/Dark toggle. Toggles a class on <html>; the canvas grid/label colours
// are refreshed from the CSS vars and the scene is redrawn. Button label shows the mode it
// switches TO.
// PLACEMENT ANGLE dial (pitch / yaw / roll). See anglesToRot / EROT further up: the value
// is the entity `angles` key a .bsp/.map would supply, which the engine hands to AnglesToAxis
// to build the refEntity axis. The slider has four stops - 0 / 90 / 180 / 270 - because map
// placements for props and wall/ceiling fx are overwhelmingly axis-aligned quarter turns, and
// four hard detents beat hunting for 90.0 on a free slider. The button to its left picks WHICH
// of the three components the slider edits; each component keeps its own value, so cycling the
// button swaps the slider to that axis's setting (0 until it has been moved) and never disturbs
// the other two.
// rev 62: the four detents are no longer the only reachable values. The pencil to the RIGHT of
// the ( pitch yaw roll ) readout swaps it for three number fields that accept ANY angle - the
// muzzle-flash / turret placement work needs 45s and 22.5s, not just quarter turns - and
// setAngles no longer quantises what it is handed. The <input type=range> is therefore
// step="any" with the thumb positioned at deg/90, so an off-detent angle parks it BETWEEN two
// tick marks instead of lying about where the model is pointing. The TRACK therefore spans a
// full turn (0..4 quarter turns) even though only four detents are marked: with a 0..3 range
// everything in the fourth quadrant (a typed -7 normalises to 353) had nowhere to sit and
// clamped to the 270 mark. The right edge is 360, which is the same orientation as 0, so it is
// left unmarked and the control WRAPS there instead of resting on it - stepping right off 270
// arrives at 0, stepping left off 0 arrives at 270, round and round for as long as you hold the
// key. That wrap is why the arrow keys are handled in a keydown of our own: a native range
// clamps at its ends and simply stops firing input, which read as the control being stuck.
// Dragging and the arrow keys still land on whole detents, which is what the tick marks
// promise; the fields are the only way to leave them. Unlike the setsize pencil - which previews a value the FILE owns and
// so reverts on close - a typed angle survives closing the editor: this dial is a view setting
// that is already persisted, and throwing the number away would defeat the point of typing it.
{const _axBtn=document.getElementById('angAxis'),
       _agEl=document.getElementById('angsl'),
       _agV=document.getElementById('angslv'),
       _agB=document.getElementById('angEdit');
 const _AXN=['Pitch','Yaw','Roll'];
 let _axi=0;                                     // always opens on Pitch, per model
 let _agEdit=false;                              // pencil: readout text vs. three number fields
 // 3 decimals is what the launcher's config round-trip preserves; trailing zeros are dropped
 // so a plain quarter turn still reads '90' rather than '90.000'.
 const _agFmt=v=>String(Math.round((+v||0)*1000)/1000);
 function _agSave(){
   // Persisted twice on purpose: localStorage covers the page opened straight in a browser,
   // and the WebView2 bridge covers the embedded pane - the launcher writes the triple into
   // mohaa_viewer_config.json and hands it back on the next page's #ang= boot hash.
   try{localStorage.setItem('mohaaViewerAngles',EANG.join(','));}catch(_e){}
   try{if(window.chrome&&chrome.webview)chrome.webview.postMessage('mohaa-ang '+EANG.join(','));}catch(_e){}}
 function _agSync(){
   if(_axBtn)_axBtn.textContent=_AXN[_axi];
   // the slider tracks ONLY the axis the button currently names. deg/90 rather than a rounded
   // detent index: with step="any" that is what puts the thumb at the true fraction between
   // two ticks for an angle the pencil typed in.
   // 0..4 quarter turns; EANG is already folded into [0,360) so this never reaches 4 (the
   // wrap seam) - it only ever approaches it from the left, which is what the last quarter of
   // the track is for.
   if(_agEl)_agEl.value=String((((EANG[_axi]%360)+360)%360)/90);
   if(_agB)_agB.className=_agEdit?'on':'';
   if(!_agV)return;
   // ...while the readout is the whole orientation, in the engine's own (pitch yaw roll)
   // order - the same triple a .map entity would carry in its `angles` key. Showing all
   // three keeps the two axes the slider is not driving from silently disappearing.
   if(!_agEdit){
     _agV.style.minWidth='100px';
     _agV.textContent='( '+_agFmt(EANG[0])+' '+_agFmt(EANG[1])+' '+_agFmt(EANG[2])+' )';
     return;}
   // Editing: three number fields, sized and wired like the setsize / attach-to-bone editors
   // (commit on change, i.e. Enter or blur). Rebuilt only when the readout is not ALREADY the
   // editor, so a slider drag - which lands back in here - refreshes the values in place
   // instead of destroying the field the caret is sitting in.
   const ins=_agV.getElementsByTagName('input');
   if(ins.length===3){
     // The FOCUSED field is refreshed too. Every path that reaches here is a deliberate change
     // the readout has to show - slider, axis button, a committed field, the launcher hook -
     // and commit-on-change means a field never fires mid-keystroke, so there is no half-typed
     // value being protected; skipping the focused one just left it lying (drag the slider with
     // the caret in Pitch and the field would still read the old angle). Assigning only on a
     // real difference keeps the caret from jumping when that field is already correct.
     for(let k=0;k<3;k++){const t=_agFmt(EANG[k]);if(ins[k].value!==t)ins[k].value=t;}
     return;}
   _agV.style.minWidth='0';
   _agV.textContent='';
   _agV.appendChild(document.createTextNode('('));
   for(let k=0;k<3;k++){
     const e=document.createElement('input');e.type='text';e.value=_agFmt(EANG[k]);
     // 40px, not the 30px the setsize / offset fields use: those hold integers, these hold
     // things like 22.5 and 337.5, and a clipped '337.' is worse than a slightly tighter slider -
     // which, while you have exact numbers in front of you, is the control you need least.
     e.style.cssText='width:40px';
     e.title=_AXN[k]+' in degrees - any value, not just the four quarter turns.';
     e.onchange=()=>{const v=parseFloat(e.value),nx=EANG.slice();
       nx[k]=isFinite(v)?v:0;setAngles(nx[0],nx[1],nx[2],true);};
     _agV.appendChild(e);}
   _agV.appendChild(document.createTextNode(')'));}
 function setAngles(p,y,r,save){
   // Normalised into [0,360) but NOT quantised: the pencil is allowed to hand this any angle,
   // and the slider path has already snapped to a detent before it gets here. Rounded to 3
   // decimals so float drift never turns 45 into 44.99999999999999 in the readout.
   const q=v=>{v=(isNaN(+v)?0:+v)%360;if(v<0)v+=360;return Math.round(v*1000)/1000;};
   EANG=[q(p),q(y),q(r)];
   EROT=(EANG[0]||EANG[1]||EANG[2])?anglesToRot(EANG[0],EANG[1],EANG[2]):null;
   _agSync();
   // Live particles were integrated in the OLD frame; leaving them would smear the two
   // orientations together for a full particle life. Drop them and let the emitters re-seed.
   parts.length=0;
   applyFrame();                                 // rebuilds curWorld / modelBase / normals, redraws
   if(save!==false)_agSave();}
 window.setViewerAngles=setAngles;               // launcher / console hook
 if(_axBtn)_axBtn.onclick=()=>{_axi=(_axi+1)%3;_agSync();};
 if(_agB)_agB.onclick=()=>{_agEdit=!_agEdit;_agSync();
   if(_agEdit){const i0=_agV&&_agV.getElementsByTagName('input')[0];if(i0){i0.focus();i0.select();}}};
 // Land the current axis on detent t, counted in quarter turns and taken round the circle:
 // 4 is a full turn and comes back to 0, -1 goes to 270. Everything that moves the slider goes
 // through here, so the wrap is the same whether it came from a drag or a key.
 function _agDetent(t){
   t=((t%4)+4)%4;
   const nx=EANG.slice();nx[_axi]=t*90;
   setAngles(nx[0],nx[1],nx[2],true);}
 if(_agEl)_agEl.oninput=()=>{
   // Dragging / clicking the track: step="any" makes the raw value continuous, so snap it to
   // the nearest detent. Past 3.5 the nearest one IS the seam, and 4 folds to 0 - dragging
   // into the last eighth of the track therefore sends the thumb home, which is exactly what
   // going the whole way round does.
   const raw=parseFloat(_agEl.value);
   if(isFinite(raw))_agDetent(Math.round(raw));};
 // Arrow keys, handled instead of the native stepping. A range input clamps at min/max, so at
 // either end the value stopped changing and no input event fired at all - the dial read as
 // jammed. preventDefault takes the key away from the control and steps it ourselves, which
 // also means the step is a whole detent rather than the (max-min)/100 = 0.04 a step="any"
 // range would move. From an off-detent angle (a typed 353) it walks to the next detent in the
 // direction of travel rather than a fixed distance. Home/End/PageUp/PageDown are left to the
 // native control, whose raw value lands back in oninput above and snaps like a drag.
 if(_agEl)_agEl.addEventListener('keydown',e=>{
   let d=0;
   if(e.key==='ArrowRight'||e.key==='ArrowUp')d=1;
   else if(e.key==='ArrowLeft'||e.key==='ArrowDown')d=-1;
   else return;
   e.preventDefault();
   const cur=(((EANG[_axi]%360)+360)%360)/90;     // fractional when the pencil typed the angle
   _agDetent(d>0?Math.floor(cur+1e-9)+1:Math.ceil(cur-1e-9)-1);});
 // restore order: the launcher config (#ang= boot hash) wins, else localStorage
 let _a0=null;
 if(window.__HOSTANG__&&window.__HOSTANG__.length===3)_a0=window.__HOSTANG__;
 else{try{const _s=localStorage.getItem('mohaaViewerAngles');
          if(_s){const _p=_s.split(',').map(Number);
                 if(_p.length===3&&_p.every(v=>isFinite(v)))_a0=_p;}}catch(_e){}}
 if(_a0&&_a0.some(v=>v))setAngles(_a0[0],_a0[1],_a0[2],false); else _agSync();
}
const themeBtn=document.getElementById('bTheme');
function setTheme(light){document.documentElement.classList.toggle('light',light);
  themeBtn.innerHTML=light?'\u263d Dark mode':'\u2600 Light mode';
  try{localStorage.setItem('mohaaViewerTheme',light?'light':'dark');}catch(_e){}
  readTheme();
  // keep the backdrop swatch tracking the theme default (a custom inline --bg wins)
  try{const _b=document.getElementById('bgcol');
    if(_b&&!document.documentElement.style.getPropertyValue('--bg'))_b.value=cssVar('--bg')||_b.value;}catch(_e){}
  requestDraw();}
themeBtn.onclick=()=>setTheme(!document.documentElement.classList.contains('light'));
// theme at load, in priority order:
//   1. the launcher host theme from the URL hash (#theme=light|dark) - the head
//      boot script already put the class on <html>; this reaffirms it and sets the
//      button label / canvas colours with no visible change (no flash).
//   2. an explicit --theme launch flag baked in by the launcher's right-click
//      "Open in viewer light/dark".
//   3. otherwise restore the saved choice (best-effort: file:// storage can be
//      unavailable).
const FORCETHEME='__THEME__';
if(window.__HOSTTHEME__==='light'||window.__HOSTTHEME__==='dark'){setTheme(window.__HOSTTHEME__==='light');}
else if(FORCETHEME==='light'||FORCETHEME==='dark'){setTheme(FORCETHEME==='light');}
else{try{if(localStorage.getItem('mohaaViewerTheme')==='light')setTheme(true);}catch(_e){}}
// DISPLAY section: backdrop colour. Sets an inline --bg on <html> that overrides the
// theme's default - the page body, the 2D canvas backdrop and the WebGL clearColor all
// read TH.bg from that same CSS var, so one override recolours everything. Remembered
// across loads; Default drops the override so the backdrop follows the theme again.
const bgIn=document.getElementById('bgcol'),bgRst=document.getElementById('bgReset');
function applyBackdrop(col,save){
  if(col)document.documentElement.style.setProperty('--bg',col);
  else document.documentElement.style.removeProperty('--bg');
  if(save){try{if(col)localStorage.setItem('mohaaViewerBg',col);
    else localStorage.removeItem('mohaaViewerBg');}catch(_e){}}
  readTheme();bgIn.value=cssVar('--bg')||bgIn.value;requestDraw();}
bgIn.oninput=()=>applyBackdrop(bgIn.value,true);
bgIn.onchange=bgIn.oninput;   // some embedded hosts only commit on dialog close
bgRst.onclick=()=>applyBackdrop(null,true);
try{applyBackdrop(localStorage.getItem('mohaaViewerBg')||null,false);}
catch(_e){applyBackdrop(null,false);}
// Reset: restart the model/effect from time 0 without reloading the page - clears all live
// particles, the per-emitter spawn accumulators and effect schedule, rewinds the effect clock
// and the animation to frame 0. A currently-Playing animation is STOPPED at frame 0 (press
// Play to run it again); the global pause (freeze) state is left untouched.
const resetBtn=document.getElementById('reset');
function resetModel(){parts=[];for(let i=0;i<spawnAcc.length;i++)spawnAcc[i]=0;_triggers=[];
  animStreams=[];                             // fresh sub-stream state, as at load
  // Reset rewinds to frame 0, so the animation's own commands are re-folded from scratch
  // by the applyFrame() at the end of this function. Dropping the hand-overrides here is
  // what makes Reset mean "back to the tik's spawn state plus the user's own hides" -
  // clearing to all-visible instead would leave dday_ranger_private showing twelve
  // bangalores, a state the engine never has since SurfaceCommand ran once at spawn.
  ANIM_SURF.clear();ANIM_SURF_OVR.clear();ANIM_OWNED.clear();surfApply();
  try{surfCountRender();if(surfEl)surfMenuRender();}catch(e){}
  pendingFx=[];_initfxLast=-1e9;_lastWrapFire=-1e9;   // re-arm delayed cmds + init sfx one-shots
  for(let i=0;i<EM.length;i++)emActive[i]=_emDefaultActive(EM[i]);   // startoff back to silent
  playing=false;                              // Reset also halts a running animation at frame 0
  loopAnim=false;loopBtn.classList.remove('on');   // ...and turns the Loop button off (visual+behaviour;
                                              // the saved localStorage preference is left untouched, per the button's promise)
  attPurgeAnim();
  effT=0;_effLast=0;curFrame=0;acc=0;last=performance.now();if(scrub)scrub.value=0;
  updatePlayBtn();applyFrame();}
resetBtn.onclick=resetModel;
// ---- UI keyboard shortcuts + help overlay -------------------------------
// Fly keys (WASDQEC/Space/arrows) and R are handled by the camera listeners
// above; the keys below are chosen to never collide with them. Shortcuts are
// suppressed while a <select>/<input> has focus so typing isn't hijacked.
const helpOv=document.getElementById('helpOv');
function toggleHelp(force){const show=(force!==undefined)?force:(helpOv.style.display==='none');
  helpOv.style.display=show?'flex':'none';}
function closeViewer(){
  // Embedded (URL hash #embed): the WebView2 host listens for 'mohaa-close' and reverts
  // its pane to the start page (App._close_viewer). Standalone browser tab: just close it.
  try{
    if(window.chrome&&window.chrome.webview){window.chrome.webview.postMessage('mohaa-close');return;}
  }catch(_e){}
  try{window.close();}catch(_e){}
}
document.getElementById('bHelp').onclick=()=>toggleHelp();
document.getElementById('helpClose').onclick=()=>toggleHelp(false);
helpOv.addEventListener('click',e=>{if(e.target===helpOv)toggleHelp(false);});
function stepFrame(d){if(curAnim<0)return;const n=DATA.anims[curAnim].frames.length;
  curFrame=((curFrame+d)%n+n)%n;scrub.value=curFrame;applyFrame();}
window.addEventListener('keydown',e=>{
 const tg=e.target&&e.target.tagName;
 if(tg==='SELECT'||tg==='INPUT'||tg==='TEXTAREA')return;
 if(e.ctrlKey||e.metaKey||e.altKey)return;
 switch(e.key){
  case '1':document.getElementById('bTex').click();break;
  case '2':document.getElementById('bMesh').click();break;
  case '3':document.getElementById('bWire').click();break;
  case '4':document.getElementById('bSize').click();break;
  case '5':document.getElementById('bNodes').click();break;
  case '6':document.getElementById('bLbl').click();break;
  // 7 is a no-op unless the current animation actually has a face layer to toggle
  case '7':{const _fb=document.getElementById('bFace');
            if(_fb&&_fb.style.display!=='none')_fb.click();break;}
  case 'p':case 'P':playBtn.click();break;
  case 'f':case 'F':setPaused(!paused);break;
  case 'v':case 'V':(camMode==='free'?document.getElementById('bLock'):document.getElementById('bFree')).click();break;
  case 'l':case 'L':themeBtn.click();break;
  case '[':stepFrame(-1);e.preventDefault();break;
  case ']':stepFrame(1);e.preventDefault();break;
  case 'Backspace':resetModel();e.preventDefault();break;
  case '\\':case '|':document.getElementById('sideTab').click();e.preventDefault();break;
  case 'h':case 'H':case '?':toggleHelp();break;
  case 'Escape':
    // Esc closes the hotkeys panel (if open) AND the whole viewer window at once, so it
    // reverts the launcher to its start page from any state. closeViewer() posts
    // 'mohaa-close' up to the host (or window.close() standalone); toggleHelp(false) makes
    // sure the panel doesn't linger on the last frame before the pane is torn down.
    if(helpOv.style.display!=='none') toggleHelp(false);
    closeViewer();
    break;
 }
});
// ============================== WebGL renderer ===============================
// Hybrid pipeline. WebGL renders the grid + skinned model - textured, flat-shaded
// mesh, wireframe and pulse-overlay passes - with a TRUE per-pixel depth buffer:
// no painter's centroid sort, no nested-surface ordering heuristics, full-quality
// textures while the camera moves, and perspective-correct texturing (the 2D path
// could only do affine). Canvas 2D on top keeps what it is best at: autosprite
// billboards, all particles (sprites / VSS puffs / debris meshes), bone nodes,
// labels and the setsize box - which were always drawn over the model anyway.
// If WebGL is unavailable, GLR stays null and draw2DScene() renders exactly as
// the pre-hybrid viewer did.
//
// world -> clip-space matrix reproducing project() EXACTLY (same yaw/pitch/roll,
// center, dist, pan and focal math) so the GL model and every 2D overlay element
// land on the same pixels. Kept top-level (not closed over by initGLRenderer)
// so it can be tested against project() directly.
function buildMVP(nearP,farP){
 const ca=Math.cos(yaw),sa=Math.sin(yaw),ce=Math.cos(pitch),se=Math.sin(pitch),
       cr=Math.cos(roll),sr=Math.sin(roll);
 // linear part of the camera transform (project() minus the center translation):
 // yaw about Y, pitch, then roll about the view axis.
 function cam(dx,dy,dz){
   const x1=ca*dx+sa*dz,z1=-sa*dx+ca*dz,y1=dy;
   const y2=ce*y1-se*z1,z2=se*y1+ce*z1,x2=x1;
   return[cr*x2-sr*y2,sr*x2+cr*y2,z2];}
 const c0=cam(1,0,0),c1=cam(0,1,0),c2=cam(0,0,1);
 // translation column: cam(-center), plus the orbit distance on the view axis
 const t=[-(c0[0]*cx+c1[0]*cy+c2[0]*cz),
          -(c0[1]*cx+c1[1]*cy+c2[1]*cz),
          -(c0[2]*cx+c1[2]*cy+c2[2]*cz)+dist];
 // projection: NDC.x = (f2w*qx + panX*qz)/qz, NDC.y = (f2h*qy - panY*qz)/qz -
 // algebraically identical to project()'s screen mapping.
 const focal=Math.min(W,H)*0.9, f2w=focal/((W/2)||1), f2h=focal/((H/2)||1);
 const A=(farP+nearP)/(farP-nearP), B=-2*farP*nearP/(farP-nearP);
 const M=new Float32Array(16);        // column-major for uniformMatrix4fv
 function col(j,vx,vy,vz){
   M[j*4+0]=f2w*vx+panX*vz;
   M[j*4+1]=f2h*vy-panY*vz;
   M[j*4+2]=A*vz+(j===3?B:0);
   M[j*4+3]=vz;}
 col(0,c0[0],c0[1],c0[2]);col(1,c1[0],c1[1],c1[2]);col(2,c2[0],c2[1],c2[2]);
 col(3,t[0],t[1],t[2]);
 return M;}
function initGLRenderer(){
 let gl=null,isGL2=false;
 try{
   const opts={alpha:false,antialias:true,depth:true};
   gl=glcv.getContext('webgl2',opts);isGL2=!!gl;
   if(!gl)gl=glcv.getContext('webgl',opts)||glcv.getContext('experimental-webgl',opts);
 }catch(e){gl=null;}
 if(!gl)return null;
 // flat shading derives the face normal in the fragment shader (dFdx/dFdy):
 // core in WebGL2, extension in WebGL1 - without it, fall back to the 2D path.
 if(!isGL2&&!gl.getExtension('OES_standard_derivatives'))return null;
 const NV=DATA.verts.length;
 let IdxArr=Uint16Array,idxType=gl.UNSIGNED_SHORT;
 if(NV>65535){
   if(isGL2||gl.getExtension('OES_element_index_uint')){IdxArr=Uint32Array;idxType=gl.UNSIGNED_INT;}
   else return null;                  // huge mesh on ancient GL1: keep the proven 2D path
 }
 function mkShader(type,src){const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);
   if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)){try{console.error('GL shader: '+gl.getShaderInfoLog(s));}catch(_e){}return null;}
   return s;}
 // uTexRot=(cos,sin,enabled): a per-surface texcoord spin about (0.5,0.5) for shaders
 // whose base stage has `tcmod rotate` (RB_CalcRotateTexMatrix, tr_shade_calc.c:809-826)
 // - the aircraft propeller discs (prop / c47prop). enabled<=0.5 leaves UVs untouched.
 // The transform is affine, so rotating per-vertex then interpolating vUV is exact.
 const VSRC='attribute vec3 aPos;attribute vec2 aUV;uniform mat4 uMVP;uniform vec3 uTexRot;'+
   'varying vec3 vPos;varying vec2 vUV;'+
   'void main(){vPos=aPos;vec2 uv=aUV;'+
   ' if(uTexRot.z>0.5){vec2 d=uv-vec2(0.5);'+
   '   uv=vec2(uTexRot.x*d.x-uTexRot.y*d.y, uTexRot.y*d.x+uTexRot.x*d.y)+vec2(0.5);}'+
   ' vUV=uv;gl_Position=uMVP*vec4(aPos,1.0);}';
 // uMode: 0 flat-shaded palette fill / 1 textured+shade / 2 blendfunc-add texture /
 //        3 pulse overlay (additive, x wave glow) / 4 unshaded lines (grid, wire)
 // shade math mirrors the 2D path: sh=0.35+0.65*|dot(N,L)|; textured surfaces get
 // the same darken the black overlay produced there: rgb*(1-(1-sh)*0.55).
 const FSRC=(isGL2?'':'#extension GL_OES_standard_derivatives : enable\n')+
   'precision mediump float;varying vec3 vPos;varying vec2 vUV;'+
   'uniform int uMode;uniform vec3 uColor;uniform float uAlpha;uniform float uAtest;uniform sampler2D uTex;'+
   'void main(){'+
   ' if(uMode==4){gl_FragColor=vec4(uColor,uAlpha);return;}'+
   ' vec3 N=cross(dFdx(vPos),dFdy(vPos));float nl=length(N);'+
   ' N=(nl>0.0)?N/nl:vec3(0.0,1.0,0.0);'+
   ' vec3 L=normalize(vec3(0.4,0.8,0.45));float s=0.35+0.65*abs(dot(N,L));'+
   ' if(uMode==0){gl_FragColor=vec4(uColor*s,1.0);return;}'+
   ' vec4 t=texture2D(uTex,vUV);'+
   // uAlpha carries alphaGen distFade; uAtest carries the alphaFunc threshold (0 = none).
   // Tested stages resolve to full opacity, matching the engine's binary discard.
   ' if(uMode==1){float A=t.a*uAlpha;'+
   '   if(uAtest>0.0){if(A<uAtest)discard;A=1.0;}else if(A<0.01)discard;'+
   '   gl_FragColor=vec4(t.rgb*(1.0-(1.0-s)*0.55),A);return;}'+
   ' if(uMode==2){gl_FragColor=vec4(t.rgb*t.a,1.0);return;}'+   // ONE,ONE: matches canvas lighter
   ' gl_FragColor=vec4(t.rgb*t.a*uAlpha,1.0);}';                // pulse: glow as brightness
 const vsh=mkShader(gl.VERTEX_SHADER,VSRC),fsh=mkShader(gl.FRAGMENT_SHADER,FSRC);
 if(!vsh||!fsh)return null;
 const prog=gl.createProgram();gl.attachShader(prog,vsh);gl.attachShader(prog,fsh);gl.linkProgram(prog);
 if(!gl.getProgramParameter(prog,gl.LINK_STATUS))return null;
 gl.useProgram(prog);
 const aPos=gl.getAttribLocation(prog,'aPos'),aUV=gl.getAttribLocation(prog,'aUV');
 const uMVP=gl.getUniformLocation(prog,'uMVP'),uMode=gl.getUniformLocation(prog,'uMode'),
       uColor=gl.getUniformLocation(prog,'uColor'),uAlpha=gl.getUniformLocation(prog,'uAlpha'),
       uTex=gl.getUniformLocation(prog,'uTex'),uTexRot=gl.getUniformLocation(prog,'uTexRot'),
       uAtest=gl.getUniformLocation(prog,'uAtest');
 gl.uniform1i(uTex,0);
 gl.enableVertexAttribArray(aPos);
 // vertex positions = the live skinned model; re-uploaded whenever skin() runs
 const posBuf=gl.createBuffer();
 gl.bindBuffer(gl.ARRAY_BUFFER,posBuf);gl.bufferData(gl.ARRAY_BUFFER,model,gl.DYNAMIC_DRAW);
 let dirty=false;
 const UV=DATA.uvs,hasUV=!!(UV&&UV.length);
 let uvBuf=null;
 if(hasUV){uvBuf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,uvBuf);
   gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(UV),gl.STATIC_DRAW);}
 // per-surface triangle + deduped wireframe-edge index buffers (surface tris are
 // contiguous ranges of DATA.tris, so hidden/billboarded surfaces skip cleanly)
 function buildSurfBufs(){return LSR.map(s=>{
   const tris=[];for(let t=s.start;t<s.end;t++){const tr=LT[t];tris.push(tr[0],tr[1],tr[2]);}
   const eset=new Set(),edges=[];
   for(let t=s.start;t<s.end;t++){const tr=LT[t];
     for(let k=0;k<3;k++){const a2=tr[k],b2=tr[(k+1)%3];
       const key=a2<b2?(a2+'_'+b2):(b2+'_'+a2);
       if(!eset.has(key)){eset.add(key);edges.push(a2,b2);}}}
   const tb=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,tb);
   gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new IdxArr(tris),gl.STATIC_DRAW);
   const eb=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,eb);
   gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new IdxArr(edges),gl.STATIC_DRAW);
   return{tb:tb,tn:tris.length,eb:eb,en:edges.length};});}
 let surfBufs=buildSurfBufs();
 // fixed ground grid, same anchors as the 2D grid (cx0/gy/cz0, radius-scaled)
 const gpts=[];{const g=rad,gy=groundY;
   for(let i=-4;i<=4;i++){gpts.push(cx0+i*g/4,gy,cz0-g, cx0+i*g/4,gy,cz0+g);
     gpts.push(cx0-g,gy,cz0+i*g/4, cx0+g,gy,cz0+i*g/4);}}
 const gridBuf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,gridBuf);
 gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(gpts),gl.STATIC_DRAW);
 const gridN=gpts.length/3;
 function texFor(img){if(img._glTex)return img._glTex;
   let src=img;const iw=img.naturalWidth||img.width||1,ih=img.naturalHeight||img.height||1;
   if(!isGL2&&(((iw&(iw-1))!==0)||((ih&(ih-1))!==0))){
     // WebGL1 REPEAT/mipmaps need power-of-two: stretch onto a POT canvas
     // (normalized UVs are unaffected by the stretch)
     const pot=v=>{let p=1;while(p<v)p<<=1;return p;};
     const c2=document.createElement('canvas');c2.width=pot(iw);c2.height=pot(ih);
     c2.getContext('2d').drawImage(img,0,0,c2.width,c2.height);src=c2;}
   const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);
   gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);   // UVs address the image top-down, like the 2D path
   gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,src);
   // clampmap propeller textures clamp to their transparent border as the spinning
   // texcoords sweep past [0,1] (clampmap -> GL_CLAMP, tr_image.c); everything else tiles
   // (tire treads to u~9, body panels to u~5). Wrap is fixed per texture object, and a
   // clampmap image is only ever used by its own clampmap surface, so this never conflicts.
   const _wrap=img._clamp?gl.CLAMP_TO_EDGE:gl.REPEAT;
   gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,_wrap);
   gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,_wrap);
   gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);
   gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
   gl.generateMipmap(gl.TEXTURE_2D);
   img._glTex=t;return t;}
 // per-surface texcoord spin uniform: propeller discs (prop / c47prop) whose base stage
 // carries `tcmod rotate <deg/sec>`. Engine: degs = -degsPerSecond * shaderTime
 // (RB_CalcRotateTexMatrix, tr_shade_calc.c:809-826); cos/sin of that angle drive the
 // vertex-shader rotation about (0.5,0.5). effT is the shared effect clock (frozen while
 // paused), so a paused aircraft holds its blade angle instead of snapping on resume.
 function setTexRot(si){
   const r=LTEX[si]&&LTEX[si].texrotate;
   if(r){const th=-r*effT*Math.PI/180.0;gl.uniform3f(uTexRot,Math.cos(th),Math.sin(th),1.0);}
   else gl.uniform3f(uTexRot,1.0,0.0,0.0);}
 function hexRGB(h){if(!h)return[0,0,0];h=(''+h).trim();
   if(h[0]==='#'){if(h.length>=7)return[parseInt(h.slice(1,3),16)/255,parseInt(h.slice(3,5),16)/255,parseInt(h.slice(5,7),16)/255];
     if(h.length>=4)return[parseInt(h[1]+h[1],16)/255,parseInt(h[2]+h[2],16)/255,parseInt(h[3]+h[3],16)/255];}
   const m=h.match(/rgba?\(([^)]+)\)/);
   if(m){const p=m[1].split(',');return[(+p[0]||0)/255,(+p[1]||0)/255,(+p[2]||0)/255];}
   return[0,0,0];}
 // Backface cull parity with the 2D path: skin() emits (X,Z,Y), so a MOHAA CCW
 // front face projects with NEGATIVE screen-space (y-down) area - which is CCW in
 // GL's y-up NDC. Hence frontFace(CCW)/cullFace(BACK) drops exactly the triangles
 // the 2D `_a2<0` test kept out.
 function setCull(on){if(on){gl.enable(gl.CULL_FACE);gl.cullFace(gl.BACK);gl.frontFace(gl.CCW);}
   else gl.disable(gl.CULL_FACE);}
 function bindGeom(){gl.bindBuffer(gl.ARRAY_BUFFER,posBuf);
   gl.vertexAttribPointer(aPos,3,gl.FLOAT,false,0,0);
   if(hasUV&&aUV>=0){gl.enableVertexAttribArray(aUV);gl.bindBuffer(gl.ARRAY_BUFFER,uvBuf);
     gl.vertexAttribPointer(aUV,2,gl.FLOAT,false,0,0);}
   else if(aUV>=0){gl.disableVertexAttribArray(aUV);gl.vertexAttrib2f(aUV,0,0);}}
 function render(){
   gl.viewport(0,0,glcv.width,glcv.height);
   const bg=hexRGB(TH.bg);
   gl.clearColor(bg[0],bg[1],bg[2],1);gl.clearDepth(1);
   gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.depthMask(true);
   gl.disable(gl.BLEND);gl.disable(gl.POLYGON_OFFSET_FILL);
   gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
   const nearP=Math.max(0.05,rad*0.002),farP=dist+rad*40;
   gl.useProgram(prog);
   gl.uniformMatrix4fv(uMVP,false,buildMVP(nearP,farP));
   gl.uniform3f(uTexRot,1.0,0.0,0.0);   // default: no texcoord spin (set per prop surface below)
   if(dirty){gl.bindBuffer(gl.ARRAY_BUFFER,posBuf);gl.bufferData(gl.ARRAY_BUFFER,model,gl.DYNAMIC_DRAW);dirty=false;}
   // grid first with depth writes OFF: the model always paints over it, matching
   // the 2D paint order, and grid lines never punch holes in the depth buffer.
   setCull(false);gl.depthMask(false);
   gl.bindBuffer(gl.ARRAY_BUFFER,gridBuf);gl.vertexAttribPointer(aPos,3,gl.FLOAT,false,0,0);
   if(aUV>=0){gl.disableVertexAttribArray(aUV);gl.vertexAttrib2f(aUV,0,0);}
   const gc=hexRGB(TH.grid);
   gl.uniform1i(uMode,4);gl.uniform3f(uColor,gc[0],gc[1],gc[2]);gl.uniform1f(uAlpha,1);
   gl.drawArrays(gl.LINES,0,gridN);
   gl.depthMask(true);
   // effect-dummy anchors (+dontdraw) never render their placeholder mesh
   if(DATA.dontdraw||!(view.tex||view.mesh||view.wire))return;
   bindGeom();
   // classify surfaces for this frame (mirrors the per-triangle rules of the 2D path,
   // which were constant per surface anyway)
   const sr=DATA.surfRanges,solid=[],adds=[],pulses=[],wires=[];
   for(let si=0;si<sr.length;si++){const s=sr[si];
     if(hiddenSurf.has(si))continue;                     // +nodraw (server anim command)
     if(view.treesprite&&!isLodSprite(si))continue;      // Tree Sprite: stand-in only
     const tex=LTEX[si];
     if(tex&&tex.autosprite&&view.sprite)continue;       // billboarded on the 2D overlay
     const img=(view.tex&&tex)?curImg(tex):null;
     const textured=!!(img&&hasUV);
     const add=!!(tex&&tex.additive);
     // alphaGen distFade, same per-surface sample the 2D path takes (surface centre).
     const _cc=surfCenterRadius(si);
     const _fa=_cc?distFadeAlpha(tex,_cc):1;
     if(_fa<=0.004)continue;                            // past near+range the engine draws nothing
     const _atv=(tex&&tex.atest==='ge128')?0.5:((tex&&tex.atest==='gt0')?0.004:0);
     // same cull exemptions as 2D: additive / pulse-only ghosts / autosprite planes /
     // two-sided surfaces, and no culling at all in pure-wireframe view
     const cull=!add&&!(tex&&(tex.pulseOnly||tex.autosprite))&&
                !((tex&&tex.twosided)||(s&&s.twosided))&&(view.tex||view.mesh);
     if(textured){(add?adds:solid).push({si:si,mode:add?2:1,img:img,cull:cull,fa:_fa,at:_atv});}
     else if(view.mesh&&!(tex&&tex.pulseOnly)){solid.push({si:si,mode:0,img:null,cull:cull,fa:_fa,at:0});}
     if(view.tex&&hasUV&&tex&&tex.pulse&&tex.pulse.img&&tex.pulse.img._ok){
       const g=pulseGlow(tex.pulse);
       if(g>0.003)pulses.push({si:si,img:tex.pulse.img,g:g});}
     if(view.wire)wires.push({si:si,cull:cull,dark:(view.mesh||textured)});}
   // push fills back a hair so the wireframe lines win the depth tie
   gl.enable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(1,1);
   gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
   for(const d of solid){setCull(d.cull);
     gl.uniform1i(uMode,d.mode);
     gl.uniform1f(uAlpha,d.fa===undefined?1:d.fa);gl.uniform1f(uAtest,d.at||0);
     if(d.mode===0){const pc=hexRGB(palette[d.si%palette.length]);gl.uniform3f(uColor,pc[0],pc[1],pc[2]);gl.uniform3f(uTexRot,1.0,0.0,0.0);}
     else{gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,texFor(d.img));setTexRot(d.si);}
     const b=surfBufs[d.si];gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,b.tb);
     gl.drawElements(gl.TRIANGLES,b.tn,idxType,0);}
   // additive stages after all solid geometry: depth-TESTED against it (an occluded
   // flame stays hidden) but never depth-written (glow does not block anything)
   gl.depthMask(false);gl.blendFunc(gl.ONE,gl.ONE);
   gl.uniform1i(uMode,2);setCull(false);
   for(const d of adds){
     gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,texFor(d.img));setTexRot(d.si);
     const b=surfBufs[d.si];gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,b.tb);
     gl.drawElements(gl.TRIANGLES,b.tn,idxType,0);}
   gl.uniform3f(uTexRot,1.0,0.0,0.0);   // pulse/wire passes below never spin their texcoords
   gl.uniform1i(uMode,3);
   for(const d of pulses){gl.uniform1f(uAlpha,d.g);
     gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,texFor(d.img));
     const b=surfBufs[d.si];gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,b.tb);
     gl.drawElements(gl.TRIANGLES,b.tn,idxType,0);}
   gl.disable(gl.POLYGON_OFFSET_FILL);
   if(view.wire){gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
     gl.uniform1i(uMode,4);gl.lineWidth(1);
     const slate=hexRGB('#3a4654');
     for(const d of wires){setCull(d.cull);
       if(d.dark){gl.uniform3f(uColor,0,0,0);gl.uniform1f(uAlpha,0.18);}
       else{gl.uniform3f(uColor,slate[0],slate[1],slate[2]);gl.uniform1f(uAlpha,1);}
       const b=surfBufs[d.si];gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,b.eb);
       gl.drawElements(gl.LINES,b.en,idxType,0);}}
   gl.depthMask(true);
 }
 function doResize(){glcv.width=Math.max(1,Math.round(W*DPR));glcv.height=Math.max(1,Math.round(H*DPR));}
 doResize();
 return{render:render,resize:doResize,markDirty:function(){dirty=true;},
   // attachments add surfaces, so the per-surface index buffers (and the UV buffer)
   // have to be re-cut. Positions come free: posBuf is uploaded from `model`, which
   // already carries the attachment vertices appended after the host's.
   rebuildSurfaces:function(){
     try{for(const b of surfBufs){gl.deleteBuffer(b.tb);gl.deleteBuffer(b.eb);}}catch(e){}
     surfBufs=buildSurfBufs();
     if(uvBuf&&LUV&&LUV.length){gl.bindBuffer(gl.ARRAY_BUFFER,uvBuf);
       gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(LUV),gl.STATIC_DRAW);}
     dirty=true;}};
}
try{GLR=initGLRenderer();}catch(e){GLR=null;try{console.error('WebGL init failed, using 2D renderer: '+e);}catch(_e){}}
// A GL context created with alpha:false makes the #gl canvas PERMANENTLY opaque
// black, even when the renderer init then bails (missing extension / shader
// failure) and GLR stays null. The 2D fallback paints on the transparent #c
// canvas ABOVE it, so that dead black canvas becomes the visible backdrop and no
// theme / backdrop-picker colour can ever show through. Hide it: with #gl gone,
// the page background (var(--bg)) is the backdrop again, exactly like the pure
// 2D path - and the backdrop colour picker works in both render paths.
if(!GLR){try{glcv.style.display='none';}catch(_e){}}
readTheme();
resize();
</script></body></html>"""

def pick_base_anim(skc_files, skd, model_stem):
    skel={b["name"] for b in skd["bones"]}
    numBone=skd["numBone"]
    parsed=[]
    for f in skc_files:
        try: parsed.append((f,parse_skc(f)))
        except Exception: pass
    if not parsed: return None,[]
    def overlap(d):
        return len({n.rsplit(" ",1)[0] for n in d["names"]} & skel)
    # only consider anims that actually drive this skeleton
    matching=[(f,d) for f,d in parsed if overlap(d)>0]
    pool=matching if matching else parsed
    mo=max(overlap(d) for f,d in pool)
    # restrict to anims that cover nearly the whole skeleton, then pick the calmest "rest" pose
    near=[(f,d) for f,d in pool if overlap(d)>=mo-max(3,mo//10)] or pool
    MOTION=("run","walk","sprint","crouch","prone","death","die","dead","fall","jump",
            "climb","hit","pain","fire","reload","aim","attack","throw","turn","strafe")
    def score(fd):
        f,d=fd; nm=os.path.basename(f).lower(); s=overlap(d)*10
        if nm==model_stem.lower()+".skc": s+=1000      # the model's own anim is the truest rest
        if "idle" in nm: s+=500
        if "stand" in nm or "stance" in nm: s+=400
        if any(k in nm for k in MOTION): s-=300         # avoid freezing mid-action
        if overlap(d)>=numBone: s+=50
        s+=d["numChan"]/1000.0; return s
    return max(near,key=score),parsed

def open_file(path):
    try:
        if sys.platform.startswith("win"): os.startfile(path)
        # NOT os.system(f'open "{path}"'): that hands the path to a shell, so a quote or
        # $(...) in it executes. Argument-vector form has no shell to inject into.
        elif sys.platform=="darwin": subprocess.run(["open",path],check=False)
        # as_uri() percent-encodes and emits the three-slash form; the old "file://"+path
        # gave file://C:/... on Windows (C: parsed as a HOSTNAME) and broke outright on any
        # path containing '#', '%' or non-ASCII characters.
        else: webbrowser.open(pathlib.Path(os.path.abspath(path)).as_uri())
    except Exception as e:
        print(f"  (could not auto-open: {e})")


def _rest_pose_variants(skd, base_channels):
    """Build alternate standing rest poses as 1-frame 'animations' so the dropdown can
    switch between them for visual A/B against in-game. Returns a list of anims_data entries."""
    if not base_channels: return []
    bones=skd["bones"]; names={b["name"] for b in bones}
    if not ({"Bip01 Spine","Bip01 Pelvis"} <= names): return []
    out=[]
    # 1) flat feet: foot rot -> identity (toe forward, level) instead of the template's downward pitch
    flat=dict(base_channels)
    for k in list(flat):
        if k.endswith(" Foot rot"): flat[k]=[0.0,0.0,0.0,1.0]
    out.append({"name":"» REST: flat feet","data":{"frameTime":0.1,"frames":[flat]}})
    # 2) FK legs (no IK): drop the Foot pos targets so legs pose purely from rotFK
    fk=dict(base_channels)
    for k in list(fk):
        if k.endswith(" Foot pos"): del fk[k]
    out.append({"name":"» REST: FK legs (no IK)","data":{"frameTime":0.1,"frames":[fk]}})
    # 3) flat feet + FK legs
    ff=dict(fk)
    for k in list(ff):
        if k.endswith(" Foot rot"): ff[k]=[0.0,0.0,0.0,1.0]
    out.append({"name":"» REST: flat feet + FK legs","data":{"frameTime":0.1,"frames":[ff]}})
    return out


def main(argv):
    args=[a for a in argv[1:] if not a.startswith("--")]
    flags={a for a in argv[1:] if a.startswith("--")}
    if not args:
        print("usage: python3 mohaa_view.py <model.skd> [--anim base.skc] [--no-open] [--3dviewer]")
        return 1
    skd_path=args[0]
    emitters=[]
    dontdraw=False
    fxcmds=None
    initfx=None              # init{client{}} `sfx <spawncmd> (...)` one-shots, fired at load
    tiknodraw=[]             # setup/init-server `surface <n> +nodraw` ops applied at spawn
    setsize=None             # bounding box (mins,maxs) from the `setsize` init command or a .map, if any
    mscale=1.0               # tik setup `scale` (load_scale); used to place the setsize wireframe
    mclassname=None          # tik init/server `classname` (case-sensitive), for the info panel
    extra_skds=[]            # attached part models (head/hands/...) for .tik assembly
    tikanims=[]              # the tik's animations{} aliases (name -> .skc + frame commands)
    if skd_path.lower().endswith(".tik"):
        # emitter / effect tik: parse its particle emitters and resolve its skelmodel
        # (placed next to the tik by the launcher) so we get a still frame to anchor them.
        try: _tt=open(skd_path,"r",encoding="latin-1",errors="replace").read()   # match the VFS codec
        except OSError: _tt=""
        emitters=parse_tik_emitters(_tt)
        # the tik's animations{} section: every named anim alias, its .skc, and its
        # per-anim client (tagspawn/originspawn bursts) / server (surface +/-nodraw)
        # frame commands (TIKI_ParseAnimations, tiki_parse.cpp:397-)
        tikanims=parse_tik_animations(_tt)
        # the start-anim client block may sequence emitters on/off over time (e.g.
        # adamspark: spark burst -> corona flash -> lingering smoke). Capture that so the
        # viewer fires the timed sequence instead of running every emitter continuously.
        # AUTO-RUN SCHEDULE RETIRED: init-client emitters WITHOUT startoff run continuously
        # from entity spawn in-game (emitterthing_t::GetEmitTime seeds active=!startoff,
        # cg_commands.h:531-557) - the `start` anim's emitteron/emitteroff windows only
        # ever execute when the level triggers that anim. The old viewer behaviour compiled
        # those windows into a load-time schedule and PULSED the emitters (adamspark name1
        # fired in short bursts synced to the corona cycle instead of streaming at
        # spawnrate 50 like the idling in-game entity). The windows still apply live when
        # the user plays `start`: tik_anim_fx queues the same emitteron/emitteroff toggles
        # (with commanddelay offsets) on playback.
        fxcmds=None
        # init{client{}} `sfx originspawn ( ... )` one-shot blocks (grenexp_water):
        # the engine executes the registered command list when the effect spawns
        # (StartSFXCommand, cg_commands.cpp:1623-1678), so the viewer fires them at
        # load / Reset (and, with Loop on, re-fires each period so they stay watchable).
        _sfxblocks=parse_tik_init_sfx(_tt)
        if _sfxblocks:
            _sp=[]; _per=0.0
            for _s in _sfxblocks:
                prm=dict(_s["prm"]); prm["name"]="initfx_%d"%len(emitters)
                prm["kind"]=_s["cmd"]; prm["animfx"]=True
                if _s["tag"]: prm["tag"]=_s["tag"]
                emitters.append(prm)
                _sp.append({"em":len(emitters)-1,"delay":round(_s["delay"],4)})
                _per=max(_per,_s["delay"]+float(prm.get("life") or 1.0))
            initfx={"spawn":_sp,"period":round(max(1.0,_per),3)}
        # `startoff` emitters must stay silent until an animation fires `emitteron`
        # (emitterthing_t::GetEmitTime seeds et->active=!startoff, cg_commands.h:
        # 531-557; EmitterStartOff, cg_commands.cpp:2112-2121). Drop them from the
        # auto-run start-anim schedule - the per-anim emit toggles drive them instead.
        # Emitters WITHOUT startoff keep the signed-off schedule behaviour (adamspark).
        if fxcmds and fxcmds.get("sched"):
            _off={e.get("name") for e in emitters if "startoff" in (e.get("flags") or [])}
            for _nm in list(fxcmds["sched"]):
                if _nm in _off: del fxcmds["sched"][_nm]
            if not fxcmds["sched"]: fxcmds=None
        setsize=parse_tik_setsize(_tt)   # bounding box for the info panel (if the tik declares one)
        mscale=parse_tik_scale(_tt)      # load_scale, to align the setsize wireframe with the model
        mclassname=parse_tik_classname(_tt)   # classname for the info panel (if the tik declares one)
        # classname animate/Animate fx tiks (firefill, explosion_mine, mortar_dirt) sit idle and
        # hidden in-game until the level triggers their `start` anim: the Animate entity spawns
        # with rendereffects +dontdraw and its client emitters are not seen running until the
        # start anim's `enter emitteron <n>` (confirmed against in-game footage; effectentity
        # tiks like tankdust/m1dust DO emit from spawn). Emulate by seeding every init-client
        # emitter of such a tik as startoff - the start anim's emitteron flips them live, and
        # stop's emitteroff silences them, exactly the observed sequencing.
        #
        # BUT only the HIDDEN fx dummies (rendereffects +dontdraw) behave that way. A DRAWN
        # `classname animate` model - e.g. the destroyed statweapons flak88_d / 20mmflak_d,
        # which have no +dontdraw and only an `idle` anim (no `start`/emitteron) - keeps its
        # tag_barrel smoke/fire emitters running continuously from spawn (engine default is
        # active=!startoff, cg_commands.h:531-557, and the tik carries no startoff). Forcing
        # startoff on those made every barrel emitter permanently silent - nothing ever fired
        # emitteron - so the destroyed guns showed no effects at all. Gate the force-add on
        # +dontdraw so drawn animate models emit as authored.
        _is_hidden_fx=bool(re.search(r'rendereffects\s+\+?dontdraw', _tt, re.I))
        if (mclassname or "").lower()=="animate" and _is_hidden_fx:
            for _e in emitters:
                if "startoff" not in _e["flags"]: _e["flags"].append("startoff")
            # the startoff-vs-schedule pruning above ran before this gating; re-apply it so a
            # gated emitter never auto-runs off the load-time schedule (the per-anim emitteron
            # toggles drive it instead).
            if fxcmds and fxcmds.get("sched"):
                _off={e.get("name") for e in emitters if "startoff" in (e.get("flags") or [])}
                for _nm in list(fxcmds["sched"]):
                    if _nm in _off: del fxcmds["sched"][_nm]
                if not fxcmds["sched"]: fxcmds=None
        # effect dummies declare `rendereffects +dontdraw`: the engine never draws the
        # anchor mesh (dummy3), only its emitted particles. Honour that so the viewer
        # doesn't show the placeholder "gem". fire.tik has no +dontdraw -> stays visible.
        # ALSO honour the server `hide` command and `surface all +nodraw`, which hide the mesh
        # the same way (entity.h:763 hideModel -> RF_DONTDRAW; all-surface nodraw): fx_cannonsmoke
        # / fx_lowsmoke use `hide ghost` on a dummy3 anchor, fx_nebelwerfer uses `surface all
        # +nodraw` on the rocket shell - all three showed a stray model at origin before this.
        dontdraw=bool(re.search(r'rendereffects\s+\+?dontdraw', _tt, re.I)) or parse_tik_server_hidden(_tt)
        # PER-SURFACE nodraw the tik applies at spawn - `surface bang* +nodraw` in
        # init{server{}} (Entity::SurfaceCommand, entity.cpp:4158) or `surface <n> flags
        # nodraw` in setup{} (TIKI_ParseSurfaceFlag, tiki_parse.cpp:513). Distinct from the
        # whole-model hide above: dday_ranger_private carries the bangalore_assembly mesh but
        # keeps its twelve bang* surfaces off until the assembly animation reveals them, and
        # the viewer drew all twelve floating through the model instead.
        tiknodraw=parse_tik_static_nodraw(_tt)
        _tikbase=os.path.basename(skd_path)
        _parts=parse_tik_skelmodels(_tt)
        _skel=_parts[0][1] if _parts else parse_tik_setup_head(_tt)[1]
        _tf=os.path.dirname(os.path.abspath(skd_path)); _found=None
        def _resolve_part(ps):
            for c in (os.path.join(_tf,os.path.basename(ps)), os.path.join(_tf,ps)):
                if os.path.exists(c): return c
            return None
        if _skel: _found=_resolve_part(_skel)
        # attached parts (head, hands, ...) live next to the tik too (launcher-extracted)
        for (_pp,_ps) in _parts[1:]:
            c=_resolve_part(_ps)
            if c: extra_skds.append(c)
        print(f"<><><> {_tikbase} <><><>  ({len(emitters)} emitter(s))")
        if _found:
            skd_path=_found
        else:
            print("- skelmodel not found next to tik; cannot render still frame yet"); return 1
    elif not skd_path.lower().endswith((".skd",".skb")):
        print("first argument must be a .skd, .skb or .tik file"); return 1
    if not os.path.exists(skd_path):
        print("file not found:", skd_path); return 1

    folder=os.path.dirname(os.path.abspath(skd_path))
    stem=os.path.splitext(os.path.basename(args[0]))[0]
    # setsize fallback: when the tik declares no `setsize`, derive the object's box from a sibling
    # .map (the model's world-unit clip hull, e.g. models/static/indycrate.map). The launcher extracts
    # the whole model folder next to the .skd, so we look for <skd-stem>.map and <input-stem>.map there.
    if setsize is None:
        _seen=set()
        for _st in (os.path.splitext(os.path.basename(skd_path))[0], stem):
            _mp=os.path.join(folder,_st+".map")
            if _mp in _seen: continue
            _seen.add(_mp)
            if os.path.exists(_mp):
                _mb=parse_map_bounds(_mp)
                if _mb:
                    setsize=_mb
                    print(f"- setsize from {os.path.basename(_mp)}: {_mb[0]} .. {_mb[1]} (world units)")
                    break
    print(f"<><><> {os.path.basename(skd_path)} <><><>")
    skd=parse_skd(skd_path)
    if extra_skds:
        merged=[skd]
        for ep in extra_skds:
            try: merged.append(parse_skd(ep))
            except Exception as e: print(f"- could not load part {os.path.basename(ep)}: {e}")
        if len(merged)>1:
            skd=merge_skds(merged)
            print(f"- assembled {len(merged)} parts (body + {len(merged)-1} attached) "
                  f"-> {skd['numBone']} bones, {len(skd['surfaces'])} surfaces")
    print(f"- {skd['numBone']} bones, {len(skd['surfaces'])} surfaces")

    # ---- ON-DEMAND ANIMATION BUILD ------------------------------------------
    # `--animbuild=<id>[,<id>...] --animsrc=<dir> --animout=<dir>`: solve just those
    # animations against this skeleton and write one JSONP sidecar each, then stop -
    # no OBJ, no HTML, no textures. This is what the launcher runs when the viewer
    # asks for an animation the page was not built with: the .skc has already been
    # pulled out of the paks to <animsrc>/<id>.skc, and the result lands in the
    # folder beside the page as <animout>/a<id>.js, where it stays cached.
    _abuild=[]; _asrc=None; _aout=None; _acat=None; _alegs=None; _apair={}
    _atbuild=None; _atkey=None; _atout=None
    for a in argv[1:]:
        # += not =: this used to ASSIGN, so a second --animbuild= threw the first away.
        # The launcher appends the facial sibling after the body id, so the body animation
        # was silently dropped and only the face got built ("Done - 1/1 animation(s)
        # built" followed by "<body>: build wrote no animation file").
        if a.startswith("--animbuild="):
            for x in a.split("=",1)[1].split(","):
                if x and x not in _abuild: _abuild.append(x)
        # --animpair=<bodyid>:<facestem>[,...]  Explicit pairing, because the workspace
        # names every extracted .skc after its catalogue ID - so "throwaway.skc" is on disk
        # as "acca77fa614c5.skc" and looking for a "<stem>MORPH.skc" neighbour can never
        # match. The launcher knows the real pairing, so it just says so.
        elif a.startswith("--animpair="):
            for pr in a.split("=",1)[1].split(","):
                if ":" in pr:
                    k,v=pr.split(":",1)
                    if k and v: _apair[k]=v
        elif a.startswith("--animsrc="): _asrc=a.split("=",1)[1]
        elif a.startswith("--animout="): _aout=a.split("=",1)[1]
        elif a.startswith("--animcat="): _acat=a.split("=",1)[1]
        elif a.startswith("--animlegs="): _alegs=a.split("=",1)[1]
        elif a.startswith("--attachbuild="): _atbuild=a.split("=",1)[1]
        elif a.startswith("--attachkey="): _atkey=a.split("=",1)[1]
        elif a.startswith("--attachout="): _atout=a.split("=",1)[1]
    if _atbuild:
        # `--attachbuild=<file.skd> --attachkey=<key> --attachout=<dir>`: resolve a model to
        # a RIGID bind-pose mesh and cache it beside the page as at<key>.js.
        #
        # An attached model is not skinned to the host skeleton - MOHAA binds the whole
        # entity to a tag and the tag's transform carries it (Entity::attachmodel, docs:
        # "attach a entity with modelname to this entity to tag called tagname"). So the
        # only thing the page needs is the model's own bind-pose geometry; the single
        # tag matrix, the scale and the offset are applied at draw time.
        #
        # Positions use the SAME resolve-then-to_yup path as write_obj(), so an attachment
        # lands in the identical coordinate frame as the host mesh and can be fed straight
        # into the existing draw code.
        if not (_atkey and _atout):
            print("! --attachbuild needs --attachkey=<key> and --attachout=<dir>"); return 1
        try:
            _ad=parse_skd(_atbuild)
        except Exception as _e:
            print(f"! attach {_atkey}: {_e}"); return 1
        _abones=_ad["bones"]
        # A TIKI model's REST pose is frame 0 of its idle animation, not an identity
        # skeleton - the .skd stores no rotation for POSROT bones, so the authored
        # orientation lives only in the .skc. Ignoring it left every attachment rotated by
        # whatever its own bind happened to be: mp44.skc poses Box01 (1206 of its 1230
        # verts) at [0.5,-0.5,-0.5,0.5] = (0,-90,90) - which is exactly the constant the
        # first attempt hard-coded as WEAPON_ATTACH_ROT, i.e. that "weapon correction" was
        # really just this one model's idle pose. airtank.skc poses Box01 differently
        # again. Reading it per model is what makes the correction stop being per model.
        _abase={}
        _aidle=None
        for _a2 in argv[1:]:
            if _a2.startswith("--attachidle="): _aidle=_a2.split("=",1)[1]
        if _aidle and os.path.isfile(_aidle):
            try:
                _ai=parse_skc(_aidle)
                if _ai["frames"]:
                    _abase=dict(_ai["frames"][0])
                    print(f"- attach bind pose: {os.path.basename(_aidle)} "
                          f"({_ai['numChan']} channels)")
            except Exception as _e:
                print(f"  (attach idle pose unusable: {_e})")
        for _b in _abones:
            _abase.setdefault(_b["name"]+" rot",[0.0,0.0,0.0,1.0])
        _awR,_awT=compute_world(_abones,_abase)
        _av=[]; _atris=[]; _auv=[]; _asr=[]; _vb=0
        _lo=[1e30,1e30,1e30]; _hi2=[-1e30,-1e30,-1e30]
        for _s in _ad["surfaces"]:
            _st=len(_atris)
            for _w in _s["verts"]:
                _p=[0.0,0.0,0.0]
                for _bi,_wt,_ofx in _w:
                    _wp=v_add(mat_vec(_awR[_bi],_ofx),_awT[_bi])
                    _p=[_p[k]+_wt*_wp[k] for k in range(3)]
                for k in range(3):
                    if _p[k]<_lo[k]: _lo[k]=_p[k]
                    if _p[k]>_hi2[k]: _hi2[k]=_p[k]
                _av.append([round(_p[0],3),round(_p[1],3),round(_p[2],3)])
            for _t in _s["tris"]:
                _atris.append([_t[0]+_vb,_t[1]+_vb,_t[2]+_vb])
            for _st2 in _s.get("uvs",[]):
                _auv.append([round(_st2[0],4),round(_st2[1],4)])
            _asr.append({"name":_s["name"],"start":_st,"end":len(_atris)})
            _vb+=len(_s["verts"])
        if not _av:
            print(f"! attach {_atkey}: {os.path.basename(_atbuild)} has no drawable geometry"); return 1
        # Same {surface_name: data-url} manifest the normal build consumes, so an attached
        # weapon is textured by exactly the shader/skin resolution that textures the host.
        _atex=None
        for _a2 in argv[1:]:
            if _a2.startswith("--textures="):
                try:
                    _atex={str(k).lower():v for k,v in
                           json.load(open(_a2.split("=",1)[1],encoding="utf-8")).items()}
                except Exception as _e:
                    print(f"  (attach texture manifest unusable: {_e})")
        if not _atex:
            print(f"- attach textures: none resolved ({len(_asr)} surface(s) draw untextured)")
        if _atex:
            for _sr in _asr:
                _du=_atex.get(_sr["name"].lower())
                # An entry is a plain data-url for a simple opaque surface, but an OBJECT
                # ({"tex":url,"additive":..,"frames":[...]}) whenever the shader carries
                # render hints - static_yellowtank has an rgbGen stage, so the airtank's
                # texture arrived as an object, was stored raw, and the page had nothing
                # usable to draw with.
                #
                # rev 63: those hints are now CARRIED rather than thrown away. "An attachment
                # is rigid and unanimated, so the base diffuse is all it needs" held for solid
                # props, but a sprite is not its diffuse: muzmodel is `map flashnode1.tga` +
                # `blendFunc GL_SRC_ALPHA GL_ONE` + `cull none`, and drawn as a plain opaque
                # one-sided quad that is a black card with a smear on it, visible from one
                # side only. The viewer's mkSurfTex already understands every one of these
                # keys - the surface just has to reach it still wearing them.
                if isinstance(_du,dict):
                    for _k in ("additive","autosprite","autosprite2","lightglow","twosided",
                               "clamp","texrotate","fps","frames","atest","distfade","pulse"):
                        _v=_du.get(_k)
                        if _v: _sr[_k]=_v
                    # `cull none` / `twosided` reaches the manifest as the raw shader keyword
                    # on some entries and as a bool on others; normalise both to the flag the
                    # page reads. A one-sided muzzle flash disappears from half the angles.
                    if str(_du.get("cull","")).lower() in ("none","disable","twosided","two-sided"):
                        _sr["twosided"]=True
                    _du=_du.get("tex") or ((_du.get("frames") or [None])[0])
                if _du and isinstance(_du,str): _sr["tex"]=_du
            _nt=sum(1 for _x in _asr if _x.get("tex"))
            _neff=sum(1 for _x in _asr if _x.get("additive") or _x.get("autosprite")
                      or _x.get("autosprite2") or _x.get("frames") or _x.get("pulse"))
            print(f"- attach textures: {_nt}/{len(_asr)} surfaces"
                  +(f" ({_neff} effect/sprite)" if _neff else ""))

        _rec={"n":os.path.splitext(os.path.basename(_atbuild))[0],
              "src":_atbuild.replace("\\","/"),
              "v":_av,"t":_atris,"uv":_auv,"sr":_asr,
              "bb":[[round(c,3) for c in _lo],[round(c,3) for c in _hi2]],
              "tags":[b["name"] for b in _abones]}
        os.makedirs(_atout,exist_ok=True)
        _jp=os.path.join(_atout,"at"+_atkey+".js")
        with open(_jp,"w",encoding="utf-8") as _f:
            _f.write("MOHAA_ATTACH("+json.dumps(_atkey)+","+json.dumps(_rec,separators=(",",":"))+");\n")
        _sz=[round(_hi2[k]-_lo[k],2) for k in range(3)]
        print(f"- attach {_rec['n']}: {len(_av)} verts, {len(_atris)} tris, "
              f"{len(_asr)} surface(s), size {_sz[0]}x{_sz[1]}x{_sz[2]} "
              f"-> {os.path.basename(_jp)} ({os.path.getsize(_jp)//1024} KB)")
        return 0

    if _abuild:
        if not (_asrc and _aout):
            print("! --animbuild needs --animsrc=<dir> and --animout=<dir>"); return 1
        names={}; _acmd={}
        if _acat:
            try:
                _cj=json.load(open(_acat,"r",encoding="utf-8",errors="replace"))
                for e in _cj.get("anims",[]):
                    names[e.get("id")]=(e.get("n"),e.get("s"))
                    # "v" is the animation's server{} frame-command block, kept verbatim by
                    # build_anim_catalog. Reading only n/s here is what threw away every
                    # frame command an on-demand animation carries.
                    if e.get("v"): _acmd[e.get("id")]=e.get("v")
            except Exception as _e: print(f"  (catalog unreadable: {_e})")
        os.makedirs(_aout,exist_ok=True)
        _hi,_lc=anim_solver_ctx(skd["bones"])
        _skel={b["name"] for b in skd["bones"]}
        # MOVEMENT SLOT: frame 0 of a full-body .skc, supplying whatever channels the action
        # animation omits (legs + "Bip01 pos"). The legs are static across the animations that
        # need filling, so one frame is enough and there is no frame-count/rate to reconcile.
        _mv=None
        if _alegs:
            try:
                _md=parse_skc(_alegs)
                _mv=_md["frames"][0] if _md["frames"] else None
                _mc=len({n.rsplit(" ",1)[0] for n in _md["names"]} & _skel)
                print(f"- movement slot: {os.path.basename(_alegs)} "
                      f"({_md['numChan']} channels, {_mc} on this skeleton)")
                if not _mc: _mv=None
            except Exception as _e:
                print(f"  (movement slot unusable: {_e})")
        _ok=0
        for _id in _abuild:
            _nm,_ref=names.get(_id,(_id,""))
            _sp=os.path.join(_asrc,_id+".skc")
            if not os.path.isfile(_sp):
                print(f"! {_nm}: .skc not found ({_ref or _id})"); continue
            try: _d=parse_skc(_sp)
            except Exception as _e:
                print(f"! {_nm}: {_e}"); continue
            _cov=len({n.rsplit(" ",1)[0] for n in _d["names"]} & _skel)
            _mn=skd.get("morphNames") or []
            # Try a facial track ALWAYS, not only when the file drives no bones. 21 of the 57
            # .skc in models/human/animation/misc carry BOTH channel sets in one file
            # (ATTACKidle01.skc = 8 bone + 35 morph), and gating this on "no bones" silently
            # dropped every one of their faces. When both are present the bone animation is
            # built as normal and the weights ride along on the same frame index - exact, no
            # resampling, because they came out of the same file.
            _mt=morph_track(_d,_mn)
            if _mt and not _cov:
                _rec={"name":_nm,"frames":[{} for _ in _mt["frames"]],"mw":_mt["frames"]}
                _fx=anim_sidecar_fx(_acmd.get(_id))
                if _fx: _rec["fx"]=_fx
                _jp=os.path.join(_aout,"a"+_id+".js")
                with open(_jp,"w",encoding="utf-8") as _f:
                    _f.write("MOHAA_ANIM("+json.dumps(_id)+","+json.dumps(_rec,separators=(",",":"))+");\n")
                print(f"- built {_nm}: {len(_mt['frames'])} frames, FACIAL MORPH track "
                      f"({_mt['matched']}/{len(_mn)} targets) -> {os.path.basename(_jp)} "
                      f"({os.path.getsize(_jp)//1024} KB)")
                if _mt["unmatched"]:
                    print(f"    ({len(_mt['unmatched'])} channel(s) have no matching morph target "
                          f"on this head: {', '.join(_mt['unmatched'][:6])}"
                          + (" ..." if len(_mt["unmatched"])>6 else "") + ")")
                _ok+=1; continue
            if not _cov:
                if _mn:
                    print(f"! {_nm}: drives none of this skeleton's {len(_skel)} bones and matches "
                          f"none of its {len(_mn)} morph targets - skipped")
                else:
                    print(f"! {_nm}: drives none of this skeleton's {len(_skel)} bones - skipped")
                continue
            _rec=solve_anim(skd["bones"],{"name":_nm,"data":_d},_hi,_lc,_mv)
            # Face layer for a BODY animation: either the same file's own morph channels, or
            # a MORPH sibling next to it. Both end up as "mw" on one record, so the viewer
            # plays body and face off a single clock the way the engine's blend slots do.
            _face=None; _fsrc=""
            if _mt:
                _face=_mt["frames"]; _fsrc="own channels"
            elif _mn:
                _pf=_apair.get(_id)
                _sib=(os.path.join(_asrc,_pf+".skc") if _pf else None) or morph_sibling_path(_sp)
                if _sib and not os.path.isfile(_sib): _sib=None
                if _sib:
                    try:
                        _st=morph_track(parse_skc(_sib),_mn)
                        if _st:
                            _face=resample_mw(_st["frames"],len(_rec["frames"]))
                            # an unaliased sibling (throwawayMORPH.skc) has no catalogue
                            # row, so there is no friendly name to print - say what it is
                            _fsrc=((names[_pf][0] if _pf in names else "paired MORPH .skc")
                                   if _pf else os.path.basename(_sib))\
                                  +(" (resampled %d->%d frames)"
                                  %(len(_st["frames"]),len(_rec["frames"]))
                                  if len(_st["frames"])!=len(_rec["frames"]) else "")
                            _mt=_st
                    except Exception as _e:
                        print(f"    (facial sibling {os.path.basename(_sib)} unusable: {_e})")
            if _face:
                _rec["mw"]=_face
                print(f"    + facial morph layer from {_fsrc} "
                      f"({_mt['matched']}/{len(_mn)} targets)")
            _fx=anim_sidecar_fx(_acmd.get(_id))
            if _fx: _rec["fx"]=_fx
            _jp=os.path.join(_aout,"a"+_id+".js")
            with open(_jp,"w",encoding="utf-8") as _f:
                _f.write("MOHAA_ANIM("+json.dumps(_id)+","+json.dumps(_rec,separators=(",",":"))+");\n")
            print(f"- built {_nm}: {len(_rec['frames'])} frames, {_cov}/{len(_skel)} bones "
                  f"-> {os.path.basename(_jp)} ({os.path.getsize(_jp)//1024} KB)")
            if _fx:
                _sn=sorted({o["name"] for o in _fx["surf"]})
                print(f"    + {len(_fx['surf'])} surface +/-nodraw command(s) over "
                      f"{len(_sn)} surface(s): {', '.join(_sn[:8])}"
                      + (" ..." if len(_sn)>8 else ""))
            _ok+=1
        print(f"Done - {_ok}/{len(_abuild)} animation(s) built")
        return 0 if _ok else 1

    # animation files (sibling .skc), minus an explicit --anim override
    explicit=None
    for a in args[1:]:
        if a.lower().endswith(".skc"): explicit=a
    # glob.escape: a model folder called "Models[1]" or "set?" is a legal directory
    # name but glob reads [ ] ? as metacharacters and silently matches nothing.
    skc_files=sorted(glob.glob(os.path.join(glob.escape(folder),"*.skc")))
    tik_files=sorted(glob.glob(os.path.join(glob.escape(folder),"*.tik")))
    print(f"- folder: {folder}")
    print(f"- found {len(skc_files)} .skc and {len(tik_files)} .tik in this folder")

    # optional shared-animation root (e.g. the models/ root) for models whose
    # animations live centrally (human characters) rather than beside the .skd
    animroot=None
    for a in argv[1:]:
        if a.startswith("--animroot="): animroot=a.split("=",1)[1]
    skel_names={b["name"] for b in skd["bones"]}
    chan_bones=lambda d:{n.rsplit(" ",1)[0] for n in d["names"]}

    # Base-pose (.skc) selection keys off the RESOLVED skelmodel name, NOT the input arg. For a
    # .tik open, args[0] (hence `stem`) is the tik (e.g. "cigarette"), but the skelmodel it loads
    # can differ (cigarette.tik -> cigaretteburn.skd). pick_base_anim gives the model's own
    # <name>.skc a +1000 bonus; keyed on the tik name it wrongly picks cigarette.skc (only 3 of the
    # 6 bones), leaving Dummy01/02/03 unposed -> collapsed to origin -> the stubby cigarette. `stem`
    # still names the OBJ/HTML output + viewer title (the launcher opens <tik-name>_view.html).
    skel_stem=os.path.splitext(os.path.basename(skd_path))[0]
    cand=[explicit] if explicit else list(skc_files)
    base_pick,all_parsed=pick_base_anim(cand, skd, skel_stem)
    def coverage(bp):
        return 0 if not bp else len(chan_bones(bp[1]) & skel_names)
    # if co-located anims don't cover the skeleton, pull a base pose from shared idle anims
    if animroot and coverage(base_pick) < max(2, len(skel_names)//2):
        shared=[]
        for sub in ("human/animation/idle","human/animation/walks_runs","human/animation/misc"):
            shared+=sorted(glob.glob(os.path.join(glob.escape(animroot),sub,"*.skc")))
        if shared:
            print(f"- skeleton not posed locally; scanning {len(shared)} shared anim(s) for a base pose")
            sbase,sparsed=pick_base_anim(shared, skd, skel_stem)
            if coverage(sbase) > coverage(base_pick):
                base_pick=sbase
                # merge: shared base becomes available, co-located anims still load
                all_parsed=(all_parsed or [])+[sbase]
    if explicit and base_pick is None:
        base_pick,all_parsed=pick_base_anim(skc_files, skd, skel_stem)

    if base_pick is None:
        print("- no .skc found; using identity rest pose")
        base_channels={}; anims_data=[]
    else:
        bf,bd=base_pick
        print(f"- bind pose from: {os.path.basename(bf)} ({bd['numChan']} channels)")
        base_channels=bd["frames"][0] if bd["frames"] else {}
        # every sibling skc that drives THIS skeleton becomes a playable animation
        anims_data=[]
        seen=set()
        for f,d in all_parsed:
            if f in seen: continue
            seen.add(f)
            if chan_bones(d) & skel_names:   # at least one channel maps to a bone here
                anims_data.append({"name":os.path.splitext(os.path.basename(f))[0],"data":d,
                                   "src":f})
            elif morph_track(d,skd.get("morphNames") or []):
                # facial (MORPH) .skc: no bone channels by design, blend-shape weights instead
                anims_data.append({"name":os.path.splitext(os.path.basename(f))[0],"data":d,
                                   "src":f,"morph":True})
        anims_data.sort(key=lambda a:a["name"])
        skipped=[os.path.basename(f) for f,d in all_parsed
                 if not (chan_bones(d) & skel_names) and not morph_track(d,skd.get("morphNames") or [])]
        if skipped: print("  (skipped .skc not matching this skeleton: "+", ".join(skipped)+")")
        _nfa=sum(1 for a in anims_data if a.get("morph"))
        if _nfa: print(f"- {_nfa} facial morph track(s) on {len(skd.get('morphNames') or [])} targets")
        print(f"- {len(anims_data)} animation(s): "+", ".join(a['name'] for a in anims_data))

    # ---- .tik animation aliases -------------------------------------------------
    # When the input is a .tik with an animations{} section, the dropdown lists the
    # tik's OWN anim names (idle / skidding / remove_surfaces / ...), each resolved
    # to its referenced .skc (basename match: in this folder first, then under the
    # shared --animroot). Aliases sharing one .skc (jeep idle+skidding) each get
    # their own entry; per-anim frame commands become the entry's "fx" (bursts fire
    # on playback, surface +/-nodraw toggles apply). Anims whose .skc isn't present
    # or doesn't drive this skeleton are listed in the log and skipped.
    animcat=None; animpre=ANIM_PRELOAD_MAX; _acp=None
    for a in argv[1:]:
        if a.startswith("--animcat="): _acp=a.split("=",1)[1]
        elif a.startswith("--animpreload="):
            try: animpre=int(a.split("=",1)[1])
            except ValueError: pass
    if _acp:
        try: animcat=json.load(open(_acp,"r",encoding="utf-8",errors="replace"))
        except Exception as e:
            print(f"  (animation catalog unreadable: {e})"); animcat=None
    _hascat=bool(animcat and animcat.get("anims"))

    animskind="skc"
    # The legacy path below reads the FIRST animations{} block of the $include-expanded
    # tik, which for a character model is whichever included file happened to land first
    # (allied_pilot.tik -> scripted/balcony.tik, eight anims) and never sees the rest.
    # When the launcher supplies a resolved catalogue it supersedes this entirely - and
    # is skipped rather than merged, so tik_anim_fx() does not append spawn emitters for
    # a mis-scoped anim list.
    # When a catalogue is supplied, none of the 2326 animations are baked into the page -
    # each one builds on first click - so the branch below never runs and the .tik's own
    # per-animation frame commands were being dropped entirely: no attachmodel, and no
    # tagspawn either (that is the cigarette smoking04/05 flick away).
    #
    # Resolve them HERE instead, at page-build time, keyed by animation name. The emitters
    # they need are appended to the page's own emitter table now, while it is still being
    # built; a sidecar loaded later merely points at them. Adding emitters at runtime would
    # mean extending six EM-parallel arrays (spawnAcc, EMSCHED, emActive, emitImg,
    # _meshImgs, and every live _triggers[].acc) in lockstep, which is not worth the risk.
    animfx_map={}
    if tikanims and _hascat:
        for _ta in tikanims:
            try: _f=tik_anim_fx(_ta,emitters)
            except Exception: _f=None
            if _f: animfx_map[_ta["name"]]=_f
        if animfx_map:
            print(f"- {len(animfx_map)} .tik animation(s) carry frame commands "
                  f"(attachmodel / tagspawn) - applied when each is built")
    if tikanims and not _hascat:
        _cache={}
        def _skc_for(fname):
            bn=os.path.basename((fname or "").replace("\\","/")).lower()
            if not bn.endswith(".skc"): return None,None
            if bn in _cache: return _cache[bn]
            hit=None
            for f in skc_files:
                if os.path.basename(f).lower()==bn: hit=f; break
            if hit is None and animroot and os.path.isdir(animroot):
                for f in glob.glob(os.path.join(glob.escape(animroot),"**","*.skc"),recursive=True):
                    if os.path.basename(f).lower()==bn: hit=f; break
            d=None
            if hit:
                try: d=parse_skc(hit)
                except Exception: d=None
            _cache[bn]=(d,hit)
            return d,hit
        _new=[]; _missing=[]
        for ta in tikanims:
            d,_dsrc=_skc_for(ta["file"])
            # A FACE alias (smoking_lightup_face -> lightupMORPH.skc) resolves fine but
            # drives no bones, so the "unresolved" test below would swap it for a 1-frame
            # stub and throw its blend-shape weights away. Recognise it first.
            _isface=bool(d is not None and not (chan_bones(d)&skel_names)
                         and morph_track(d,skd.get("morphNames") or []))
            if d is None or (not (chan_bones(d)&skel_names) and not _isface):
                # The alias's .skc is missing or doesn't drive this skeleton. The engine
                # still registers the animation (TIKI_ParseAnimations keeps every alias;
                # a bad skc only means no pose data) and, crucially, its frame COMMANDS
                # still run - for effect dummies (dummy2/dummy3.skd) the skc content is a
                # static 1-frame filler anyway. Dropping the alias here meant fx tiks whose
                # dummy skc failed to resolve lost their entire `start` anim (fx_oceanspray /
                # fx_leaves_blowing listed the sibling dummy skcs and showed no effects).
                # Substitute a 1-frame static hold at the base pose so the alias appears in
                # the dropdown and its originspawn/emitteron fx fire on playback.
                _missing.append(ta["name"])
                d={"frameTime":0.1,"frames":[{}],"numChan":0}
            # src is what lets a body alias find its MORPH sibling on disk
            _ent={"name":ta["name"],"data":d,"src":_dsrc}
            if _isface: _ent["morph"]=True
            _fx=tik_anim_fx(ta, emitters)     # appends the anim's spawn blocks onto `emitters`
            if _fx: _ent["fx"]=_fx
            _new.append(_ent)
        if _new:
            animskind="tik"
            anims_data=_new
            _nfx=sum(1 for a in _new if a.get("fx"))
            print(f"- {len(anims_data)} .tik animation(s) ({_nfx} with fx commands): "
                  +", ".join(a['name'] for a in anims_data))
            if _missing: print("  (unresolved .tik anim(s): "+", ".join(_missing)+")")
        elif tikanims:
            print("  (no .tik animations{} entry resolved to a matching .skc; keeping the sibling .skc list)")

    # ---- FULL ANIMATION CATALOG (--animcat) ---------------------------------
    # The launcher resolves the model's entire animation reach - every $include
    # chain, every per-file $path scope, every `includes <map>{}` group - and hands
    # it over as JSON (mohaa_textures.build_anim_catalog). A character model reaches
    # well over a thousand .skc that way, so the catalog only ever ships NAMES: the
    # menu lists all of them, and pose data is solved one animation at a time, on
    # click, into the cache folder beside this page. Small models (effects, vehicles,
    # weapons - anything at or under --animpreload) are still baked whole, so their
    # per-anim fx keep firing exactly as before.
    if _hascat:
        _cn=len(animcat["anims"])
        print(f"- animation catalog: {_cn} unique animation(s) across "
              f"{len(animcat.get('nodes',[]))} menu group(s) from {animcat.get('files',1)} file(s)")
        if animcat.get("missing"):
            print("  (unresolved $include: "+", ".join(animcat["missing"][:6])
                  +(" ..." if len(animcat["missing"])>6 else "")+")")
        _adir=os.path.join(folder,"_anims")
        # Bake ONLY what the primary .tik declares itself (catalogue "d" entries, already
        # deduplicated against everything its $include files provide). Those are the
        # jeep/effect-tik animations whose per-anim fx must exist at load; the rest of the
        # reach - the $path / $include tree - is menu-only and builds on click.
        _direct=[e for e in animcat["anims"] if e.get("d")]
        if len(_direct)>animpre:
            print(f"  ({len(_direct)} own animation(s) exceed the bake budget {animpre}; "
                  f"baking the first {animpre}, the rest build on click)")
            _direct=_direct[:animpre]
        if _direct:
            # small model: bake every animation into the page, fx and all
            _new=[]; _miss=0
            for _e in _direct:
                _sp=os.path.join(_adir,(_e.get("id") or "")+".skc")
                _d=None
                if os.path.isfile(_sp):
                    try: _d=parse_skc(_sp)
                    except Exception: _d=None
                if _d is None or not (chan_bones(_d)&skel_names):
                    # engine keeps the alias even when the .skc is bad or absent
                    # (TIKI_ParseAnimations, tiki_parse.cpp:451-470) and its frame
                    # commands still run - hold a 1-frame static so fx tiks keep theirs
                    if _d is None: _miss+=1
                    _d={"frameTime":0.1,"frames":[{}],"numChan":0}
                _ta={"name":_e["n"],"file":_e["s"],"flags":_e.get("f",[]),
                     "client":_parse_frame_cmds(_e.get("c") or ""),
                     "server":_parse_frame_cmds(_e.get("v") or "")}
                _ent={"name":_e["n"],"data":_d}
                _fx=tik_anim_fx(_ta, emitters)
                if _fx: _ent["fx"]=_fx
                _e["ai"]=len(_new)
                _new.append(_ent)
            anims_data=_new; animskind="tik"
            print(f"- baked {len(anims_data)} animation(s) the .tik declares itself"
                  +(f" ({_miss} with no .skc data)" if _miss else "")
                  +f"; the other {_cn-len(anims_data)} build on click")
        else:
            # every animation comes in through $include/$path (allied_pilot.tik and every
            # other character model): the page ships the menu and nothing else
            anims_data=[]; animskind="tik"
            print(f"- the .tik declares no animations of its own; all {_cn} are reached "
                  f"through $include/$path and build on first click")

    # PLAYER/HUMAN TEMPLATE (LightRay3D "Use Template > Third Person"). For a humanoid rig the
    # DISPLAYED rest pose is always the allied_pilot template, NOT whatever .skc the launcher
    # happened to pull from the shared animation root. Those shared "idle" frames (salute_idle,
    # weight_shift, ...) are posed ACTIONS: they drop the arms into salutes/slivers and drive legs
    # through IK end-effectors the FK viewer can't reproduce - the "glitchy disconnected limbs" the
    # assembled player models showed. allied_pilot.skc is a neutral A-pose with rotFK baked for
    # every IK bone -> pure FK stands the body, attaches both arms and both legs, and poses the
    # merged head/hands fingers and the weapon tags. Every matching .skc still loads into the
    # animation dropdown and plays normally; only the default "rest" frame is forced.
    # A MOHAA humanoid is identified by the 3DS-Max Biped spine - "Bip01 Spine" + "Bip01 Pelvis".
    # Those two names appear ONLY on character rigs (every Allied/German soldier, the scientist,
    # worker, and the 1st/3rd-person player models); vehicles, weapons, statics and emitters use
    # entirely different bone names, so this never touches them. The template poses whatever Bip01
    # bones a rig actually has, so it equally fixes full bodies and partial ones (e.g. an upper-body
    # player .skd with no legs still gets correct arms/spine instead of the horizontal identity rest).
    is_biped = {"Bip01 Spine","Bip01 Pelvis"} <= skel_names
    # The german_shepherd dog reuses the 3DS-Max Biped spine (Bip01 Spine/Pelvis) but is a
    # quadruped: its skeleton carries a Biped TAIL (Bip01 Tail, Bip01 Tail1/Tail2) and only stub
    # front paws (Bip01 L/R Finger0, with NO finger sub-joints) - neither of which any human/player
    # rig has. No MOHAA character has a tail, so a tailed Bip01 rig is a creature, not a person.
    # It ships its own rest pose (german_shepherd.skc, the "german_shepherd (1f)" 1-frame anim);
    # forcing the allied_pilot human template stands it upright like a person - exactly LightRay3D's
    # "Use Template" behaviour. Skip the template (and, below, the human-idle rotFK gap-fill) for
    # creatures so they keep their own pose. "Bip01 Ponytail*" is NOT matched (the space after Tail
    # excludes it): startswith("Bip01 Tail") only hits the tail chain.
    is_animal = any(b.startswith("Bip01 Tail") for b in skel_names)
    if is_biped and not is_animal:
        tcov=len({n.rsplit(" ",1)[0] for n in ALLIED_PILOT_POSE} & skel_names)
        print(f"- biped player/human rig detected; using allied_pilot template rest pose "
              f"(LightRay3D 'Use Template', {tcov}/{len(skel_names)} bones posed)")
        # LightRay3D's biped template displays the FINGERS STRAIGHT OUT (flat palm). allied_pilot.skc
        # sampled into ALLIED_PILOT_POSE is a relaxed idle whose middle/distal finger joints curl
        # ~35-56 deg, over-cupping every hand - most visible on the 1st-person arm models, where the
        # 'lefthand'/'triggerhand' read as a grasp and the over-curled fingertips fold up over the
        # palm (the stray cluster above the hand). MOHAA type-0 rotation bones carry NO base
        # orientation - skelBone_Rotation::SetBaseValue keeps only the position offset
        # (skeletor/skeletorbones.cpp:560-563), and GetDirtyTransform builds the bone from the anim
        # quat with identity at rest - so the rest finger pose is purely our display choice. Zero the
        # non-thumb finger joints to match LightRay3D; the thumb (Finger0/01/02) keeps its splay.
        # Surfaces whose grip is baked into the MESH (USarmyplyr 'garandhand') stay cupped under
        # straight bones, exactly as LightRay3D shows them. Copy the shared table before editing so
        # the module-level pose isn't mutated for later models in the same launcher run.
        base_channels=dict(ALLIED_PILOT_POSE)
        for _side in ("L","R"):
            for _fj in ("Finger1","Finger11","Finger12","Finger2","Finger21","Finger22",
                        "Finger3","Finger31","Finger32","Finger4","Finger41","Finger42"):
                base_channels[f"Bip01 {_side} {_fj} rot"]=[0.0,0.0,0.0,1.0]

    # FINAL fallback: if no local/shared animation actually poses this skeleton, a Bip01
    # human/player model would render in its horizontal identity rest pose with the IK leg/arm
    # chains splayed into elongated straight limbs. Apply the built-in canonical idle so the
    # model stands. Only when it covers MORE of this skeleton than the current pick and the
    # skeleton is genuinely under-posed - so animated models and non-Bip01 models are untouched.
    cur_cov=len({n.rsplit(" ",1)[0] for n in base_channels} & skel_names)
    def_cov=len({n.rsplit(" ",1)[0] for n in DEFAULT_BIP01_POSE} & skel_names)
    if not is_biped and cur_cov < max(2, len(skel_names)//2) and def_cov > cur_cov:
        print(f"- skeleton under-posed ({cur_cov}/{len(skel_names)} bones); applying built-in Bip01 idle base pose ({def_cov} bones covered)")
        base_channels=DEFAULT_BIP01_POSE

    # Gap-fill IK limb rotations. Many MOHAA idle/anim .skc pose the legs (and sometimes arms)
    # purely through IK end-effector channels (Bip01 * Foot pos / rot) WITHOUT baking the
    # forward-kinematic rotFK the FK viewer relies on. With no rotFK, an IK shoulder/elbow/wrist
    # bone (type 2/3/4) falls to identity and its child offset shoots off along the bind axis -
    # the leg stretches in a straight line far past the ankle. Borrow the built-in idle's
    # straight-limb rotFK for any IK bone the chosen pose doesn't already rotate, so the limb
    # stays attached. No-op when the pose already carries rotFK (own idle) or for non-Bip01 rigs.
    if is_biped and not is_animal and base_channels is not DEFAULT_BIP01_POSE and base_channels:
        bc=dict(base_channels); filled=0
        for bn in skd["bones"]:
            if bn.get("boneType") in (2,3,4):
                nm=bn["name"]
                if (nm+" rotFK") not in bc:
                    src=DEFAULT_BIP01_POSE.get(nm+" rotFK") or DEFAULT_BIP01_POSE.get(nm+" rot")
                    if src: bc[nm+" rotFK"]=src; filled+=1
        if filled:
            base_channels=bc
            print(f"- filled {filled} IK limb rotation(s) from built-in idle (pose drives them via IK targets only)")

    wR,wT=compute_world(skd["bones"],base_channels)
    referenced,convention=find_tag_bones(skd_path,[b['name'] for b in skd['bones']])
    tagset=referenced|convention
    # final classification (matches build_payload): origin / tag / bone
    tag_names=[]; n_bones=0
    for bi,bn in enumerate(skd["bones"]):
        nm=bn["name"]; nml=nm.lower(); t=wT[bi]
        at_origin=(abs(t[0])<0.5 and abs(t[1])<0.5 and abs(t[2])<0.5)
        origin=(nml.startswith("box") or nml.startswith("object") or "origin" in nml or at_origin)
        if origin or nm in tagset:
            tag_names.append(nm)
        else:
            n_bones+=1
    print(f"- tag/attach bones: {len(tag_names)} tags, {n_bones} bones")
    if tag_names: print("    tags: "+", ".join(tag_names))

    out_dir=os.path.join(folder,"")  # write next to the model
    obj_path=os.path.join(folder, stem+".obj")
    # the filename says what was opened: jeep_tik_view.html vs jeep_skd_view.html
    _vkind="tik" if args[0].lower().endswith(".tik") else "skd"
    html_path=os.path.join(folder, f"{stem}_{_vkind}_view.html")
    # --outdir=DIR: save the viewer HTML into a persistent output folder (the launcher's
    # "models" folder next to the scripts) instead of beside the (often temporary) model.
    # The HTML is fully self-contained (textures/sprites are data URLs), so it stays
    # openable after the launcher's temp extraction folder is cleaned up.
    outdir=None
    for a in argv[1:]:
        if a.startswith("--outdir="): outdir=a.split("=",1)[1]
    if outdir:
        try:
            os.makedirs(outdir,exist_ok=True)
            html_path=os.path.join(outdir, f"{stem}_{_vkind}_view.html")
            obj_path=os.path.join(outdir, stem+".obj")   # keep the .obj beside its viewer
        except OSError as e:
            print(f"  (could not use output folder {outdir}: {e}; writing next to the model)")
    # --theme=light|dark: bake the viewer's initial theme (right-click open in the launcher)
    vtheme=None
    for a in argv[1:]:
        if a.startswith("--theme="): vtheme=a.split("=",1)[1].strip().lower()
    # optional pre-resolved texture manifest {surface_name: data-url}, produced by the launcher
    textures=None
    for a in argv[1:]:
        if a.startswith("--textures="):
            try:
                textures={str(k).lower():v for k,v in json.load(open(a.split("=",1)[1],encoding="utf-8")).items()}
            except Exception as e:
                print(f"  (could not load textures manifest: {e})")
    if textures:
        n_tex=sum(1 for s in skd["surfaces"] if textures.get(s["name"].lower()))
        print(f"- textures: {n_tex}/{len(skd['surfaces'])} surfaces")
    # optional emitter sprite map {model-ref: data-url} (corona/smoke/electric .spr,
    # plus billboard textures for .tik sub-model particles), produced by the launcher
    if emitters:
        spritemap=None
        for a in argv[1:]:
            if a.startswith("--emittertex="):
                try: spritemap={str(k).lower():v for k,v in json.load(open(a.split("=",1)[1],encoding="utf-8")).items()}
                except Exception as e: print(f"  (could not load emitter sprites: {e})")
        if spritemap:
            ns=0
            for e in emitters:
                ref=(e.get("model") or "").lower()
                if ref and ref in spritemap:
                    ent=spritemap[ref]
                    # a dummy sub-.tik (snipesmoke, gas_mushroom_cloud) has no billboard of
                    # its own - its inner client fx were exported as "subfx" for one-level
                    # flattening (expand_subfx below). Don't treat that record as a sprite.
                    if isinstance(ent,dict) and ent.get("subfx"):
                        e["_subfx"]=ent["subfx"]; continue
                    e["sprite"]=ent; ns+=1
                    # carry sizing metadata onto the emitter so the viewer can size each
                    # particle correctly: mesh particles by true geometry (basesize/aspect),
                    # sprites by original texture pixels (texw/texh).
                    if isinstance(ent,dict):
                        if ent.get("basesize"): e["basesize"]=ent["basesize"]
                        if ent.get("baseaspect"): e["baseaspect"]=ent["baseaspect"]
                        if ent.get("mesh"): e["mesh"]=ent["mesh"]
                        if ent.get("texw"): e["texw"]=ent["texw"]
                        if ent.get("texh"): e["texh"]=ent["texh"]
                        if "additive" in ent: e["additive"]=ent["additive"]
                        if "rgbvertex" in ent: e["rgbvertex"]=ent["rgbvertex"]
                        if "srcalpha" in ent: e["srcalpha"]=ent["srcalpha"]
                        if ent.get("alphatest"): e["alphatest"]=ent["alphatest"]
                        if ent.get("bundle"): e["bundle"]=ent["bundle"]
                        if ent.get("erode_sprite"): e["erode_sprite"]=ent["erode_sprite"]
                        if ent.get("volumetric"): e["volumetric"]=True
                        if ent.get("spritescale"): e["spritescale"]=ent["spritescale"]
                        if ent.get("sprite_type"): e["sprite_type"]=ent["sprite_type"]
                        if ent.get("lightglow"): e["lightglow"]=True
            print(f"- emitter sprites: {ns}/{len(emitters)} emitters")
            _nsub=expand_subfx(emitters, anims_data, spritemap)
            if _nsub: print(f"- flattened {_nsub} sub-model fx block(s) from spawned dummy .tik tempmodels")
        if fxcmds:
            print(f"- fx schedule: {len(fxcmds['sched'])} timed emitter(s), re-fire {fxcmds['refire']}s / schedule {fxcmds['schedlen']}s")
        if initfx:
            print(f"- init sfx: {len(initfx['spawn'])} one-shot block(s) fire at load (Loop re-fires every {initfx['period']}s)")
    if tiknodraw:
        _pat=", ".join(dict.fromkeys(o["name"] for o in tiknodraw))
        _hid={s0["name"].lower() for s0 in skd["surfaces"]}
        _n=0
        for _o in tiknodraw:                       # engine rule: trailing '*' = case-insensitive prefix
            _nm=_o["name"].lower(); _st=_nm.endswith("*"); _b=_nm[:-1] if _st else _nm
            _hit={x for x in _hid if (x==_b or (_st and x.startswith(_b)))}
            _n=_n+len(_hit) if _o["nodraw"] else max(0,_n-len(_hit))
        if _n: print(f"- tik surface nodraw: {_pat} -> {_n} surface(s) start hidden "
                     f"(struck through in the surfaces list)")
        else:  print(f"- tik surface nodraw: {_pat} declared, but no loaded surface matches "
                     f"(that part model is not among the assembled skelmodels)")
    write_obj(obj_path, skd["bones"], skd["surfaces"], wR, wT, tagset)
    payload=build_payload(skd, anims_data, base_channels, referenced, convention, wT, textures=textures, emitters=emitters, dontdraw=dontdraw, fxcmds=fxcmds, setsize=setsize, scale=mscale, classname=mclassname, animskind=animskind, initfx=initfx, animfx=animfx_map,
                          tiknodraw=tiknodraw,
                          animcat=animcat, animdir=os.path.splitext(os.path.basename(html_path))[0])
    write_html(html_path, stem, payload, theme=vtheme)
    print(f"- wrote: {os.path.basename(obj_path)}")
    print(f"- wrote: {html_path}" if outdir else f"- wrote: {os.path.basename(html_path)}")

    if "--no-open" not in flags:
        if "--3dviewer" in flags:
            print("- opening OBJ in default 3D handler (Windows 3D Viewer)...")
            open_file(obj_path)
        else:
            print("- opening interactive viewer in browser...")
            open_file(html_path)
    return 0

if __name__=="__main__":
    sys.exit(main(sys.argv))