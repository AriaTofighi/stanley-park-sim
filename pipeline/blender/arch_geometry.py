"""Make the review arch as a closed solid, without internal wedge faces."""
import math
import bpy
import bmesh
import numpy as np


def outward_normals(mesh):
    bm=bmesh.new();bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(mesh);bm.free();mesh.update()


def cut_arches(obj, collection, anchor, world, bottom, opening_half=1.1):
    """Cut both crossing openings. Their dimensions are still review values."""
    material=obj.data.materials[0]
    outward_normals(obj.data)
    for swap in [False,True]:
        profile=[[-opening_half,bottom-1],[opening_half,bottom-1]]
        profile.extend([[opening_half*math.cos(t),5.25+1.85*math.sin(t)] for t in np.linspace(0,math.pi,25)])
        n=len(profile);verts=[]
        for depth in [-10,10]:
            for span,z in profile:
                verts.append(world([depth,span,z] if swap else [span,depth,z]))
        faces=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]
        faces.extend([(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)])
        mesh=bpy.data.meshes.new('SP_ArchCutterTemporary')
        mesh.from_pydata((np.asarray(verts)-anchor).tolist(),[],faces);outward_normals(mesh)
        mesh.materials.append(material)
        cutter=bpy.data.objects.new('SP_ArchCutterTemporary',mesh)
        collection.objects.link(cutter);cutter.location=anchor
        modifier=obj.modifiers.new('ReviewArchOpening','BOOLEAN')
        modifier.operation='DIFFERENCE';modifier.solver='EXACT';modifier.object=cutter
        bpy.context.view_layer.objects.active=obj
        bpy.ops.object.select_all(action='DESELECT');obj.select_set(True)
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        bpy.data.objects.remove(cutter,do_unlink=True);bpy.data.meshes.remove(mesh)
    outward_normals(obj.data)
    obj.data.materials.clear();obj.data.materials.append(material)
    for face in obj.data.polygons:face.material_index=0
    bm=bmesh.new();bm.from_mesh(obj.data)
    nonmanifold=sum(not edge.is_manifold for edge in bm.edges);bm.free()
    if nonmanifold:raise RuntimeError(f'Arch has {nonmanifold} non-manifold edges')
    obj['arch_topology_check']='Closed manifold; no internal wedge faces'
