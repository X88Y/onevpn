import os
from PIL import Image
import shutil

def replace_images(root_dir, source_png, source_svg):
    # Supported extensions for raster images
    raster_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.ico'}
    svg_extension = '.svg'
    
    # Absolute paths to avoid replacing source files
    source_png_abs = os.path.abspath(source_png)
    source_svg_abs = os.path.abspath(source_svg)
    
    # Common directories to skip
    skip_dirs = {'.git', '.dart_tool', 'build', 'ios/Pods', 'node_modules', '.fvm'}

    print(f"Starting image replacement...")
    print(f"Source PNG: {source_png}")
    print(f"Source SVG: {source_svg}")
    print("-" * 30)

    for root, dirs, files in os.walk(root_dir):
        # Skip hidden and build directories
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
        
        for file in files:
            file_path = os.path.join(root, file)
            file_abs = os.path.abspath(file_path)
            
            # Skip the source files themselves
            if file_abs == source_png_abs or file_abs == source_svg_abs:
                continue
                
            ext = os.path.splitext(file)[1].lower()
            
            try:
                if ext in raster_extensions:
                    # Open original to get size
                    with Image.open(file_path) as target_img:
                        target_size = target_img.size
                    
                    # Resize source and save
                    with Image.open(source_png) as src_img:
                        # Use LANCZOS for high-quality downsampling
                        resized_img = src_img.resize(target_size, Image.Resampling.LANCZOS)
                        
                        # Handle color mode (e.g., if target was JPG, maybe remove alpha)
                        if ext in {'.jpg', '.jpeg'}:
                            resized_img = resized_img.convert('RGB')
                        else:
                            resized_img = resized_img.convert('RGBA')
                            
                        resized_img.save(file_path)
                        print(f"Replaced Raster: {file_path} ({target_size[0]}x{target_size[1]})")

                elif ext == svg_extension:
                    # For SVGs, we simply replace the file
                    shutil.copy2(source_svg, file_path)
                    print(f"Replaced SVG: {file_path}")
                    
            except Exception as e:
                print(f"Error processing {file_path}: {e}")

if __name__ == "__main__":
    project_root = "."
    src_png = "assets/app_icon/app_icon.png"
    src_svg = "assets/app_icon/app_icon.svg"
    
    if not os.path.exists(src_png):
        print(f"Error: Source PNG not found at {src_png}")
    elif not os.path.exists(src_svg):
        print(f"Error: Source SVG not found at {src_svg}")
    else:
        replace_images(project_root, src_png, src_svg)
        print("-" * 30)
        print("Done!")
