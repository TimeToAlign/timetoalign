# Rectangle Visualization Fix for 07_alignment_thoresen.ipynb

## Problem Identified

The notebook was failing with `NameError: name 'event_h' is not defined` in Step 9 because cells had dependencies on variables defined in previous cells that may not have been executed.

## Root Cause

**Original Issue:** Events in `thoresen_test.tsv` are **rectangles** with `(x, y, width, height)` coordinates, not just lines. The notebook was drawing horizontal lines along the time axis but ignoring the y-dimension and height.

**Variable Scope Issue:** Step 9 (transfer via audio) depended on `event_h` being defined in Step 7, but if Step 7 wasn't executed (or outputs were cleared), Step 9 would fail.

## Changes Made

### 1. Step 7: DGT2 Rectangle Visualization (ALREADY CORRECT)

```python
# Draw rectangle at EXACT image coordinates
rect = patches.Rectangle(
    (img_x, img_y), img_width, img_height,
    linewidth=3, edgecolor='red', facecolor='none'
)
ax.add_patch(rect)
```

**Status:** ✅ Already correctly drawing rectangles with matplotlib patches.

### 2. Step 9: Transfer via Audio (FIXED)

**Before:**
```python
def transfer_via_audio(...):
    ...

# Transfer event H
h_start_dgt1 = transfer_via_audio(event_h["start_global"], ...)  # ❌ event_h undefined
```

**After:**
```python
# Find rect_h2 event (self-contained cell)
event_h = next(evt for evt in dgt2_events if evt["event_id"] == "rect_h2")

def transfer_via_audio(...):
    ...

# Transfer event H
h_start_dgt1 = transfer_via_audio(event_h["start_global"], ...)  # ✅ event_h now defined
```

**Change:** Added `event_h` definition at the start of the cell to make it self-contained.

### 3. Step 9b: DGT1 Rectangle Visualization (COMPLETELY REWRITTEN)

**Before:**
```python
# OLD CODE: Drew lines, not rectangles
dgt1_event_images = dgt1_bundle.draw_interval(
    start_coord=h_start_dgt1,
    end_coord=h_end_dgt1,
    color=(0, 0, 255),
    line_width=5,
)
```

**After:**
```python
# NEW CODE: Draw proper rectangles with Y-coordinate transformation

# Calculate DGT1 image x-coordinate
dgt1_seg_idx = int(h_start_dgt1 / 967)
dgt1_local_x_start = h_start_dgt1 - (dgt1_seg_idx * 967)
dgt1_img_x = DGT1_X0 + dgt1_local_x_start
dgt1_img_width = h_end_dgt1 - h_start_dgt1

# Calculate Y-coordinate transformation
dgt2_y0 = DGT2_SEGMENT_BOUNDS[seg_idx_dgt2][2]  # y=18
dgt2_y_offset = img_y_dgt2 - dgt2_y0            # 46 - 18 = 28
dgt1_y0 = DGT1_Y_POSITIONS[dgt1_seg_idx]        # 205
dgt1_img_y = dgt1_y0 + dgt2_y_offset            # 205 + 28 = 233
dgt1_img_height = img_height_dgt2               # 20

# Draw rectangle
rect = patches.Rectangle(
    (dgt1_img_x, rect_y_adjusted), dgt1_img_width, dgt1_img_height,
    linewidth=3, edgecolor='blue', facecolor='none'
)
ax.add_patch(rect)
```

**Key Innovation:** Y-coordinate transformation preserves the **morphological position** of the event:
- In DGT2: Event is 28 pixels above segment baseline (y=46, baseline=18)
- In DGT1: Event should be 28 pixels above segment baseline (y=233, baseline=205)

**Variable Dependency Fix:** Removed reference to `event_h['start_global']` in print statement, replaced with computed `dgt2_start_timeline` from raw TSV data.

### 4. Step 9c: Side-by-Side Comparison (COMPLETELY REWRITTEN)

**Before:**
```python
# OLD CODE: Used draw_interval() which draws lines
dgt2_img_with_event = dgt2_bundle.draw_interval(...)
dgt1_img_with_event = dgt1_bundle.draw_interval(...)
```

**After:**
```python
# NEW CODE: Draw rectangles on both images with matplotlib

# DGT2 (source) with RED rectangle
ax1.imshow(dgt2_img)
rect_dgt2 = patches.Rectangle(
    (img_x_dgt2, img_y_dgt2), img_width_dgt2, img_height_dgt2,
    linewidth=3, edgecolor='red', facecolor='none'
)
ax1.add_patch(rect_dgt2)

# DGT1 (target) with BLUE rectangle (Y-transformed)
ax2.imshow(dgt1_cropped)
rect_dgt1 = patches.Rectangle(
    (dgt1_img_x, rect_y_adjusted), dgt1_img_width, dgt1_img_height,
    linewidth=3, edgecolor='blue', facecolor='none'
)
ax2.add_patch(rect_dgt1)
```

