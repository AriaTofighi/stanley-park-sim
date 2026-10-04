"""Small, original M1 navigation shapes. No application or asset dependencies."""
import numpy as np


def box(center, axes, size):
    center, axes, size = np.asarray(center), np.asarray(axes), np.asarray(size)
    signs = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]])
    vertices = center + (signs * size * .5) @ axes
    faces = np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
                      [1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]], dtype=np.int32)
    if np.linalg.det(axes) < 0:
        faces = faces[:, ::-1]
    return vertices, faces


def merge(parts):
    vertices, faces, count = [], [], 0
    for v, f in parts:
        vertices.append(v); faces.append(f + count); count += len(v)
    return np.vstack(vertices), np.vstack(faces)


def mesh_check(vertices, faces, closed):
    triangles = vertices[faces]
    normal = np.cross(triangles[:,1]-triangles[:,0], triangles[:,2]-triangles[:,0])
    edges = np.sort(np.concatenate((faces[:,:2], faces[:,1:], faces[:,[2,0]])), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    result = {"finite": bool(np.isfinite(vertices).all()), "minimum_area_m2": float(np.linalg.norm(normal,axis=1).min()*.5),
              "boundary_edges": int((counts==1).sum()), "nonmanifold_edges": int((counts>2).sum())}
    if closed:
        tri = triangles - vertices.mean(axis=0)
        result['signed_volume_m3'] = float(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()/6)
    if not result['finite'] or result['minimum_area_m2'] < 1e-10 or result['nonmanifold_edges'] or (closed and (result['boundary_edges'] or result['signed_volume_m3']<=0)):
        raise ValueError(result)
    return result
