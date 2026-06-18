import os
from PIL import Image

def main():
    # Paths relative to the script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    images_dir = os.path.join(script_dir, "images")
    resized_dir = os.path.join(script_dir, "resized")
    
    # Target dimensions
    target_width = 1242
    target_height = 2688
    target_size = (target_width, target_height)
    
    if not os.path.exists(images_dir):
        print(f"Error: images directory not found at {images_dir}")
        return
        
    os.makedirs(resized_dir, exist_ok=True)
    
    # Process files
    files = sorted(os.listdir(images_dir))
    image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
    
    processed_count = 0
    for file in files:
        ext = os.path.splitext(file)[1].lower()
        if ext not in image_extensions:
            continue
            
        input_path = os.path.join(images_dir, file)
        output_path = os.path.join(resized_dir, file)
        
        try:
            with Image.open(input_path) as img:
                # Resize image
                resized_img = img.resize(target_size, Image.Resampling.LANCZOS)
                # Save resized image
                resized_img.save(output_path)
                print(f"Resized {file} from {img.size[0]}x{img.size[1]} to {target_width}x{target_height}")
                processed_count += 1
        except Exception as e:
            print(f"Failed to process {file}: {e}")
            
    print(f"Done! Processed {processed_count} images.")

if __name__ == "__main__":
    main()
