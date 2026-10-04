"""Separate ground output; use the same actual-terrain clipping contract."""
from build_ground_space_meshes import main

if __name__=='__main__':
    main('manifests/site-completion-sources.json','manifests/site-completion-blockouts.json',
         'data/derived/site-completions/meshes','evidence/site-completions/mesh-checks.json','SM_Site_')
