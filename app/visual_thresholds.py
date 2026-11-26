"""Fixed numeric limits and diagnostic identifiers for rendering."""

# Maximum subject bounding-box fraction of canvas area.
AREA = 0.35

# Maximum celestial object height relative to canvas height.
CELESTIAL_HEIGHT = 0.22

# Minimum subject height relative to canvas height.
MIN_HEIGHT = 0.18

# Character height range relative to canvas height.
CHARACTER = (0.22, 0.3)

# Minimum gap between adjacent subject bounding boxes, in pixels.
GAP = 24.0

# Maximum backdrop scale relative to the midground subject.
BACKDROP = 0.7

# Maximum identical subjects per scene, excluding rain segments.
DUPLICATES = 1

# Excluded band on either side of the canvas center, in pixels.
CENTER_BAND = 8.0

# Scale multiplier for each additional depth layer.
DEPTH = 0.75

# Minimum luminance increase on a lit surface.
LUMA = 12.0

# Highlight width range relative to object width.
HIGHLIGHT_WIDTH = (0.12, 0.18)

# Highlight opacity range.
HIGHLIGHT_ALPHA = (0.35, 0.55)

# Shadow-side opacity range.
SHADE_ALPHA = (0.12, 0.2)

# Maximum number of water color bands.
WATER_BANDS = 2

# Maximum relative deviation from the depth scale multiplier.
DEPTH_TOLERANCE = 0.15

# Maximum lines per subtitle page.
MAX_LINES = 2

# Minimum delivery duration in seconds.
MIN_SECONDS = 15.0

# Maximum delivery duration in seconds.
MAX_SECONDS = 45.0

# Maximum encoded bytes per aspect.
MAX_BYTES = 1500000.0

# Minimum sentence pause in milliseconds.
PAUSE_MS = 350.0

# Subtitle safe margin relative to the shorter canvas edge.
SAFE = 0.04

# Diagnostic identifiers recognized by render error reporting.
CODES = {
    'ACTION_TARGET_SELF',
    'ARROW_DIRECTION',
    'ARROW_LENGTH',
    'ARROW_ORPHAN',
    'BACKDROP_SCALE',
    'CARD_AS_SUBJECT',
    'CHARACTER_SCALE',
    'COMPARISON_MISSING_PEER',
    'CONTAINER_OUT_OF_BOUNDS',
    'CONTAINER_OVERLAP',
    'DEPTH_SCALE',
    'DURATION_ABOVE_CEILING',
    'DURATION_BELOW_FLOOR',
    'FLOATING_SUBJECT',
    'GRADIENT_BANNED',
    'HIGHLIGHT_DECLARATION_MISMATCH',
    'HIGHLIGHT_GRAMMAR',
    'HORIZON_MISSING',
    'LABEL_FONT_MIXED',
    'LABEL_ORPHAN',
    'LABEL_OVERLAP',
    'LABEL_TOO_MANY',
    'LIGHT_CAUSALITY_MISSING',
    'LIGHT_DIRECTION',
    'PAUSE_TOO_SHORT',
    'REPEAT_SCENE_ADJACENT',
    'REPEAT_SCENE_MONOTONE',
    'SHAPE_UNRECOGNIZABLE',
    'SILHOUETTE_DETAIL',
    'SIZE_EXCEEDS_LIMIT',
    'SPHERE_SHADING',
    'STATE_REPEAT_IN_SCENE',
    'STATIC_IMAGE_MULTI_NARRATION',
    'SUBJECT_CLIPPED',
    'SUBJECT_DUPLICATE',
    'SUBJECT_SPACING',
    'SUBJECT_STATIC',
    'SUBJECT_SYMMETRY',
    'SUBJECT_TOO_LARGE',
    'SUBJECT_TOO_SMALL',
    'SUBJECT_UNDECLARED_MOTION',
    'SUBQUESTION_COVERAGE',
    'SUBQUESTION_SPLIT',
    'SUBTITLE_BREAK_WORD',
    'SUBTITLE_BROKEN',
    'SUBTITLE_OUT_OF_SAFE',
    'SUBTITLE_PUNCT_EDGE',
    'SUBTITLE_RATIO',
    'SUBTITLE_TOO_MANY_LINES',
    'TEXTURE_BANNED',
    'TRANSITION_HANDOFF',
    'UI_LEFTOVER',
    'UNKNOWN_SHAPE',
    'WHITE_RING_IN_VIDEO',
    'character_present',
    'rules_fingerprint',
    'same_frame_compare',
}

from app.layout_validation import CODES as LAYOUT_CODES
CODES.update(LAYOUT_CODES)
