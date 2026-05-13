# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.2
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # How to Work with Graphical Timelines
#
# This notebook demonstrates how to load and work with graphical timelines
# using the `GraphicalLoader`.
#
# Graphical timelines map 2D pixel coordinates in images to 1D timeline
# coordinates. This is essential for:
# - Musical score analysis (staff systems as timelines)
# - Spectrograms (time on x-axis)
# - Graphical analytical diagrams (like Thoresen's morphological analyses)
#
# ## Key Concepts
#
# - **TimeAxisPath**: Abstract path defining how 1D timeline coordinates map to 2D pixels
# - **ImageSource**: Unified interface for images (files, PDFs)
# - **GraphicalSegment**: Source + path + timeline offset
# - **GraphicalBundle**: Collection of sources and segments
# - **GraphicalLoader**: Factory for building bundles
#

# %%
# Install dependencies if needed
# # !pip install -e ".[graphical]"

# %%
import math
from pathlib import Path

from timetoalign.loader.graphical import GraphicalLoader

# %% [markdown]
# ## Example 1: Single Image with Multiple Systems
#
# Load a musical score with multiple staff systems (horizontal lines).

# %%
# Create loader
loader = GraphicalLoader(metadata={"source": "Example Score"})

# Add the image
image_path = Path("path/to/score.png")
# idx = loader.add_image(image_path)

# For this example, we'll use mock data
# In real usage, uncomment the line above
idx = 0  # Mock source index

# Add horizontal segments for each staff system
# System 1: x from 50 to 800, y at 100
# loader.add_horizontal_segment(idx, x0=50, x1=800, y=100, name="system_1")

# System 2: x from 50 to 800, y at 250
# loader.add_horizontal_segment(idx, x0=50, x1=800, y=250, name="system_2")

# System 3: x from 50 to 800, y at 400
# loader.add_horizontal_segment(idx, x0=50, x1=800, y=400, name="system_3")

# Build the bundle
# bundle = loader.store

print("Bundle structure:")
# print(f"  Sources: {bundle.n_sources}")
# print(f"  Segments: {bundle.n_segments}")
# print(f"  Total length: {bundle.total_length} pixels")

# %% [markdown]
# ## Example 2: Coordinate Conversion
#
# Convert between 1D timeline coordinates and 2D image coordinates.

# %%
# Timeline coordinate -> Image coordinate
# coord = 400  # 400 pixels into the timeline
# source_idx, (x, y) = bundle.timeline_to_image(coord)

# print(f"Timeline coord {coord} maps to:")
# print(f"  Source image: {source_idx}")
# print(f"  Image position: ({x:.1f}, {y:.1f})")

# Image coordinate -> Timeline coordinate
# coord_back = bundle.image_to_timeline(source_idx, x, y)
# print(f"\nRound-trip: {coord_back:.1f} (should be {coord})")

# %% [markdown]
# ## Example 3: Multiple Images (Separate Pages)
#
# Load a multi-page analysis where each page is a separate image.

# %%
# Create loader for multi-page document
loader2 = GraphicalLoader(metadata={"source": "Multi-page Analysis"})

# Add images and segments
# image_paths = [
#     Path("analysis_page1.jpg"),
#     Path("analysis_page2.jpg"),
#     Path("analysis_page3.jpg"),
# ]

# Segment dimensions for each page (x0, x1, y)
# segments = [
#     (10, 850, 50),   # Page 1: 840 pixels
#     (10, 860, 50),   # Page 2: 850 pixels
#     (10, 840, 50),   # Page 3: 830 pixels
# ]

# for img_path, (x0, x1, y) in zip(image_paths, segments):
#     idx = loader2.add_image(img_path)
#     loader2.add_horizontal_segment(idx, x0=x0, x1=x1, y=y, name=f"page_{idx+1}")

# bundle2 = loader2.bundle
# print(f"Multi-page bundle: {bundle2.n_sources} sources, {bundle2.total_length:.0f} total pixels")

# %% [markdown]
# ## Example 4: Creating a Timeline
#
# Convert a GraphicalBundle into a DiscreteGraphicalTimeline.

# %%
# Create timeline from bundle
# timeline = bundle.create_timeline(uid="score_timeline", name="Example Score")

# print(f"Timeline: {timeline.id}")
# print(f"  Length: {timeline.length}")
# print(f"  Unit: {timeline.unit}")
# print(f"  Domain: {timeline.domain}")

# %% [markdown]
# ## Example 5: Visualization
#
# Draw paths and events on images.

# %%
# Draw all segment paths on the source image
# viz_img = bundle.draw_segments_on_source(source_index=0, color=(0, 255, 0), line_width=2)

# Save visualization
# viz_img.save(Path("score_with_paths.png"))

# Draw an event interval (e.g., a note or phrase)
# event_start = 100  # Timeline coordinate
# event_end = 300
# event_images = bundle.draw_interval(event_start, event_end, color=(255, 0, 0), line_width=3)

# print(f"Drew event on {len(event_images)} images")

# %% [markdown]
# ## Advanced: Custom Paths
#
# For non-horizontal timelines, use custom TimeAxisPath classes.
#

# %%
from timetoalign.loader.graphical import (  # noqa: E402
    DiagonalLinePath,
    ParametricPath,
    VerticalLinePath,
)

# Vertical timeline (top to bottom)
vertical_path = VerticalLinePath(x=400, y0=50, y1=600)
print(f"Vertical path length: {vertical_path.length} pixels")

# Diagonal timeline
diagonal_path = DiagonalLinePath(start=(100, 100), end=(700, 500))
print(f"Diagonal path length: {diagonal_path.length:.1f} pixels")

# Spiral timeline (parametric)
# r = a + b*t (Archimedean spiral)
a, b = 50, 10
spiral_path = ParametricPath(
    x_func=lambda t: 400 + (a + b * t) * math.cos(t),
    y_func=lambda t: 400 + (a + b * t) * math.sin(t),
    t_start=0,
    t_end=4 * math.pi,  # 2 full rotations
    samples=1000,
)
print(f"Spiral path length: {spiral_path.length:.1f} pixels")

# %% [markdown]
# ## Summary
#
# The graphical loader provides:
#
# 1. **Flexible path definitions** - Horizontal, vertical, diagonal, or parametric curves
# 2. **Multiple image support** - Single or multi-page analyses
# 3. **Bidirectional conversion** - Timeline ↔ Image coordinates
# 4. **Visualization** - Draw paths and events on images
# 5. **Timeline integration** - Convert bundles to DiscreteGraphicalTimeline
#
# Next: See `07_alignment.ipynb` for the Thoresen alignment example using these tools.
