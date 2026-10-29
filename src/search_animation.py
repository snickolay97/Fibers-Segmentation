"""Record actual window trials and reveal the accepted boundary.

The path reveal is not a simulation of the Dijkstra exploration frontier.
"""
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw


def save_search_animation(folder,name,index,axis,origin,mask,background,trials,seam,method,max_frames=24):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    h,w=mask.shape;scale=min(1.,480./max(h,w));size=(max(1,round(w*scale)),max(1,round(h*scale)))
    raw=background if background is not None else mask
    if raw.dtype!=np.uint8:raw=(raw/256).astype(np.uint8)
    base=cv2.resize(raw,size,interpolation=cv2.INTER_AREA)
    if base.ndim==2:base=cv2.cvtColor(base,cv2.COLOR_GRAY2RGB)
    blocked=cv2.resize((mask>0).astype(np.uint8),size,interpolation=cv2.INTER_NEAREST)>0
    base[blocked]=(.65*base[blocked]+.35*np.array([220,60,50])).astype(np.uint8)
    def frame(title,window=None,points=None):
        canvas=Image.new('RGB',(max(480,size[0]),size[1]+50),(18,18,18))
        canvas.paste(Image.fromarray(base),(0,50));draw=ImageDraw.Draw(canvas)
        draw.text((8,5),'{} search #{} | x={}, y={}'.format(axis,index,*origin),fill='white')
        draw.text((8,22),title,fill='white')
        if window:
            a,z=window;draw.rectangle((int(a*scale),50,min(size[0]-1,int(z*scale)),size[1]+49),outline=(80,160,255),width=2)
        if points is not None and len(points)>1:
            pts=[(int(x*scale),50+int(y*scale)) for x,y in points]
            draw.line(pts,fill=(255,240,40),width=2)
        return canvas
    frames=[frame('Obstacle mask overlay; horizontal searches transposed')]
    selected=np.unique(np.linspace(0,len(trials)-1,min(len(trials),max_frames),dtype=int)) if trials else []
    for k in selected:
        frames.append(frame('Window {}: [{}, {})'.format(k+1,*trials[k]),trials[k]))
    if seam is not None:
        points=list(zip(np.asarray(seam).tolist(),range(len(seam))))
        for stop in np.linspace(2,len(points),8,dtype=int):
            frames.append(frame(method+': accepted route reveal',points=points[:stop]))
    else:frames.append(frame('NO PATH: component repair required'))
    frames.append(frame(method+' | final search result',points=points if seam is not None else None))
    stem='{}_search_{:04d}_{}'.format(name,index,axis)
    # A shared palette and full disposal avoid stale text and disappearing
    # route colours in Pillow's multi-frame GIF encoding.
    colours=[(v,v,v) for v in range(0,256,2)]
    colours += [(int(.65*v+.35*220),int(.65*v+.35*60),int(.65*v+.35*50)) for v in range(0,256,4)]
    colours += [(255,240,40),(80,160,255),(255,255,255),(18,18,18)]
    colours += [(0,0,0)]*(256-len(colours))
    palette=Image.new('P',(1,1));palette.putpalette([c for rgb in colours for c in rgb])
    encoded=[f.quantize(palette=palette,dither=Image.NONE) for f in frames]
    encoded[0].save(str(folder/(stem+'.gif')),save_all=True,append_images=encoded[1:],duration=[350]+[120]*(len(encoded)-2)+[900],loop=0,optimize=False,disposal=2)
    (folder/(stem+'.json')).write_text(json.dumps(dict(axis=axis,origin_xy=list(origin),method=method,windows=trials,coordinate_system='local vertical; bottom search is transposed',path_reveal_is_not_solver_frontier=True),indent=2))
