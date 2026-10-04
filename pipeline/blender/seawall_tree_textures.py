"""Original botanical texture atlas, drawn from equations in Blender.

No reference pixels or external assets are used. The atlas has two needle
sprays and two broadleaf sprigs. UV cells are bottom-left, bottom-right,
top-left, top-right. The PNG stores colour and coverage, not a photograph.
"""
import hashlib
import math
import random

import bpy
import numpy as np


class Canvas:
    def __init__(self, size):
        self.size = size
        self.rgba = np.zeros((size, size, 4), dtype=np.float32)
        # Green behind the transparent border avoids black texture-filter halos.
        self.rgba[:, :, :3] = (.085, .145, .045)

    def region(self, low, high):
        low = np.maximum(np.floor(low).astype(int), 0)
        high = np.minimum(np.ceil(high).astype(int) + 1, self.size)
        if np.any(high <= low):
            return None
        y, x = np.mgrid[low[1]:high[1], low[0]:high[0]]
        return self.rgba[low[1]:high[1], low[0]:high[0]], x + .5, y + .5

    @staticmethod
    def paint(region, alpha, color):
        alpha = np.clip(alpha, 0, 1).astype(np.float32)
        # Straight alpha, with over compositing for veins and overlapping leaves.
        old = region[:, :, 3]
        total = alpha + old * (1 - alpha)
        rgb = np.asarray(color) + np.zeros((*alpha.shape, 3), np.float32)
        region[:, :, :3] = (rgb * alpha[:, :, None] + region[:, :, :3] * (old * (1-alpha))[:, :, None]) / np.maximum(total[:, :, None], 1e-8)
        region[:, :, 3] = total

    def stroke(self, a, b, width, color, taper=.45):
        a, b = np.array(a) * self.size, np.array(b) * self.size
        radius = width * self.size
        data = self.region(np.minimum(a, b) - radius - 1, np.maximum(a, b) + radius + 1)
        if data is None:
            return
        region, x, y = data
        delta = b - a
        t = np.clip(((x-a[0])*delta[0] + (y-a[1])*delta[1]) / max(float(delta @ delta), 1e-8), 0, 1)
        distance = np.sqrt((x-a[0]-t*delta[0])**2 + (y-a[1]-t*delta[1])**2)
        coverage = np.clip(radius * (1 - t * taper) + .7 - distance, 0, 1)
        self.paint(region, coverage, color)

    def leaf(self, centre, length, width, angle, color, maple=False):
        centre = np.array(centre) * self.size
        length, width = length * self.size, width * self.size
        data = self.region(centre - length - 2, centre + length + 2)
        if data is None:
            return
        region, x, y = data
        dx, dy = x-centre[0], y-centre[1]
        u = (dx*math.cos(angle) + dy*math.sin(angle)) / max(width, 1)
        v = (-dx*math.sin(angle) + dy*math.cos(angle)) / max(length, 1)
        if maple:
            theta = np.arctan2(v, u)
            edge = .78 + .19 * np.cos(5*(theta-math.pi/2)) + .035*np.cos(17*theta)
            radial = np.sqrt(u*u + v*v)
            mask = (edge - radial) * min(width, length)
        else:
            edge = np.maximum(0, 1-v*v)**.62 * (1 + .035*np.sin(v*74))
            mask = np.minimum((edge-np.abs(u))*width, (1-np.abs(v))*length)
        shade = np.clip(.91 + .15*(1-u) + .055*np.cos(v*25 + u*9), .7, 1.18)
        self.paint(region, np.clip(mask+.65, 0, 1), np.asarray(color)[None, None, :] * shade[:, :, None])
        # Midrib and secondary veins stay narrow and low contrast.
        direction = np.array([-math.sin(angle), math.cos(angle)])
        sideways = np.array([math.cos(angle), math.sin(angle)])
        c = centre/self.size
        l, w = length/self.size, width/self.size
        vein = np.array(color)*1.18
        self.stroke(c-direction*l*.8, c+direction*l*.85, .0008, vein)
        for t in (-.5, -.15, .2, .5):
            for sign in (-1, 1):
                a = c + direction*l*t
                b = c + direction*l*(t+.18) + sideways*w*sign*math.sqrt(max(0, 1-t*t))*.72
                self.stroke(a, b, .00045, vein*.94)


