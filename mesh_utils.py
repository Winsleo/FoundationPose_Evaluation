from typing import Union, Optional
import os
import argparse
import pymeshlab as ml
import trimesh
import scipy
import numpy as np


def compute_mesh_diameter(model_pts=None, mesh=None, n_sample=1000):
    # from sklearn.decomposition import TruncatedSVD

    if mesh is not None:
        u, s, vh = scipy.linalg.svd(mesh.vertices, full_matrices=False)
        pts = u @ s
        diameter = np.linalg.norm(pts.max(axis=0) - pts.min(axis=0))
        return float(diameter)

    if n_sample is None:
        pts = model_pts
    else:
        ids = np.random.choice(
            len(model_pts), size=min(n_sample, len(model_pts)), replace=False
        )
        pts = model_pts[ids]
    dists = np.linalg.norm(pts[None] - pts[:, None], axis=-1)
    diameter = dists.max()
    return diameter


def simplify_textured_mesh(
    input_path: str,
    output_path: str,
    target_faces: Optional[int] = None,
    reduction_ratio: Optional[float] = None,
    texture_weight: float = 1.5,
    preserve_boundary: bool = True,
    boundary_weight: float = 1.0,
    quality_threshold: float = 0.3,
    planar: bool = False,
    optimal_placement: bool = True,
    verbose: bool = True
):
    """
    Simplify a textured 3D mesh while keeping texture seams aligned.

    Args:
        input_path (str): Input mesh path (textured formats such as .obj/.ply supported).
        output_path (str): Output mesh path.
        target_faces (int, optional): Target number of faces (mutually exclusive with reduction_ratio).
        reduction_ratio (float, optional): Target reduction ratio in [0.0, 1.0). The resulting face count
            is roughly (1 - reduction_ratio) of the original.
        texture_weight (float): Weight for UV coordinates. Higher values prioritize preserving texture
            continuity along seams.
            Tuning guide:
                Texture stretching: increase to 1.5–2.0
                Too much geometric detail loss: decrease to 0.5–1.0
        boundary_weight (float): Boundary preservation weight (0.0–inf). Larger values keep boundary edges
            more intact during decimation.
            Tuning guide:
                Default 1.0: boundaries are treated similar to interior edges
                Must-protect silhouettes (e.g., building outlines): set to 3.0–5.0
                Too high: may cause over-simplification elsewhere
        optimal_placement (bool): Compute optimal vertex placement when collapsing edges to minimize error.
            Tuning guide:
                True (default): smoother geometry overall
                If you observe spikes on flat regions: set to False (may degrade quality)
        verbose (bool): Print processing logs.
    """
    try:
        # Argument validation
        if target_faces is None and reduction_ratio is None:
            raise ValueError("You must specify either target_faces or reduction_ratio")
        
        if target_faces is not None and reduction_ratio is not None:
            raise ValueError("target_faces and reduction_ratio are mutually exclusive")
            
        if reduction_ratio is not None and not (0 <= reduction_ratio < 1):
            raise ValueError("reduction_ratio must be within [0, 1)")
            
        # Check input file existence
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file {input_path} not found")
        
        # Initialize MeshLab
        ms = ml.MeshSet()
        if verbose:
            print(f"🟢 Loading mesh: {os.path.basename(input_path)}")
        
        # Load mesh (textures will be loaded automatically if available)
        ms.load_new_mesh(input_path)
        input_mesh = ms.current_mesh()
        input_faces = input_mesh.face_number()

        # Compute target face count
        if reduction_ratio is not None:
            calculated_target_faces = int(input_faces * (1 - reduction_ratio))
            # Keep at least a few faces
            target_faces = max(calculated_target_faces, 4)
            if verbose:
                print(f"📊 Target faces from reduction ratio {reduction_ratio:.1%}: {target_faces}")
        
        # Run texture-aware quadric decimation
        if verbose:
            print(f"🔧 Start decimation (target_faces={target_faces}, texture_weight={texture_weight})")
        
        ms.meshing_decimation_quadric_edge_collapse_with_texture(
            targetfacenum=target_faces,
            qualitythr=quality_threshold,
            extratcoordw=texture_weight,
            preserveboundary=preserve_boundary,
            boundaryweight=boundary_weight,
            optimalplacement=optimal_placement,
            planarquadric=planar,
            preservenormal=True,
        )
        
        # Get statistics after decimation
        output_mesh = ms.current_mesh()
        output_faces = output_mesh.face_number()
        reduction_ratio = 1 - (output_faces / input_faces)
        
        # Save result (textures preserved automatically)
        if verbose:
            print(f"💾 Saving to: {output_path}")
        ms.save_current_mesh(output_path, save_textures=True)
        
        if verbose:
            print(f"✅ Done! Faces: {input_faces:,} → {output_faces:,} (reduced {reduction_ratio:.1%})")
    except Exception as e:
        if verbose:
            print(f"❌ Failed: {str(e)}")


