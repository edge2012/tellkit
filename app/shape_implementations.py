"""The single source of truth for shapes the renderer can draw."""
BASE = frozenset('diagram_box apple bacteria block book candy card circle cloud cold drop force heart heat lightning many moon rainbow sound square star stick sun time tooth toothbrush triangle vibration wind'.split())
W10 = frozenset('ape_bent ape_upright arrow boat campfire car check child cloud cross curved_arrow drop earth grass house human_bent human_standing jar moon mountain question river spear star stone_axe sun timeline tree'.split())
O1 = frozenset('foot_left foot_right knife awen cookie_half cookie_large cookie_small cookie_whole drum ear_section ice_block ice_melting rain_basin rotation_globe route_long route_short shoe_left shoe_right sugar_grains sugar_solution tank_stone tank_wood vapor_particles water_cup_tall water_cup_wide'.split())
B2 = frozenset('tank cup bowl water stone wood cookie shoe water_cup_tall water_cup_wide tank_stone tank_wood sugar_solution ice ear'.split())
W18 = frozenset(['silhouette_quadruped', 'silhouette_leaning', 'silhouette_upright', 'silhouette_upright_tool', 'timeline_axis', 'water_drop', 'rotation_axis', 'sun_ray'])
W293 = frozenset('graupel charge channel brain sleeping_child memory_card'.split())
IMPLEMENTED = W293 | BASE | W10 | O1 | B2 | W18 | {'rain', 'ground'}

# Registry rule: adding a shape changes IMPLEMENTED here and nowhere else. A
# second hand-written render whitelist is a bug. Named backend inventories are
# dispatch subsets only and must never be used as a global render gate.
assert all(part <= IMPLEMENTED for part in (BASE, W10, O1, B2, W18, W293))

def require_shape(shape, supported=None):
    if shape not in (IMPLEMENTED if supported is None else supported):
        raise ValueError(f'UNKNOWN_SHAPE shape={shape}: 该形状尚未实现')
    return shape