def needle_spray(size, cedar=False):
    canvas = Canvas(size)
    rng = random.Random(851 if cedar else 712)
    # A small forked twig, not a large oval frond. At a 0.55 m card length,
    # individual needles below are about 12-24 mm long.
    shoots=[((.49,.06),(.53,.94))]
    for i,(y,reach,rise) in enumerate([(.13,.31,.22),(.23,.34,.23),(.33,.32,.24),
            (.43,.29,.23),(.53,.26,.22),(.63,.21,.21),(.73,.15,.18)]):
        for sign in (-1,1):
            shoots.append(((.50,y),(.5+sign*reach,y+rise+rng.uniform(-.025,.025))))
    for start,end in shoots:
        start,end=np.array(start),np.array(end)
        tangent=(end-start)/np.linalg.norm(end-start)
        normal=np.array([-tangent[1],tangent[0]])
        canvas.stroke(start,end,.0028,(.13,.112,.052))
        count=max(45,int(np.linalg.norm(end-start)*250))
        for needle in range(count):
            s=.045+.945*needle/count
            root=start+(end-start)*s
            color=np.array([.070,.145,.033])*rng.uniform(.74,1.42)
            for side in (-1,1):
                length=rng.uniform(.027,.048)*(1-.35*s)
                tip=root+normal*side*length+tangent*length*(.9 if cedar else .40)
                canvas.stroke(root,tip,.0034 if cedar else .0024,color,taper=.83)
                if cedar:
                    canvas.stroke(root-tangent*.004,tip-tangent*.004,.0028,color*.87,taper=.82)
    return canvas.rgba


def leaf_sprig(size, maple=False):
    canvas = Canvas(size)
    rng = random.Random(529 if maple else 329)
    canvas.stroke((.48, .06), (.53, .88), .004, (.15, .103, .049))
    positions = [(.35,.24,-.7),(.68,.29,.7),(.31,.47,-.9),(.69,.51,.7),(.34,.72,-.6),(.66,.76,.55),(.52,.88,0)]
    for i, (x, y, angle) in enumerate(positions):
        centre = np.array([x, y])
        length = (.118 if maple else .127) * rng.uniform(.92, 1.05)
        width = length * (.92 if maple else .60)
        stalk = centre - np.array([-math.sin(angle),math.cos(angle)])*length*.65
        canvas.stroke((.5, y-.10), stalk, .0018, (.17,.13,.055))
        color = np.array([.092,.171,.036] if maple else [.063,.143,.034]) * rng.uniform(.86,1.13)
        canvas.leaf(centre, length, width, angle, color, maple=maple)
    return canvas.rgba


def bark_image(size):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)/size
    warp = x + .014*np.sin(math.tau*y*3) + .009*np.sin(math.tau*(y*9+x*2))
    grain = np.sin(math.tau*warp*27) + .45*np.sin(math.tau*warp*61 + np.sin(math.tau*y*8))
    fissure = np.clip((grain-.72)*2.7, 0, 1)
    noise = (.04*np.sin(math.tau*(x*181+y*129)) + .035*np.sin(math.tau*(x*293-y*173)))
    ridges = .65 + .22*np.sin(math.tau*warp*12) - .36*fissure + noise
    rgb = np.clip(ridges[:,:,None] * np.array([.20,.15,.108]) + .022, 0, 1)
    lichen = np.clip((np.sin(math.tau*x*9)*np.sin(math.tau*y*13)-.68)*3, 0, .32)
    rgb = rgb*(1-lichen[:,:,None]) + np.array([.22,.235,.17])*lichen[:,:,None]
    return np.dstack((rgb,np.ones((size,size),np.float32)))


