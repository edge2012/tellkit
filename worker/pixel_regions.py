"""Four-connected raster regions as row intervals, without per-pixel Python sets."""
from bisect import bisect_right
import numpy as np


class Region:
    def __init__(self, runs):
        self.runs=runs
        self.bounds=(min(lo for y,lo,hi in runs),min(y for y,lo,hi in runs),
                     max(hi for y,lo,hi in runs),max(y for y,lo,hi in runs)+1)
        self.rows={}
        for y,lo,hi in runs:self.rows.setdefault(y,[]).append((lo,hi))
        self.area=sum(hi-lo for y,lo,hi in runs)

    def __len__(self):
        return self.area

    def __contains__(self, point):
        x,y=point
        return any(lo<=x<hi for lo,hi in self.rows.get(y,()))


def regions(mask):
    padded=np.pad(mask,((0,0),(1,1)))
    ys,edges=np.nonzero(padded[:,1:]!=padded[:,:-1])
    parents=[];runs=[];previous=[];previous_ends=[];current=[];last_y=None
    def root(i):
        while parents[i]!=i:
            parents[i]=parents[parents[i]];i=parents[i]
        return i
    for k in range(0,len(edges),2):
        y=int(ys[k]);lo=int(edges[k]);hi=int(edges[k+1])
        if y!=last_y:
            previous=current if last_y is not None and y==last_y+1 else []
            previous_ends=[r[1] for r in previous];current=[];last_y=y
        i=len(parents);parents.append(i);runs.append((y,lo,hi));current.append((lo,hi,i))
        j=bisect_right(previous_ends,lo)
        while j<len(previous) and previous[j][0]<hi:
            parents[root(previous[j][2])]=root(i);j+=1
    grouped={}
    for i,run in enumerate(runs):grouped.setdefault(root(i),[]).append(run)
    return [Region(run) for run in grouped.values()]
