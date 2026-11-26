# Delivery inventory

## Round 9 boundary audit

The static import closure starts at `demo/run.py`, follows `import` and `from` statements (including function-local and conditional imports), and resolves package module imports such as `from worker import scenekit_v9`. It covers all 86 remaining Python modules, including the two demo entry/adaptation modules. There are no unreachable package modules. This is import reachability, not a claim that the fixed board exercises every drawing branch. `demo/offline.py` installs the existing in-memory `app.storyboard` and `app.enforcement` adapters before renderer imports.

Removed files:

- `app/video-visual-spec-v1.md` and `app/w27a-requirements.md`: author specifications are no longer runtime data. Every numeric value needed by the retained checks is a named constant with an English explanation in `app/visual_thresholds.py`; no external specification override remains.
- `worker/character.py`: unreachable standalone character painter; the reachable scene shape renderer retains its own character drawing support.
- `worker/render_supervision.py`: unreachable service process supervisor.
- `app/scene_variety.py`: no remaining callers after removing unused author narrative/layout gates.
- All generated `out/*` artifacts except `out/episode.mp4`: local render evidence is ignored, not delivered.

Retained alternatives:

- `worker/scenekit_v9.py` is directly imported as `sk` by `worker/scenekit_renderer.py` and by shape drawers.
- `worker/scenekit_v8.py` supplies legacy geometry used by v9. Neither module is unreachable; deleting them would remove rendering functionality.

Symbol changes:

- `app/logic_w24.py` retains only the imports, `Sample`, `Handoff` and `arrow_geometry` required by rendering. Author prompts, rule names, state/identity helpers, teaching/boundary helpers, violations and generation contracts are removed.
- Removed unused author prompts in action and expression contracts, the expression author rewrite loop and its exclusive helpers/schema, unused narrative and storyboard review branches, and performance author gates. Runtime action validation, geometry fallback, frame diagnostics, subtitle checks and delivery checks remain.
- Action capability errors now describe the structured `SUPPORTED` capabilities instead of embedding author instructions.
- Actual geometry/pixel functions named `violations` remain. The requested text blacklist also matches `episode_violations(...)` inside the immutable `worker/render.py`; this is a rendering check, not an author prompt. Renaming or removing that call would violate the renderer checksum constraint.

## Inlined values and provenance

| Constants | Values | Former source |
| --- | --- | --- |
| `AREA`, `CELESTIAL_HEIGHT`, `MIN_HEIGHT`, `CHARACTER` | `0.35`, `0.22`, `0.18`, `(0.22, 0.30)` | Visual specification R1–R4 |
| `GAP`, `BACKDROP`, `DUPLICATES`, `CENTER_BAND` | `24.0`, `0.7`, `1`, `8.0` | R5–R8 |
| `DEPTH`, `DEPTH_TOLERANCE` | `0.75`, `0.15` | R10; supplemental requirement “偏差 >15%” |
| `LUMA`, `HIGHLIGHT_WIDTH`, `HIGHLIGHT_ALPHA`, `SHADE_ALPHA`, `WATER_BANDS` | `12.0`, `(0.12, 0.18)`, `(0.35, 0.55)`, `(0.12, 0.20)`, `2` | R13, R15, R16, R19 |
| `MAX_LINES`, `SAFE` | `2`, `0.04` | R39; canvas safe-margin table |
| `MIN_SECONDS`, `MAX_SECONDS`, `MAX_BYTES`, `PAUSE_MS` | `15.0`, `45.0`, `1500000.0`, `350.0` | R43–R45 |

Diagnostic code sets formerly extracted from Appendix A are explicit code constants. Layout codes still come from `app/layout_validation.py`. Unused narrative thresholds R30/R34/R46 were deleted with their author checks. No numeric value requires a Markdown fallback. Subtitle diagnostic descriptions are now English strings rather than specification excerpts.

## Python import inventory

Equality below compares round 9 to the supplied delivery tree, not to an unverified production revision. `worker/render.py` remains SHA-256 `e25ff14d3a721fb11b8d22b51294f122e1e9c7b25a12cd6a3f5e4e89cfce68df`.

