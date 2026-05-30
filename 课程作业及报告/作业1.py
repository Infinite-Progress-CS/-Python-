from PIL import  Image,ImageDraw,ImageFont
from PIL import ImageFilter
import sys
import  os
import glob

im = Image.open(r"C:\Users\HP\PycharmProjects\pythonProject1\论文实验\dataset\tinyimagenet-200\train\n01443537\images\n01443537_2.JPEG")
im.show()
print(im.format,im.size,im.mode)

width,height = im.size
res = Image.new(im.mode,(width*2,height*2))
res.paste(im,(0,0,width,height))
contour = im.filter(ImageFilter.CONTOUR)

res.paste(contour,(width,0,2*width,height))
emboss = im.filter(ImageFilter.EMBOSS)
res.paste(emboss,(0,height,width,2*height))

edges = im.filter(ImageFilter.FIND_EDGES)
res.paste(edges,(width,height,2*width,2*height))
res.show()

img_path = "D:\大学专业课\计算机科学与技术\个性发展课\Python程序设计\图片库" + "/*" + "JPEG"
for infile in glob.glob(img_path):
    f,e = os.path.splitext(infile)
    outfile = f + "." + "PNG"
    Image.open(infile).save(outfile)

size = (128,128)
for infile in glob.glob(img_path):
    f, e = os.path.splitext(infile)
    outfile = f + "_s." + "JPEG"
    img = Image.open(infile)
    img.thumbnail(size, Image.Resampling.LANCZOS)
    img.save(outfile)

img_suffix = "JPEG"
txt_log = "Python"
for infile in glob.glob(img_path):
    f, e = os.path.splitext(infile)
    outfile = f + "_w." + img_suffix
    img = Image.open(infile)
    im_log = Image.new('RGBA',im.size)
    fnt = ImageFont.truetype("c:/Windows/fonts/Tahoma.ttf",20)
    d = ImageDraw.ImageDraw(im_log)
    d.text((0,0),txt_log,font=fnt)
    im_out = Image.composite(im_log,im,im_log)
    im_out.save(outfile)