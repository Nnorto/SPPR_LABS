"""Схема из общей геометрии: редактируемый draw.io и PNG для отчёта."""
from pathlib import Path
import xml.etree.ElementTree as ET
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from settings import ROOT

NODES = {
    "nasa": (40, 45, 300, 85, "NASA POWER / MERRA-2\nИстория, 2021–2025"),
    "meteo": (390, 45, 300, 85, "Open-Meteo / ERA5\nАльтернативный адаптер"),
    "owm": (1040, 45, 300, 85, "OpenWeatherMap\nТекущие наблюдения + ключ"),
    "history": (215, 220, 300, 85, "JSON → проверка единиц\nUTC → Europe/Moscow"),
    "current": (1040, 220, 300, 85, "JSON → температура,\nвлажность, ветер, время"),
    "expert": (665, 220, 300, 85, "База знаний\n7 общих + 1 правило города"),
    "norms": (215, 395, 300, 85, "Сезонные статистики\nСреднее, s, min, max"),
    "fuzzy": (665, 395, 300, 110, "Мамдани: фаззификация\nИ/ИЛИ → активация\nmax → центр тяжести"),
    "anomaly": (1040, 470, 300, 85, "Сравнение с сезоном\nΔ и z; учебный порог |z|>2"),
    "result": (665, 620, 300, 85, "Индекс комфорта\n+ предупреждения и советы"),
    "table": (215, 785, 300, 70, "CSV / JSON / Markdown\nТаблицы и трассировка"),
    "plots": (665, 785, 300, 70, "PNG: термы, профили,\nвременной ряд, результат"),
    "doc": (1040, 785, 300, 70, "Отчёт и защита\nИсходники + скриншоты"),
}
EDGES = [
    ("nasa", "history"), ("meteo", "history"), ("owm", "current"),
    ("history", "norms"), ("norms", "fuzzy"), ("expert", "fuzzy"),
    ("current", "fuzzy"), ("current", "anomaly"), ("norms", "anomaly"),
    ("fuzzy", "result"), ("anomaly", "result"),
    ("result", "table"), ("result", "plots"), ("result", "doc"),
]


def anchors(a, b):
    x, y, w, h, _ = NODES[a]
    X, Y, W, H, _ = NODES[b]
    if b == "anomaly" and a == "norms":
        return (x+w/2, y+h), (X, Y+H/2)
    if abs((x+w/2)-(X+W/2)) > 300 and abs(y-Y) < 170:
        return ((x+w, y+h/2), (X, Y+H/2)) if x<X else ((x, y+h/2), (X+W, Y+H/2))
    return (x+w/2, y+h), (X+W/2, Y)


def create(folder=ROOT):
    folder = Path(folder)
    root = ET.Element("mxfile", host="app.diagrams.net")
    diagram = ET.SubElement(root, "diagram", name="Архитектура лабораторной №3")
    model = ET.SubElement(diagram, "mxGraphModel", page="1", pageWidth="1400", pageHeight="900")
    graph = ET.SubElement(model, "root")
    ET.SubElement(graph, "mxCell", id="0")
    ET.SubElement(graph, "mxCell", id="1", parent="0")
    fig, ax = plt.subplots(figsize=(14, 9), layout="constrained")
    ax.set_xlim(0, 1400)
    ax.set_ylim(900, 0)
    ax.axis("off")
    for node, (x, y, w, h, text) in NODES.items():
        cell = ET.SubElement(graph, "mxCell", id=node, value=text, vertex="1", parent="1",
                             style="rounded=1;whiteSpace=wrap;html=0;fillColor=#F7F6F2;strokeColor=#01696F;fontSize=17;")
        ET.SubElement(cell, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h),
                      attrib={"as": "geometry"})
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0,rounding_size=8",
                                   facecolor="#F7F6F2",edgecolor="#01696F"))
        ax.text(x+w/2,y+h/2,text,ha="center",va="center",fontsize=11)
    for i, (a, b) in enumerate(EDGES):
        edge = ET.SubElement(graph, "mxCell", id=f"e{i}", edge="1", parent="1",
                             source=a, target=b, style="edgeStyle=orthogonalEdgeStyle;endArrow=block;")
        ET.SubElement(edge, "mxGeometry", relative="1", attrib={"as": "geometry"})
        start, end = anchors(a, b)
        if (a,b) == ("norms","anomaly"):
            points = [start, (start[0], 580), (1010,580), (1010,end[1]), end]
            for p,q in zip(points[:-2],points[1:-1]):
                ax.plot([p[0],q[0]],[p[1],q[1]],color="#555",lw=1)
            ax.add_patch(FancyArrowPatch(points[-2],points[-1],arrowstyle="-|>",
                                        mutation_scale=12,color="#555"))
        else:
            ax.add_patch(FancyArrowPatch(start,end,arrowstyle="-|>",mutation_scale=12,
                                        color="#555",linestyle="--" if a=="meteo" else "-"))
    fig.savefig(folder/"architecture.png",dpi=170,bbox_inches="tight")
    plt.close(fig)
    ET.ElementTree(root).write(folder/"architecture.drawio",encoding="utf-8",xml_declaration=True)


if __name__ == "__main__":
    create()
