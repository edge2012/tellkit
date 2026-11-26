# Render entry evidence

Demo: `demo/run.py:13` imports `render` from `worker.render`;
`demo/run.py:29` calls `render(board, out, aspects=('16x9',), frame_workers=1)`.

Service caller (source tree, intentionally not bundled):
`worker/main.py:626` launches `python -m worker.pipeline`;
`worker/pipeline.py:29` imports `render` from `worker.render`;
`worker/pipeline.py:619` calls `render(board, root/'artifacts', sources=sources, captions=captions)`.

The function is `worker/render.py:119`, decorated by `PeakMemory` at line 118.
The demo does not replace, wrap or patch the rendering function. Its source file
is byte-for-byte identical to the input repository. Input and diagnostic service
adapters live separately in `demo/offline.py`.
