"""Identidade visual do Convergio (mesma família do Dispersio PDF).

Marca: vários feixes de luz (as conexões) convergem numa seta de download.
O Dispersio abre a luz em cores; o Convergio junta as cores num arquivo só.
Gera: logo.png (1024), convergio.png (256) e convergio.ico (16–256).
"""
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter

S = 1024
INDIGO_1, INDIGO_2 = (28, 20, 78), (66, 36, 168)
VIOLETA, AZUL, DOURADO = (190, 150, 255), (110, 150, 255), (255, 184, 84)
AQUI = os.path.dirname(os.path.abspath(__file__))


def gradiente(size, c1, c2):
    g = Image.new("RGB", (2, 64))
    for y in range(64):
        t = y / 63
        g.putpixel((0, y), tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
        g.putpixel((1, y), g.getpixel((0, y)))
    return g.resize(size, Image.BICUBIC)


def brilho_radial(size, centro, raio, cor, forca):
    m = Image.new("L", (128, 128), 0)
    cx, cy, r = centro[0] / size * 127, centro[1] / size * 127, raio / size * 127
    for y in range(128):
        for x in range(128):
            d = math.hypot(x - cx, y - cy) / r
            m.putpixel((x, y), int(255 * forca * max(0.0, 1 - d) ** 2))
    camada = Image.new("RGBA", (size, size), cor + (0,))
    camada.putalpha(m.resize((size, size), Image.BICUBIC))
    return camada


def feixe(draw, p0, p1, w0, w1, cor):
    """Feixe afunilado de p0 (largura w0) até p1 (largura w1)."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    n = math.hypot(dx, dy)
    nx, ny = -dy / n, dx / n
    draw.polygon([(p0[0] + nx * w0 / 2, p0[1] + ny * w0 / 2), (p1[0] + nx * w1 / 2, p1[1] + ny * w1 / 2),
                  (p1[0] - nx * w1 / 2, p1[1] - ny * w1 / 2), (p0[0] - nx * w0 / 2, p0[1] - ny * w0 / 2)], fill=cor)


def desenhar(S=S):
    k = S / 1024
    caixa = (int(56 * k), int(56 * k), int(968 * k), int(968 * k))
    fundo = gradiente((S, S), INDIGO_1, INDIGO_2).convert("RGBA")
    fundo.alpha_composite(brilho_radial(S, (512 * k, 520 * k), 430 * k, (124, 58, 237), 0.85))
    mascara = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(caixa, radius=int(210 * k), fill=255)

    # feixes (conexões) convergindo
    luz = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(luz)
    foco = (512 * k, 520 * k)
    for x0, cor in ((150, VIOLETA), (512, AZUL), (874, DOURADO)):
        feixe(d, (x0 * k, 40 * k), foco, 120 * k, 40 * k, cor + (235,))
    glow = luz.filter(ImageFilter.GaussianBlur(28 * k))
    camada = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    camada.alpha_composite(glow)
    camada.alpha_composite(glow)
    camada.alpha_composite(luz)

    # seta de download branca + bandeja
    seta = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    a = ImageDraw.Draw(seta)
    branco = (246, 243, 255, 255)
    a.rounded_rectangle((462 * k, 470 * k, 562 * k, 690 * k), radius=int(18 * k), fill=branco)
    a.polygon([(322 * k, 604 * k), (702 * k, 604 * k), (512 * k, 808 * k)], fill=branco)
    a.rounded_rectangle((262 * k, 836 * k, 762 * k, 904 * k), radius=int(34 * k), fill=branco)
    # cantos arredondados (como o triângulo do prisma do Dispersio)
    alfa = seta.getchannel("A").filter(ImageFilter.GaussianBlur(16 * k)).point(lambda v: 255 if v > 150 else 0)
    alfa = alfa.filter(ImageFilter.GaussianBlur(1.2 * k))
    seta = Image.new("RGBA", (S, S), branco[:3] + (0,))
    seta.putalpha(alfa)
    sombra = Image.new("RGBA", (S, S), (10, 5, 40, 0))
    sombra.putalpha(seta.getchannel("A").filter(ImageFilter.GaussianBlur(18 * k)).point(lambda v: v * 0.55))
    nucleo = brilho_radial(S, (512 * k, 520 * k), 120 * k, (255, 255, 255), 0.9)

    img = fundo
    img.alpha_composite(camada)
    img.alpha_composite(nucleo)
    img.alpha_composite(sombra, (0, int(10 * k)))
    img.alpha_composite(seta)
    # borda sutil
    borda = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(borda).rounded_rectangle(caixa, radius=int(210 * k), outline=(255, 255, 255, 40), width=max(1, int(6 * k)))
    img.alpha_composite(borda)
    img.putalpha(ImageChops.multiply(img.getchannel("A"), mascara))
    return img


if __name__ == "__main__":
    grande = desenhar(1024)
    grande.save(os.path.join(AQUI, "logo.png"))
    grande.resize((256, 256), Image.LANCZOS).save(os.path.join(AQUI, "convergio.png"))
    tamanhos = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    imgs = [grande.resize((t, t), Image.LANCZOS) for t in tamanhos]
    imgs[-1].save(os.path.join(AQUI, "convergio.ico"), sizes=[(t, t) for t in tamanhos], append_images=imgs[:-1])
    print("ícones gerados")
    # imagens do instalador (Inno Setup): lateral 328x628 (2x de 164x314) e pequena 110x116
    lateral = gradiente((328, 628), INDIGO_1, INDIGO_2).convert("RGBA")
    lateral.alpha_composite(brilho_radial(328, (164, 200), 260, (124, 58, 237), 0.8).resize((328, 628)), (0, 0))
    lateral.alpha_composite(grande.resize((200, 200), Image.LANCZOS), (64, 150))
    lateral.convert("RGB").save(os.path.join(AQUI, "wizard.bmp"))
    pequena = Image.new("RGBA", (110, 116), (255, 255, 255, 255))
    pequena.alpha_composite(grande.resize((100, 100), Image.LANCZOS), (5, 8))
    pequena.convert("RGB").save(os.path.join(AQUI, "wizard_small.bmp"))
