"""Author: Elona Shatri"""

import glob
import os
import random
import xml.dom.minidom as minidom

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def parse_output_xml(file):
    """Parse the generated XML files to extract object information"""
    dom = minidom.parse(file)
    node_elements = dom.getElementsByTagName("Node")

    objects_info = []
    for node in node_elements:
        obj_info = {}

        # Extract all the information from each node
        obj_info["id"] = node.getElementsByTagName("Id")[0].firstChild.data
        obj_info["className"] = node.getElementsByTagName("ClassName")[
            0
        ].firstChild.data
        obj_info["top"] = int(node.getElementsByTagName("Top")[0].firstChild.data)
        obj_info["left"] = int(node.getElementsByTagName("Left")[0].firstChild.data)
        obj_info["width"] = int(node.getElementsByTagName("Width")[0].firstChild.data)
        obj_info["height"] = int(node.getElementsByTagName("Height")[0].firstChild.data)
        obj_info["mask"] = node.getElementsByTagName("Mask")[0].firstChild.data

        objects_info.append(obj_info)

    return objects_info


def decode_rle(mask_str):
    """Decode RLE mask string back to counts"""
    mask_str = mask_str.replace("0: ", "").replace("1: ", "")
    split_mask = mask_str.split(" ")
    split_mask = split_mask[:-1]  # Remove last empty element
    counts = list(map(int, split_mask))
    return counts


def draw_mask_from_rle(mask_counts, width, height):
    """Convert RLE counts back to binary mask"""
    mask = np.zeros((height, width), dtype=np.uint8)
    zero = True
    i = 0
    j = 0

    for count in mask_counts:
        if count != 0:
            for _ in range(count):
                if not zero:
                    mask[i, j] = 1

                j = j + 1
                if j == width:
                    j = 0
                    i = i + 1
        zero = not zero

    return mask


def generate_random_color():
    """Generate a random bright color for visualization"""
    colors = [
        (255, 0, 0),  # Red
        (0, 255, 0),  # Green
        (0, 0, 255),  # Blue
        (255, 255, 0),  # Yellow
        (255, 0, 255),  # Magenta
        (0, 255, 255),  # Cyan
        (255, 128, 0),  # Orange
        (128, 0, 255),  # Purple
        (255, 128, 128),  # Pink
        (128, 255, 128),  # Light Green
        (128, 128, 255),  # Light Blue
        (255, 255, 128),  # Light Yellow
    ]
    return random.choice(colors)


def visualize_masks(image_path, xml_path, output_path):
    """Create visualization with colored masks and labels"""

    # Load the original image
    if not os.path.exists(image_path):
        print(f"Image file not found: {image_path}")
        return

    if not os.path.exists(xml_path):
        print(f"XML file not found: {xml_path}")
        return

    image = Image.open(image_path).convert("RGBA")

    # Create an overlay for the masks
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # Try to load a font, fall back to default if not available
    try:
        font = ImageFont.truetype("arial.ttf", 16)
        small_font = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        try:
            font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        except Exception:
            font = None
            small_font = None

    # Parse the XML file
    objects_info = parse_output_xml(xml_path)
    print(f"Found {len(objects_info)} objects in {xml_path}")

    # Color map for consistent coloring of same class names
    class_colors = {}

    for obj in objects_info:
        # Get or assign a color for this class
        if obj["className"] not in class_colors:
            class_colors[obj["className"]] = generate_random_color()

        color = class_colors[obj["className"]]

        # Get bounding box coordinates
        left = obj["left"]
        top = obj["top"]
        # right = left + obj["width"]
        bottom = top + obj["height"]

        # Decode and draw the actual mask
        try:
            mask_counts = decode_rle(obj["mask"])
            mask_array = draw_mask_from_rle(mask_counts, obj["width"], obj["height"])

            # Create a colored version of the mask
            mask_colored = np.zeros((obj["height"], obj["width"], 4), dtype=np.uint8)
            mask_colored[:, :, 0] = color[0]  # R
            mask_colored[:, :, 1] = color[1]  # G
            mask_colored[:, :, 2] = color[2]  # B
            mask_colored[:, :, 3] = mask_array * 128  # Alpha (semi-transparent)

            # Convert to PIL and paste onto overlay
            mask_image = Image.fromarray(mask_colored, "RGBA")
            overlay.paste(mask_image, (left, top), mask_image)

        except Exception as e:
            print(f"Error processing mask for {obj['className']}: {e}")

        # Draw label
        label = f"{obj['className']}"

        # Position label above the bounding box if there's space, otherwise below
        label_y = max(0, top - 20) if top > 20 else bottom + 5

        # Draw label background for better readability
        if font:
            bbox = draw.textbbox((left, label_y), label, font=small_font)
            draw.rectangle(bbox, fill=(255, 255, 255, 200))
            draw.text((left, label_y), label, fill=(0, 0, 0, 255), font=small_font)
        else:
            draw.text((left, label_y), label, fill=color + (255,))

    # Combine original image with overlay
    result = Image.alpha_composite(image, overlay)
    result = result.convert("RGB")

    # Save the result
    result.save(output_path)
    print(f"Visualization saved to: {output_path}")

    # Print summary of found classes
    print(f"\nFound classes: {list(class_colors.keys())}")
    print(f"Total objects: {len(objects_info)}")


def main():
    # Define paths - adjust these to match your directory structure
    base_path = "/Users/elona/Desktop/for_Johannes"
    images_path = os.path.join(base_path, "Images")
    xml_path = os.path.join(base_path, "OMR_xml_by_page")
    output_path = os.path.join(base_path, "visualizations")

    # Create output directory if it doesn't exist
    os.makedirs(output_path, exist_ok=True)

    # Get all XML files
    xml_files = glob.glob(os.path.join(xml_path, "*.xml"))

    if not xml_files:
        print(f"No XML files found in {xml_path}")
        return

    print(f"Found {len(xml_files)} XML files to process")

    # Process each XML file
    for xml_file in xml_files:
        # Extract the base filename without extension
        filename = os.path.basename(xml_file)
        base_name = os.path.splitext(filename)[0]  # Remove .xml extension

        # Construct corresponding image path
        image_file = os.path.join(images_path, f"{base_name}.png")
        output_file = os.path.join(output_path, f"{base_name}_visualization.png")

        print(f"\nProcessing {filename}...")
        visualize_masks(image_file, xml_file, output_file)


if __name__ == "__main__":
    main()