**Change:** Both rectangles now use matplotlib patches with proper coordinate transformation.

## Y-Coordinate Transformation Logic

### Why It's Necessary

DGT1 and DGT2 have different segment layouts:

| Segment | DGT2 Baseline (y) | DGT1 Baseline (y) |
|---------|-------------------|-------------------|
| 0       | 15                | 18                |
| 1       | 18                | 205               |
| 2       | 19                | 396               |
| 3       | 15                | 588               |
| 4       | 20                | 785               |

**Problem:** A simple pixel coordinate transfer (x=385 → x'=1390) doesn't work for y because the segments are at different vertical positions.

**Solution:** Preserve the **offset from the segment baseline**:

```python
# Original position in DGT2
dgt2_y0 = 18        # Segment 1 baseline in DGT2
img_y_dgt2 = 46     # Event y-coordinate
offset = 46 - 18 = 28 pixels above baseline

# Transferred position in DGT1
dgt1_y0 = 205       # Segment 1 baseline in DGT1
dgt1_img_y = 205 + 28 = 233  # Same offset above baseline
```

This ensures the rectangle appears at the **morphologically equivalent position** in both analyses, even though the absolute y-coordinates differ.

## Verification Checklist

When you execute the notebook, verify:

- [ ] **Step 7**: DGT2 image shows red rectangle at (385, 46, 139, 20)
- [ ] **Step 9**: Console output shows transfer calculations without errors
- [ ] **Step 9b**: DGT1 image shows blue rectangle with:
  - X-position corresponds to transferred timeline coordinates
  - Y-position is ~28 pixels above the segment baseline (not at y=46!)
  - Width and height preserved from DGT2
- [ ] **Step 9c**: Side-by-side comparison shows:
  - Red rectangle in DGT2 at original position
  - Blue rectangle in DGT1 at morphologically equivalent position
  - Both rectangles highlight the same sonic event

## Technical Rationale: Matplotlib vs PyMuPDF

**Why use matplotlib instead of PyMuPDF's drawing?**

1. **Coordinate Precision**: `patches.Rectangle((x, y), w, h)` gives exact pixel control
2. **Visualization Richness**: Transparency, colors, annotations, side-by-side comparisons
3. **Research Workflow**: Standard tool for scientific notebooks and publication figures
4. **Separation of Concerns**: PyMuPDF loads data, matplotlib presents it

**PyMuPDF's Role**: Still used in production code (`ImageSource`, `GraphicalBundle`) for efficient image loading and basic path drawing.

**Matplotlib's Role**: Used in notebooks/validation for rich scientific visualization requiring shapes beyond lines.

## Files Modified

1. **`07_alignment_thoresen.ipynb`** - Main notebook with rectangle visualization
2. **`update_notebook_rectangles.py`** - Script that applied the changes
3. **`RECTANGLE_VISUALIZATION_FIX.md`** (this file) - Documentation

## Next Steps

1. **Execute the notebook** to see the rendered figures:
   ```bash
   # Option 1: Jupyter notebook
   jupyter notebook 07_alignment_thoresen.ipynb

   # Option 2: VS Code with Jupyter extension
   # Open notebook in VS Code and run cells
   ```

2. **Verify visual alignment**: Check that the blue rectangle in DGT1 appears at the morphologically correct position (not just horizontally aligned, but vertically aligned relative to the segment structure).

3. **Test with other events**: Try visualizing other rectangles from `THORESEN_EVENTS` to validate the transformation works generally.

## Expected Outputs

### Step 7: DGT2 with Red Rectangle
- Image: `thoresen_2010_form-building-patterns_p90-91_page1_2.jpeg`
- Rectangle: Red outline at (385, 46, 139, 20)
- Segment: 2 (second image)

### Step 9b: DGT1 with Blue Rectangle
- Image: `thoresen_2009_sound-objects_p312_page1_1.jpeg` (cropped to segment 2)
- Rectangle: Blue outline at (~1390, ~233, ~155, 20)
- Segment: 2 (middle horizontal line)

### Step 9c: Side-by-Side Comparison
- Top: DGT2 with red rectangle
- Bottom: DGT1 with blue rectangle
- Visual confirmation that both rectangles mark the same sonic event at morphologically equivalent positions