def write_image(directory, name, values, role):
    image = bpy.data.images.new(name, width=values.shape[1], height=values.shape[0], alpha=True)
    # Values above are linear reflectance. Keep that convention in both engines.
    image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(np.asarray(values,dtype=np.float32).ravel())
    image.file_format = "PNG"
    image.filepath_raw = str(directory/(name+".png"))
    image.save()
    image.pack()
    path = directory/(name+".png")
    return image, dict(name=name, path=path, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      width=values.shape[1],height=values.shape[0],role=role,srgb=False)


def create_textures(directory, version, atlas_size=2048, bark_size=1024):
    half = atlas_size//2
    atlas = np.zeros((atlas_size,atlas_size,4),np.float32)
    atlas[:half,:half] = needle_spray(half)
    atlas[:half,half:] = needle_spray(half,cedar=True)
    atlas[half:,:half] = leaf_sprig(half,maple=True)
    atlas[half:,half:] = leaf_sprig(half)
    atlas[atlas[:,:,3]<.001,:3]=(.09,.16,.04)
    foliage, foliage_record = write_image(directory,"T_SW_Foliage_"+version,atlas,"foliage_mask")
    bark_values = bark_image(bark_size)
    bark, bark_record = write_image(directory,"T_SW_Bark_"+version,bark_values,"bark")
    height = bark_values[:,:,:3].mean(axis=2)
    dy,dx = np.gradient(height)
    normal = np.stack((-dx*90,-dy*90,np.ones_like(dx)),axis=2)
    normal /= np.linalg.norm(normal,axis=2,keepdims=True)
    normal_values = np.dstack((normal*.5+.5,np.ones_like(dx)))
    bark_normal, normal_record = write_image(directory,"T_SW_BarkNormal_"+version,normal_values,"normal")
    return dict(foliage=foliage,bark=bark,bark_normal=bark_normal), [foliage_record,bark_record,normal_record]


def create_materials(images, version):
    materials, specs = [], {}
    for role in ("foliage", "bark"):
        image = images[role]
        name = "M_SW_"+role.title()+"_"+version
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        mat.diffuse_color = (.075,.135,.04,1) if role=="foliage" else (.17,.12,.07,1)
        tree = mat.node_tree
        shader = tree.nodes.get("Principled BSDF")
        texture = tree.nodes.new("ShaderNodeTexImage")
        texture.image = image
        tree.links.new(texture.outputs["Color"],shader.inputs["Base Color"])
        shader.inputs["Roughness"].default_value = .82 if role=="foliage" else .94
        if role=="foliage":
            tree.links.new(texture.outputs["Alpha"],shader.inputs["Alpha"])
            shader.inputs["Subsurface Weight"].default_value = .055
            mat.surface_render_method = "DITHERED"
            mat.use_backface_culling = False
        else:
            normal_texture = tree.nodes.new("ShaderNodeTexImage")
            normal_texture.image = images["bark_normal"]
            normal = tree.nodes.new("ShaderNodeNormalMap")
            normal.inputs["Strength"].default_value = .55
            tree.links.new(normal_texture.outputs["Color"],normal.inputs["Color"])
            tree.links.new(normal.outputs["Normal"],shader.inputs["Normal"])
        materials.append(mat)
        specs[name] = dict(role=role,texture=image.name,masked=role=="foliage",two_sided=role=="foliage",
                           roughness=.82 if role=="foliage" else .94,opacity_mask_clip=.32)
        if role == "bark":
            specs[name]["normal_texture"] = images["bark_normal"].name
    # Geometry convention is bark slot 0 and foliage slot 1.
    materials.sort(key=lambda mat: specs[mat.name]["role"]=="foliage")
    return materials, specs
