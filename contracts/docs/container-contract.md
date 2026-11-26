# W30 容器承载契约

VisualItem 增加可选字符串 `id` 和 `parent`。`parent` 引用同场容器的 `id`；未声明 id 的旧对象沿用零起始 items 下标字符串。禁止重复 id、自引用、悬空引用、嵌套容器、父或子 count 大于 1。索引型 from/to/gaze_target 保持原语义。

当前支持真实内壁的形状为 water_cup_tall、water_cup_wide、sugar_solution、tank_stone、tank_wood；其他形状不能声明为父容器。parent 只用于带 background 的 tank/table/ground 共享物理场景。已有复合形状内部绘制的内容保持原样；不会自动根据旁白推断 parent。

内壁矩形由 shapes_b2 的容器绘制器产生，扣除轮廓笔画，减去裁剪偏移，再按实际 sprite 缩放和平移换算到像素坐标，记录为 metrics.inner_rect（x,y,width,height）。斜壁取内接矩形，不用外框。内容的 bbox 不裁剪、不缩小来隐藏违规。

顶层对象保留完整规则。子对象保留尺寸和画面越界检查，使用 R5b 的内壁超出量 ≤4px、同父内容重叠深度 ≤2px；不参与外部24px间距、重复形状和中线构图判定。R11b 需要内壁范围内的投影矩形，或实际绘制的底面接触线（与底面误差≤4px）；画面地面投影与 ground_error_px=0 不构成容器支撑证据。

内容默认按同父兄弟分槽置于内底面；自身 placement 是画面归一化位移，父容器移动则内容同步移动。几何排布器只排顶层对象，不独立把内容移出容器；R5b 和内部支撑错误原样返回，不用外部重排修复。

schema 同步到 contracts/storyboard.schema.json、api/contracts/storyboard.schema.json 和 api/internal/storyboardcontract/storyboard.schema.json。部署规则身份同时涵盖 parent 校验器与绘制内壁的 shapes_b2。
