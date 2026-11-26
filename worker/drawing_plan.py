"""Scene draw commands stay inert until geometry validation succeeds."""
from PIL import Image, ImageDraw

class DrawingPlan:
    def __init__(self, size, background):
        self.size=size;self.width,self.height=size;self.background=background
        self.commands=[]

    def getdraw(self, mode=None):
        plan=self
        class Pen:
            def __getattr__(self,name):
                def record(*args,**kwargs):
                    plan.commands.append(('draw',name,args,kwargs,mode))
                return record
        return Pen()

    def paste(self,image,box,mask=None):
        self.commands.append(('paste',image.copy(),box,mask.copy() if hasattr(mask,'copy') else mask))

    def putpixel(self,xy,color):
        self.commands.append(('pixel',xy,color))

    def render(self):
        image=Image.new('RGB',self.size,self.background)
        for command in self.commands:
            if command[0]=='pixel':image.putpixel(*command[1:])
            elif command[0]=='paste':
                from worker.occlusion_guard import assert_not_fullscreen
                assert_not_fullscreen((*command[2][:2], *command[1].size), self.size)
                image.paste(*command[1:])
            else:
                _,name,args,kwargs,mode=command
                getattr(ImageDraw.Draw(image,mode),name)(*args,**kwargs)
        return image
