from app.response_assembly import required_first
from worker.lighting_declaration import for_sprite
from worker.drawing_plan import DrawingPlan
"""Comparison with frozen subject cells, optional cue and a separate narrator."""
import math
from PIL import Image
from worker.visual import centered_text,paste_text

def stage(visual,size,index,t):
 from worker.scenekit_renderer import sprite,BG,_stage_fonts
 w,h=size;portrait=w<h;im=DrawingPlan(size,BG)
 subjects=[it for it in visual.items if it.role=='subject'];cues=[it for it in visual.items if it.role=='decoration']
 ground=h*(690/1280 if portrait else 510/720);n=round(min(w*.42,h*.44))
 metrics=[]
 for j,it in enumerate(subjects):
  sp,mask=sprite(it.shape,it.color,n);cx=w*(.30+.40*j);x,y=round(cx-sp.width/2),round(ground-sp.height)
  from worker.celestial import fit
  sp,x,y=fit(sp,x,y,size,it.shape)
  from worker.beat_animation import transform
  sp,x,y=transform(sp,x,y,it,size)
  from app.semantic_bands import place
  x,y=place(sp,x,y,it,visual,size)
  im.paste(sp,(x,y),sp)
  # W38 labels are composed by frame().
  metrics.append(dict(shape=it.shape,pixel_mask=sp.getchannel('A'),lighting_declaration=for_sprite(sp),bbox=(x,y,sp.width,sp.height)))
 for it in cues:
  sp,_=sprite(it.shape,it.color,32);x=round(w*.5-sp.width/2);y=round(ground-n*.6+20*math.sin(t/700))
  from worker.celestial import fit
  sp,x,y=fit(sp,x,y,size,it.shape)
  from app.semantic_bands import place
  x,y=place(sp,x,y,it,visual,size)
  im.paste(sp,(x,y),sp);metrics.append(dict(shape=it.shape,pixel_mask=sp.getchannel('A'),lighting_declaration=for_sprite(sp),bbox=(x,y,sp.width,sp.height)))
 for it in visual.items:
  if it.shape != 'awen' or it.role != 'character':continue
  from worker.shapes_o1 import awen_sprite,pointing_awen
  # Alternate observing and explaining poses without changing the frozen subjects.
  pose=awen_sprite
  an=180 if portrait else 190
  target_item=visual.items[it.gaze_target] if it.gaze_target is not None else subjects[0]
  target_box=required_first(((m['bbox'] for m in metrics if m['shape']==target_item.shape)), path='worker/worker/display_composition.py:35')
  target=(target_box[0]+target_box[2]/2,target_box[1]+target_box[3]/2)
  x=520 if portrait else 1090;y=860 if portrait else 320
  sp,mask,eyes=pose(an,(-1,0))
  eye=(x+eyes['eye'][0],y+eyes['eye'][1])
  direction=(target[0]-eye[0],target[1]-eye[1])
  sp,mask,eyes=pose(an,direction)
  from worker.celestial import fit
  sp,x,y=fit(sp,x,y,size,it.shape)
  if not visual.poses and visual.camera_motion is None:im.paste(sp,(x,y),sp)
  metrics.append(dict(shape='awen',lighting_declaration=for_sprite(sp),bbox=(x,y,sp.width,sp.height),pose='idle',gaze_target=it.gaze_target,gaze=dict(eye=eye,target=target,direction=direction)))
 return im,dict(objects=metrics,ray_gaps=[],content_bottom=ground+50)
