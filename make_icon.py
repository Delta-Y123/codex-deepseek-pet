# -*- coding: utf-8 -*-
"""生成应用图标 pet.ico。"""
from PIL import Image, ImageDraw

def face(size):
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 圆角底
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=(25, 28, 42, 255))
    d.rounded_rectangle([1, 1, s - 2, s - 2], radius=int(s * 0.21),
                        outline=(77, 107, 254, 255), width=max(1, int(s * 0.02)))
    # 脸
    m = int(s * 0.18)
    d.ellipse([m, m, s - m, s - m], fill=(16, 163, 127, 255), outline=(234, 255, 247, 255),
              width=max(2, int(s * 0.02)))
    # 眼睛
    ey = int(s * 0.44)
    r = int(s * 0.075)
    for cx in (int(s * 0.37), int(s * 0.63)):
        d.ellipse([cx - r, ey - r, cx + r, ey + r], fill=(11, 31, 25, 255))
        d.ellipse([cx - r * 0.35, ey - r * 0.7, cx + r * 0.15, ey - r * 0.15], fill=(255, 255, 255, 255))
    # 微笑
    d.arc([int(s * 0.34), int(s * 0.56), int(s * 0.66), int(s * 0.80)], 20, 160,
          fill=(11, 31, 25, 255), width=max(2, int(s * 0.025)))
    return img

sizes = [16, 24, 32, 48, 64, 128, 256]
imgs = [face(s) for s in sizes]
imgs[-1].save(r"D:\For Desktop Pet\pet.ico", format="ICO",
              sizes=[(s, s) for s in sizes])
print("saved pet.ico")
