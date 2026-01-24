from __future__ import annotations

import logging
from typing import Optional, List, Any

from timetoalign.alignment.container import Alignment
from timetoalign.timelines.timeline import Timeline
from timetoalign.coordinates.coordinate import Coordinate

# Simple implementation for plotting
try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
except ImportError:
    plt = None

module_logger = logging.getLogger(__name__)

class SimpleVisualizer:
    """Basic visualizer using Matplotlib to plot an Alignment."""
    
    def __init__(self):
        if plt is None:
            raise ImportError("Matplotlib is not installed.")
            
    def plot_alignment(self, alignment: Alignment, title: Optional[str] = None):
        """Plots all timelines in the alignment as parallel tracks."""
        
        timelines = alignment.timelines
        n_timelines = len(timelines)
        if n_timelines == 0:
            print("No timelines to plot.")
            return
            
        fig, ax = plt.subplots(figsize=(10, 2 * n_timelines))
        if title:
            ax.set_title(title)
        else:
            ax.set_title(f"Alignment: {alignment.id}")
            
        y_positions = range(n_timelines)
        
        # Determine global x-limits (naive, assumes commensurability or just plots value)
        max_length = 0.0
        
        for i, tl in enumerate(timelines):
            y = i
            length = tl.length.to_float()
            unit = str(tl.unit)
            max_length = max(max_length, length)
            
            # Draw Timeline Axis
            ax.plot([0, length], [y, y], color='black', linewidth=2)
            ax.text(-0.5, y, f"{tl.id}\n({unit})", va='center', ha='right')
            
            # Draw Intervals
            self._plot_intervals(ax, tl, y)
            
            # Draw Instants
            self._plot_instants(ax, tl, y)
            
        # Draw Matches
        # Naive: Just draw lines between matched events? 
        # This requires knowing x-coordinates of events which might be implicit in different units.
        # For this simple visualizer, we assume raw values are comparable or just draw them raw?
        # A real plotter uses C-Maps to normalize to a display unit.
        
        ax.set_xlim(-1, max_length * 1.05)
        ax.set_yticks([])
        ax.set_xlabel("Coordinate Value (Raw)")
        
        plt.tight_layout()
        return fig
        
    def _plot_intervals(self, ax, tl: Timeline, y: float):
        if len(tl._intervals) == 0:
            return
            
        # Iterate over PyArrow table
        # Naive iteration for prototype
        df = tl._intervals.to_pandas()
        for _, row in df.iterrows():
            start = row['start']
            end = row['end']
            width = end - start
            
            # Draw rectangle
            rect = patches.Rectangle((start, y - 0.2), width, 0.4, 
                                     linewidth=1, edgecolor='blue', facecolor='lightblue', alpha=0.5)
            ax.add_patch(rect)
            
            label = row.get('label', row['category'])
            if label:
                ax.text(start + width/2, y, str(label), 
                        ha='center', va='center', fontsize=8, clip_on=True)

    def _plot_instants(self, ax, tl: Timeline, y: float):
        if len(tl._instants) == 0:
            return
            
        df = tl._instants.to_pandas()
        for _, row in df.iterrows():
            coord = row['coordinate']
            
            # Draw wedge/marker
            ax.plot(coord, y, marker='v', color='red')
            
            label = row.get('label', row['category'])
            if label:
                ax.text(coord, y + 0.25, str(label), 
                        ha='center', va='bottom', fontsize=8, rotation=45)
