"""Shared visual values in native 720p pixels; no content semantics."""
from types import MappingProxyType

PALETTE = MappingProxyType(dict(
    primary='#287EB0', secondary='#54876A', accent='#D46A32',
    neutral_900='#2B2118', neutral_600='#72777D',
    neutral_300='#DDE3E7', neutral_050='#FFFFFF',
    ground='#E5DDC9', background='#FBF6EC',
))
STROKE = MappingProxyType(dict(body=4, decoration=2, detail_luma_max=96, color=PALETTE['neutral_900']))
EMPHASIS = MappingProxyType(dict(mix=.6, color=PALETTE['neutral_050']))
RADIUS = MappingProxyType(dict(square=0, small=8, large=16))
SHADOW = MappingProxyType(dict(offset=(0, 4), blur=0, color=PALETTE['neutral_600']))
OPACITY = MappingProxyType(dict(light=100, medium=105))
TYPE = MappingProxyType(dict(title=36, explanation=28, label=24, caption=32, line_height=1.4))
PATH = MappingProxyType(dict(
    primary=6, secondary=4, auxiliary=2, head_ratio=3, head_angle=.5,
    dash_ratio=3, gap_ratio=2, lane_gap=32, arrival_ms=250,
    pulse_ratio=2, halo=2, endpoint_gap_max=2,
))
LAYOUT = MappingProxyType(dict(
    safe=.05, subject_min=.45, subject_max=.65,
    columns=(1/6, 1/2, 5/6), rows=(.38, .57, .76),
    title_y=.05, explanation_y=.12, explanation_width=.60, content_top=.19,
    legend_x=.74, legend_y=.05, legend_width=.21, legend_row=.05,
    leader_max=120, gap=16, padding=12, group_scale=.8,
))