| File | Importing callers | Round 9 bytes |
| --- | --- | --- |
| `app/action_contract.py` | `worker.scenekit_renderer`, `app.sentence_beats`, `app.action_end_state` | boundary adaptation |
| `app/action_end_state.py` | `worker.scenekit_renderer`, `worker.render_actions`, `app.action_geometry`, `app.action_start_state`, `app.layout_validation` | unchanged |
| `app/action_geometry.py` | `worker.scenekit_renderer`, `worker.render_actions`, `worker.render`, `app.action_start_state` | unchanged |
| `app/action_start_state.py` | `worker.render_actions` | unchanged |
| `app/action_vocabulary.py` | `worker.render_actions`, `app.sentence_beats`, `app.action_geometry`, `app.action_contract` | boundary adaptation |
| `app/aspects.py` | `worker.scenekit_renderer`, `worker.render`, `app.geometry_healing`, `app.visual_validation`, `app.visual_spec_w27c` | unchanged |
| `app/canvas_bounds.py` | `worker.occlusion_guard`, `app.geometry_healing` | unchanged |
| `app/comparison.py` | `app.visual_spec_w27b` | unchanged |
| `app/comparison_peers.py` | `app.visual_spec_w27b` | unchanged |
| `app/container_semantics.py` | `worker.visual`, `worker.scene_composition`, `app.layout_validation`, `app.visual_spec_w27b`, `app.action_end_state` | unchanged |
| `app/degradation.py` | `worker.expression_scene`, `worker.render`, `app.ledger_shapes` | unchanged |
| `app/expression_contract.py` | `worker.scenekit_renderer`, `worker.render_actions`, `worker.render`, `app.action_start_state` | boundary adaptation |
| `app/geometry_healing.py` | `worker.subject_geometry`, `worker.frame_renderer`, `worker.scenekit_renderer`, `worker.scene_composition`, `worker.beat_animation`, `app.action_geometry` | unchanged |
| `app/json_safe.py` | `app.comparison_peers` | unchanged |
| `app/layout_validation.py` | `worker.scenekit_renderer`, `worker.render`, `app.visual_thresholds`, `app.geometry_healing` | unchanged |
| `app/ledger_shapes.py` | `worker.expression_scene`, `worker.scenekit_renderer` | unchanged |
| `app/logic_w24.py` | `worker.logic_w24`, `worker.visual` | boundary adaptation |
| `app/official_shapes.py` | `app.ledger_shapes` | unchanged |
| `app/performance.py` | `worker.visual` | boundary adaptation |
| `app/relation_migration.py` | `worker.expression_scene`, `worker.phenomenon`, `app.expression_contract` | unchanged |
| `app/response_assembly.py` | `worker.display_composition`, `worker.scenekit_renderer`, `worker.scene_composition`, `worker.render_actions`, `app.sentence_beats`, `app.action_geometry`, `app.json_safe`, `app.comparison_peers` | unchanged |
| `app/scene_budget.py` | `worker.scenekit_renderer`, `worker.render` | unchanged |
| `app/self_check_budget.py` | `app.visual_validation` | unchanged |
| `app/semantic_bands.py` | `worker.display_composition`, `worker.expression_scene`, `worker.occlusion_guard`, `worker.diagram_composition`, `worker.scenekit_renderer`, `worker.phenomenon`, `worker.scene_composition` | unchanged |
| `app/sentence_beats.py` | `worker.visual`, `worker.scenekit_renderer`, `worker.render_actions`, `app.action_geometry`, `app.action_start_state` | unchanged |
| `app/shape_implementations.py` | `worker.visual`, `worker.scenekit_renderer`, `worker.shapes_w293`, `worker.shapes_o1`, `app.ledger_shapes`, `app.visual_spec_w27b` | unchanged |
| `app/shape_vocab.py` | `worker.scenekit_renderer`, `worker.scenekit_shapes`, `app.ledger_shapes` | unchanged |
| `app/storyboard_trace.py` | `app.action_geometry`, `app.self_check_budget`, `app.visual_validation` | unchanged |
| `app/video_contract.py` | `worker.subject_geometry` | boundary adaptation |
| `app/visual_spec_w27b.py` | `worker.scenekit_renderer`, `worker.shoe_pixels`, `worker.label_glyphs`, `worker.silhouette_pixels`, `app.sentence_beats`, `app.ledger_shapes`, `app.visual_validation`, `app.visual_spec_w27c` | boundary adaptation |
| `app/visual_spec_w27c.py` | `worker.scenekit_renderer`, `app.visual_validation` | boundary adaptation |
| `app/visual_thresholds.py` | `worker.subject_geometry`, `worker.composition_b5`, `worker.scenekit_renderer`, `worker.lighting_declaration`, `worker.material_pixels`, `app.action_geometry`, `app.visual_spec_w27b`, `app.geometry_healing`, `app.visual_spec_w27c`, `app.action_end_state` | boundary adaptation |
| `app/visual_validation.py` | `worker.scenekit_renderer` | boundary adaptation |
| `app/word_timing.py` | `worker.captions`, `app.sentence_beats` | unchanged |
| `demo/offline.py` | `demo.run` | unchanged |
| `demo/run.py` | Entry point | unchanged |
| `worker/ambient.py` | `worker.size_semantics`, `worker.scenekit_renderer`, `worker.scene_composition`, `worker.shapes_o1`, `worker.render_actions` | unchanged |
| `worker/beat_animation.py` | `worker.display_composition`, `worker.diagram_composition`, `worker.scenekit_renderer`, `worker.scene_composition` | unchanged |
| `worker/captions.py` | `worker.scenekit_renderer`, `app.visual_spec_w27c` | unchanged |
| `worker/celestial.py` | `worker.display_composition`, `worker.diagram_composition`, `worker.scenekit_renderer`, `worker.scene_composition` | unchanged |
| `worker/composition_b5.py` | `worker.scenekit_renderer`, `worker.scene_composition`, `worker.render`, `app.visual_spec_w27b`, `app.visual_validation` | unchanged |
| `worker/depth.py` | `worker.scenekit_renderer`, `worker.scene_composition` | unchanged |
| `worker/depth_measure.py` | `worker.scene_composition`, `worker.depth` | unchanged |
| `worker/design_tokens.py` | `worker.logic_w24`, `worker.expression_scene`, `worker.shapes_b4`, `worker.visual_style`, `worker.composition_b5`, `worker.visual`, `worker.diagram_composition`, `worker.scenekit_renderer`, `worker.phenomenon`, `worker.shapes_w293`, `worker.scene_composition`, `worker.label_glyphs`, `worker.scenekit_v9`, `worker.beat_animation`, `worker.depth`, `worker.scenekit_shapes`, `worker.shapes_o1`, `worker.scenekit_v8`, `worker.overlays`, `worker.render` | unchanged |
| `worker/diagram_composition.py` | `worker.scenekit_renderer` | unchanged |
| `worker/display_composition.py` | `worker.scenekit_renderer` | unchanged |
| `worker/drawing_plan.py` | `worker.display_composition`, `worker.expression_scene`, `worker.diagram_composition`, `worker.scenekit_renderer`, `worker.scene_composition`, `worker.depth` | unchanged |
| `worker/encoding.py` | `worker.render` | unchanged |
| `worker/errors.py` | `worker.process_evidence`, `worker.encoding`, `worker.frame_pool`, `worker.render_actions`, `worker.render`, `app.action_geometry`, `app.degradation` | unchanged |
| `worker/expression_scene.py` | `worker.scenekit_renderer`, `worker.scene_composition` | unchanged |
| `worker/frame_pool.py` | `worker.render` | unchanged |
| `worker/frame_renderer.py` | `worker.render` | unchanged |
| `worker/frame_safety.py` | `worker.scenekit_renderer` | unchanged |
| `worker/json_files.py` | `worker.render` | unchanged |
| `worker/label_glyphs.py` | `app.visual_validation` | unchanged |
| `worker/label_selection.py` | `worker.composition_b5`, `worker.scenekit_renderer`, `worker.overlays` | unchanged |
| `worker/lighting_declaration.py` | `worker.size_semantics`, `worker.display_composition`, `worker.expression_scene`, `worker.shapes_b4`, `worker.occlusion_guard`, `worker.diagram_composition`, `worker.scenekit_renderer`, `worker.scene_composition`, `worker.celestial`, `worker.scenekit_shapes`, `worker.shapes_o1`, `worker.frame_safety`, `worker.material_pixels` | unchanged |
| `worker/logic_w24.py` | `worker.scenekit_renderer`, `worker.scene_composition` | unchanged |
| `worker/material_pixels.py` | `worker.lighting_declaration`, `app.visual_validation` | unchanged |
| `worker/occlusion_guard.py` | `worker.scenekit_renderer`, `worker.drawing_plan`, `app.geometry_healing` | unchanged |
| `worker/overlays.py` | `worker.composition_b5`, `worker.diagram_composition`, `worker.scenekit_renderer`, `worker.frame_safety` | unchanged |
| `worker/peak_memory.py` | `worker.encoding`, `worker.render` | unchanged |
| `worker/phenomenon.py` | `worker.expression_scene` | unchanged |
| `worker/pixel_regions.py` | `worker.lighting_declaration`, `worker.material_pixels` | unchanged |
| `worker/process_evidence.py` | `worker.encoding`, `worker.render_actions` | unchanged |
| `worker/raster_cache.py` | `worker.depth_measure`, `worker.scene_composition`, `worker.lighting_declaration`, `worker.material_pixels`, `app.action_end_state` | unchanged |
| `worker/relation_geometry.py` | `worker.expression_scene`, `worker.phenomenon` | unchanged |
| `worker/render.py` | `demo.run`, `worker.frame_renderer`, `worker.scenekit_renderer`, `worker.shapes_o1`, `worker.overlays`, `app.visual_validation` | unchanged |
| `worker/render_actions.py` | `worker.frame_renderer`, `worker.frame_pool`, `worker.scenekit_renderer`, `worker.render`, `app.action_geometry` | unchanged |
| `worker/render_resources.py` | `worker.frame_renderer`, `worker.render` | unchanged |
| `worker/scene_composition.py` | `worker.scenekit_renderer` | unchanged |
| `worker/scenekit_renderer.py` | `worker.display_composition`, `worker.visual`, `worker.diagram_composition`, `worker.frame_renderer`, `worker.frame_pool`, `worker.scene_composition`, `worker.beat_animation`, `worker.overlays`, `worker.render_actions`, `worker.render`, `app.action_geometry`, `app.action_start_state`, `app.self_check_budget` | unchanged |
| `worker/scenekit_shapes.py` | `worker.shapes_b4`, `worker.scenekit_renderer`, `worker.scene_composition`, `worker.shapes_o1` | unchanged |
| `worker/scenekit_v8.py` | `worker.scenekit_v9` | unchanged |
| `worker/scenekit_v9.py` | `worker.scenekit_renderer`, `worker.shapes_o1` | unchanged |
| `worker/shape_redraw.py` | `worker.size_semantics` | unchanged |
| `worker/shapes_b4.py` | `worker.scenekit_renderer`, `worker.scene_composition`, `worker.shapes_o1` | unchanged |
| `worker/shapes_o1.py` | `worker.display_composition`, `worker.diagram_composition`, `worker.scenekit_renderer`, `worker.scene_composition` | unchanged |
| `worker/shapes_w293.py` | `worker.scenekit_renderer` | unchanged |
| `worker/shoe_pixels.py` | `app.visual_validation` | unchanged |
| `worker/silhouette_pixels.py` | `app.visual_validation` | unchanged |
| `worker/size_semantics.py` | `worker.scenekit_renderer`, `worker.scene_composition` | unchanged |
| `worker/soft_safety.py` | `worker.scenekit_renderer` | unchanged |
| `worker/subject_geometry.py` | `worker.composition_b5`, `worker.scenekit_renderer`, `worker.scene_composition`, `worker.material_pixels`, `app.visual_validation` | unchanged |
| `worker/visual.py` | `demo.run`, `worker.display_composition`, `worker.expression_scene`, `worker.composition_b5`, `worker.diagram_composition`, `worker.scenekit_renderer`, `worker.shapes_w293`, `worker.scene_composition`, `worker.captions`, `worker.label_glyphs`, `worker.scenekit_v9`, `worker.scenekit_shapes`, `worker.shapes_o1`, `worker.scenekit_v8`, `worker.overlays`, `worker.render` | unchanged |
| `worker/visual_style.py` | `worker.expression_scene`, `worker.scenekit_shapes` | unchanged |

