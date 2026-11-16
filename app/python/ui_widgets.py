from PIL import Image, ImageDraw, ImageTk

def icon(master, name, color, size=22):
    image=Image.new("RGBA",(24,24))
    draw=ImageDraw.Draw(image)
    def line(points): draw.line(points,fill=color,width=2)
    if name in ("left","right","up","down"):
        arrow=[(15,5),(8,12),(15,19)]
        if name=="right": arrow=[(24-x,y) for x,y in arrow]
        if name in ("up","down"): arrow=[(y,x if name=="up" else 24-x) for x,y in arrow]
        line(arrow)
    elif name=="home":
        line([(3,11),(12,3),(21,11)]); line([(6,10),(6,21),(18,21),(18,10)])
    elif name=="pan":
        line([(12,2),(12,22)]); line([(2,12),(22,12)])
        for points in ([(8,6),(12,2),(16,6)],[(8,18),(12,22),(16,18)],[(6,8),(2,12),(6,16)],[(18,8),(22,12),(18,16)]): line(points)
    elif name in ("zoom","target"):
        draw.ellipse((3,3,16,16),outline=color,width=2); line([(15,15),(22,22)])
        if name=="target": line([(6,10),(13,10)]); line([(10,6),(10,13)])
    elif name=="point":
        draw.ellipse((5,2,19,16),outline=color,width=2); line([(6,13),(12,22),(18,13)])
        draw.ellipse((10,7,14,11),fill=color)
    elif name=="legend":
        for y in (5,11,17): draw.rectangle((3,y,7,y+3),fill=color); line([(11,y+1),(21,y+1)])
    elif name=="style":
        for y,x in ((5,9),(12,16),(19,7)):
            line([(3,y),(21,y)]); draw.rectangle((x-2,y-2,x+2,y+2),fill=color)
    elif name in ("clear_selection","clear_measure"):
        if name=="clear_selection":
            draw.rectangle((3,3,16,16),outline=color,width=2)
        else:
            line([(3,16),(15,4)])
            for x,y in ((3,16),(15,4)): draw.ellipse((x-2,y-2,x+2,y+2),fill=color)
        line([(15,15),(22,22)]); line([(22,15),(15,22)])
    elif name=="eye_off":
        draw.ellipse((2,6,22,18),outline=color,width=2)
        line([(3,3),(21,21)])
    elif name=="eye":
        draw.ellipse((2,6,22,18),outline=color,width=2); draw.ellipse((9,9,15,15),fill=color)
    elif name=="delete":
        line([(6,7),(7,21),(17,21),(18,7)]); line([(4,5),(20,5)]); line([(9,2),(15,2)])
    return ImageTk.PhotoImage(image.resize((size,size),Image.Resampling.LANCZOS),master=master)
