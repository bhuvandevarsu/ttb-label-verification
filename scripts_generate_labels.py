from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import random

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'sample_labels'
OUT.mkdir(exist_ok=True)
W,H = 1400,1900
NAVY=(30,42,58); CREAM=(248,244,232); GOLD=(176,134,55); RED=(115,30,25); BLACK=(25,25,25)
WARNING='GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.'

def font(size,bold=False):
    p='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    return ImageFont.truetype(p,size)

def wrap(draw,text,f,maxw):
    words=text.split(); lines=[]; cur=''
    for w in words:
        t=(cur+' '+w).strip()
        if draw.textbbox((0,0),t,font=f)[2] <= maxw: cur=t
        else: lines.append(cur); cur=w
    if cur: lines.append(cur)
    return lines

def label(warning=WARNING, tilt=0, glare=False, name='label'):
    im=Image.new('RGB',(W,H),CREAM); d=ImageDraw.Draw(im)
    d.rounded_rectangle((55,55,W-55,H-55),radius=35,outline=GOLD,width=8,fill=(255,251,241))
    d.rectangle((110,110,W-110,330),fill=NAVY)
    d.text((W//2,165),'OLD TOM DISTILLERY',font=font(74,True),anchor='mm',fill='white')
    d.text((W//2,260),'EST. 1891 · KENTUCKY',font=font(30,True),anchor='mm',fill=(221,229,237))
    d.text((W//2,500),'KENTUCKY STRAIGHT BOURBON WHISKEY',font=font(54,True),anchor='mm',fill=BLACK)
    d.line((250,610,W-250,610),fill=GOLD,width=6)
    d.text((W//2,720),'45% Alc./Vol. (90 Proof)',font=font(54,True),anchor='mm',fill=BLACK)
    d.text((W//2,800),'750 mL',font=font(50),anchor='mm',fill=BLACK)
    d.text((W//2,925),'BOTTLED BY OLD TOM DISTILLERY',font=font(36,True),anchor='mm',fill=NAVY)
    d.text((W//2,990),'FRANKFORT, KENTUCKY · UNITED STATES',font=font(30),anchor='mm',fill=BLACK)
    d.rounded_rectangle((170,1080,W-170,1650),radius=20,outline=(60,60,60),width=3,fill=(252,249,239))
    wf=font(27,True)
    y=1120
    for line in wrap(d,warning,wf,W-400):
        d.text((205,y),line,font=wf,fill=BLACK); y+=47
    d.text((W//2,1740),'SMALL BATCH · BARREL AGED',font=font(31,True),anchor='mm',fill=GOLD)
    if glare:
        overlay=Image.new('RGBA',im.size,(255,255,255,0)); od=ImageDraw.Draw(overlay)
        od.polygon([(80,300),(360,180),(980,1600),(700,1750)],fill=(255,255,255,72))
        im=Image.alpha_composite(im.convert('RGBA'),overlay).convert('RGB')
    if tilt:
        im=im.rotate(tilt,expand=True,resample=Image.Resampling.BICUBIC,fillcolor=(220,215,202))
    im.save(OUT/f'{name}.jpg',quality=94)

label(name='01_pass_clean')
label(name='02_pass_rotated',tilt=4)
label(name='03_pass_glare',glare=True)
label(warning=WARNING.replace('women should not drink alcoholic beverages', 'women should drink alcoholic beverages'),name='04_fail_warning')
label(tilt=-6,glare=True,name='05_review_rotated_glare')
# A deliberate ABV mismatch for a deterministic failure.
im=Image.open(OUT/'01_pass_clean.jpg'); d=ImageDraw.Draw(im); d.rectangle((360,675,1040,765),fill=CREAM); d.text((W//2,720),'40% Alc./Vol. (80 Proof)',font=font(54,True),anchor='mm',fill=BLACK); im.save(OUT/'06_fail_abv.jpg',quality=94)
print('Generated',len(list(OUT.glob('*.jpg'))),'sample labels in',OUT)
