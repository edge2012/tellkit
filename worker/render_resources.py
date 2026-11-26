"""Release scene-owned raster caches without changing drawing or validation."""
import gc
import sys

# Explicit ownership list: keep fonts and scalar geometry helpers warm.
CACHES = {
    'app.action_end_state': ('_mask_component_bounds',),
    'worker.scenekit_renderer': ('sprite', '_cached_stage', '_camera_base', '_cached_solved_layout', '_cached_solved_scene'),
    'worker.scenekit_shapes': ('mask_for',),
    'worker.shape_redraw': ('paint',),
    'worker.visual': ('_text_bitmap', 'sticker', '_legacy_relation_sticker', 'relation_sticker', 'item_sticker', 'abstract_frames'),
    'worker.overlays': ('_sticker_layer', '_leader_layer'),
    'worker.depth': ('_static_backdrop',),
    'worker.lighting_declaration': ('_static_transform', '_cached', '_unlit'),
    'worker.material_pixels': ('_measure_pixels',),
    'worker.scene_composition': ('_material_rgb',),
    'worker.depth_measure': ('_contour_pixels',),
}


def release_scene():
    for name, functions in CACHES.items():
        module = sys.modules.get(name)
        if module is None:
            continue
        for name in functions:
            clear = getattr(getattr(module, name, None), 'cache_clear', None)
            if clear is not None:
                clear()
    gc.collect()