## Runtime data and entry adaptations

- `worker/size_label_words.json`: vocabulary loaded by the size renderer.
- `worker/awen_o1.json`: character geometry loaded by the scene shape renderer.
- `demo/offline.py`: existing input models and local diagnostic adapters; hard findings remain blocking.
- `demo/run.py`: unchanged fixed input validation, renderer call and output filename adaptation.
- `demo/storyboard.json`: unchanged manually authored 16-second example, including all narration, action and subtitle timing fields.

## Contracts and fonts

All contract working-tree files are copied, including uncommitted changes. Endpoint examples use the documentation address 192.0.2.1; descriptive wording is normalized. No contract source is taken from a committed revision.

Three font binaries are unchanged: TellkitHappySubset-Regular.ttf, TellkitSansSubset-Regular.otf and SourceHanSansCN-Regular.otf. Original OFL texts accompany them. Ancillary font build instructions and unrelated character lists are omitted.

## Other new delivery files

`README.md`, `README.zh.md`, `docs/adr/0001.md`–`0020.md`, `LICENSE`, `NOTICE`, `Dockerfile`, `requirements.txt`, `.gitignore`, plus records under `demo/`. Only `out/episode.mp4` is shipped. The demo still generates render manifests, reports, lighting declarations and offline diagnostics locally; `.gitignore` excludes `out/*` except `out/episode.mp4`.