def display_mesh(mesh: Union[str, trimesh.Trimesh], show_bbox: bool = True):
    """
    Visualize a 3D mesh.

    Args:
        mesh (str or trimesh.Trimesh): File path or a trimesh object.
        show_bbox (bool): Whether to draw the oriented bounding box wireframe.
    """
    if isinstance(mesh, str):
        mesh = trimesh.load(mesh)
    # Create a visualization scene
    scene = trimesh.Scene()
    scene.add_geometry(mesh)
    # Add a small axis helper
    scene.add_geometry(trimesh.creation.axis(origin_size=0.005, axis_length=0.1, axis_radius=0.005))
    if show_bbox:
        # Add OBB wireframe (red color)
        obb = mesh.bounding_box
        obb.visual.face_colors = [255, 0, 0, 50]
        scene.add_geometry(obb)
    # Show the scene
    scene.show()


def dowsample_mesh(args):
    if not args.target_faces and not args.reduction_ratio:
        parser.error("You must specify either --target-faces or --reduction-ratio")

    try:
        simplify_textured_mesh(args.input, args.output, 
                               target_faces=args.target_faces, 
                               reduction_ratio=args.reduction_ratio,
                               verbose=True)
        # Display simplified mesh
        display_mesh(args.output)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


def resize_mesh(args):
    """
    Resize a mesh to a specific scale.
    """
    mesh = trimesh.load(args.input)
    obb = mesh.bounding_box
    model_size = obb.primitive.extents.min()
    print("original info:")
    print(f"  vertices: {len(mesh.vertices)}")
    print(f"  faces: {len(mesh.faces)}")
    print(f"  extents: {obb.primitive.extents}")
    scale = (args.size / model_size) if args.size else 1.0
    mesh.apply_scale(scale)
    print("resized mesh info:")
    print(f"  vertices: {len(mesh.vertices)}")
    print(f"  faces: {len(mesh.faces)}")
    print(f"  extents: {mesh.bounding_box.primitive.extents}")
    display_mesh(mesh)
    mesh.export(args.output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Simplify textured 3D mesh or resize to real scale')
    parser.add_argument("--input", '-i', type=str, required=True, help="Input mesh file path")
    parser.add_argument("--output", '-o', type=str, required=True, help="Output mesh file path")
    parser.add_argument('--downsample', '-d', action='store_true', help='Enable mesh decimation (texture-aware)')
    parser.add_argument('--size', type=float, help='Real-world size along the smallest OBB extent (meters)')
    parser.add_argument('--target-faces', type=int, help='Target number of faces for decimation')
    parser.add_argument('--reduction-ratio', type=float, help='Decimation ratio in [0,1); 0.8 → keep ~20% faces')

    args = parser.parse_args()
    if args.downsample:
        dowsample_mesh(args)
    else:
        resize_mesh(args)
