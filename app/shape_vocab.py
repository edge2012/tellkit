"""Shared W10 shape vocabulary."""
NEW_SHAPES = dict(rain="雨", ground="地面", ape_bent="猿弯背", ape_upright="猿直立", human_standing="人站立", human_bent="人弯腰", child="孩子", tree="树", grass="草", mountain="山", river="河", cloud="云", drop="雨滴", sun="太阳", moon="月亮", earth="地球", star="星星", stone_axe="石斧", spear="长矛", jar="罐子", campfire="火堆", house="房子", boat="船", car="车", arrow="直箭头", curved_arrow="弯箭头", timeline="时间轴刻度", question="问号", check="对勾", cross="叉")
OLD_SHAPES = set("diagram_box circle square triangle star drop lightning stick sun cloud rainbow block heart tooth toothbrush moon candy apple book card bacteria sound vibration heat cold wind force time many".split())
NEW_SHAPES.update({'silhouette_quadruped': '四足剪影', 'silhouette_leaning': '半直立剪影', 'silhouette_upright': '直立剪影', 'silhouette_upright_tool': '举工具剪影', 'timeline_axis': '时间轴', 'water_drop': '水滴', 'rotation_axis': '自转轴', 'sun_ray': '光束'})
SHAPES = OLD_SHAPES | NEW_SHAPES.keys()
