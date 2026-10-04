"""Read the imported color values without changing the mesh or material."""
import json
from pathlib import Path
import unreal

ROOT=Path(__file__).resolve().parents[2]


def inspect():
    rows=[]
    for name in ['SM_Region_00_01','SM_Terrain_03_03','SM_Terrain_03_04']:
        mesh=unreal.load_asset('/Game/StanleyPark/Generated/'+name)
        if mesh is None:continue
        dynamic=unreal.DynamicMesh()
        copied,outcome=unreal.GeometryScript_AssetUtils.copy_mesh_from_static_mesh(
            mesh,dynamic,unreal.GeometryScriptCopyMeshFromAssetOptions(),unreal.GeometryScriptMeshReadLOD())
        _,colors,valid,gaps=unreal.GeometryScript_VertexColors.get_mesh_per_vertex_colors(copied)
        values=colors.convert_color_list_to_array()
        _,triangle_list,triangle_gaps=copied.get_all_triangle_indices(True)
        triangles=triangle_list.convert_triangle_list_to_array()
        used={getattr(t,k) for t in triangles for k in ['x','y','z']}
        zero_ids=[i for i,c in enumerate(values) if c.r==0 and c.g==0 and c.b==0]
        used_values=[values[i] for i in used]
        used_range={key:[function(getattr(c,k) for c in used_values) for k in ['r','g','b']]
                    for key,function in [('minimum',min),('maximum',max)]} if used_values else {}
        samples=[[float(getattr(c,k)) for k in ['r','g','b','a']] for c in values[:10]]
        ranges={key:[function(getattr(c,k) for c in values) for k in ['r','g','b']]
                for key,function in [('minimum',min),('maximum',max)]} if values else {}
        rows.append(dict(name=name,outcome=str(outcome),color_valid=valid,has_id_gaps=gaps,range=ranges,
                         referenced_range=used_range,triangles=len(triangles),used_vertices=len(used),
                         zero_color_count=len(zero_ids),referenced_zero_colors=sum(i in used for i in zero_ids),
                         color_count=len(values),first_colors=samples,material=mesh.get_material(0).get_path_name()))
    result=dict(scope='Imported source vertex colors only, not lighting acceptance',meshes=rows,
                color_api=[n for n in dir(unreal.GeometryScript_VertexColors) if 'color' in n.lower()])
    (ROOT/'evidence/unreal-vertex-color-inspection.json').write_text(json.dumps(result,indent=2))
    return result
