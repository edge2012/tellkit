"""Event models and arrow geometry used by rendering."""
import math
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal


class Sample(BaseModel):
    model_config = ConfigDict(extra='forbid')
    at: float = Field(ge=0, le=1)
    position: int = Field(ge=0, le=8)

class Handoff(BaseModel):
    model_config = ConfigDict(extra='forbid', serialize_by_alias=True, populate_by_name=True)
    from_: str = Field(alias='from', min_length=1)
    to: str = Field(min_length=1)
    action: Literal['pan', 'transform']








def arrow_geometry(arrows, objects):
    errors=[]; lookup={x['id']:x['bbox'] for x in objects}
    def inside(p,b):
        x,y,w,h=b;return x-8<=p[0]<=x+w+8 and y-8<=p[1]<=y+h+8
    for a in arrows:
        if a.get('from') not in lookup or a.get('to') not in lookup:
            errors.append('ARROW_ORPHAN');continue
        src,dst=lookup[a['from']],lookup[a['to']]
        x,y,w,h=src;u,v,r,s=dst
        distance=math.hypot(max(x-u-r,u-x-w,0),max(y-v-s,v-y-h,0))
        if not inside(a['start'],src) or not inside(a['end'],dst):
            errors.append('ARROW_ORPHAN')
        if math.dist(a['start'],a['end'])<distance*.8:
            errors.append('ARROW_LENGTH')
    return errors


