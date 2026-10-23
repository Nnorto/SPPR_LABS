"""Статические графики на основе расчётов, без сетевых обращений."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from settings import CITIES, SEASONS, SEASON_NAMES
from fuzzy_model import TERM_RU

COLORS = ["#20808D", "#A84B2F", "#1B474D", "#944454", "#848456"]
LINESTYLES = ["-", "--", "-.", ":", (0, (5, 1))]


def configure():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": .18, "figure.dpi": 140,
        "savefig.facecolor": "white",
    })


def save(fig, path):
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_history(frame, norms, folder, provider):
    configure()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.6), layout="constrained")
    for ax, (metric, label) in zip(axes, [("temperature", "Температура, °C"),
                                        ("humidity", "Влажность, %"), ("wind", "Ветер, м/с")]):
        for i, (city, info) in enumerate(CITIES.items()):
            sub = norms[norms.city == city].set_index("season").loc[SEASONS]
            ax.plot(range(4), sub[metric + "_mean"], marker=["o", "s", "^"][i],
                    color=COLORS[i], linestyle=LINESTYLES[i], label=info["name"])
        ax.set_xticks(range(4), [SEASON_NAMES[s] for s in SEASONS], rotation=25)
        ax.set_ylabel(label)
    axes[0].legend(fontsize=9)
    fig.suptitle(f"Сезонные средние за 2021–2025 годы\n{provider}; учебная пятилетняя база",
                 fontsize=13)
    save(fig, folder / "seasonal_profiles.png")
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, layout="constrained")
    for ax, (city, info), color in zip(axes, CITIES.items(), COLORS):
        daily = frame[frame.city == city].set_index("time")["temperature"].resample("D").mean()
        smooth = daily.rolling(30, min_periods=30).mean()
        ax.plot(daily.index, daily, color="#a8adad", lw=.5, label="Среднее за сутки")
        ax.plot(smooth.index, smooth, color=color, lw=1.5, label="Среднее за 30 суток")
        ax.set_title(info["name"], loc="left")
        ax.set_ylabel("°C")
        ax.legend(loc="upper right", fontsize=9)
    fig.suptitle("Сезонные колебания температуры, 2021–2025\nСглаживание не доказывает долгосрочный климатический тренд",
                 fontsize=13)
    save(fig, folder / "temperature_trends.png")


def plot_memberships(model, folder):
    configure()
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.3), layout="constrained")
    labels = {"temperature": "Температура, °C", "humidity": "Влажность, %",
              "wind": "Ветер, м/с", "comfort": "Условный комфорт, 0–100"}
    for ax, (name, var) in zip(axes.flat, model.variables.items()):
        for i, (term, obj) in enumerate(var.terms.items()):
            label = {"far_below": "намного ниже", "below": "ниже", "typical": "типично",
                     "above": "выше", "far_above": "намного выше"}.get(term, TERM_RU[term])
            ax.plot(var.universe, obj.mf, color=COLORS[i], linestyle=LINESTYLES[i],
                    label=label, lw=1.8)
        ax.set_xlabel(labels[name])
        ax.set_ylabel("Степень принадлежности μ")
        ax.set_ylim(-.03, 1.08)
        if name == "temperature":
            ax.set_xlim(max(-60, model.mean-3*model.scale), min(60, model.mean+3*model.scale))
        if name == "wind":
            ax.set_xlim(0, 25)
        ax.legend(fontsize=8, loc="upper right")
    fig.suptitle(
        f"{CITIES[model.city]['name']}: {SEASON_NAMES[model.season].lower()}\n"
        f"Температурные термы: среднее {model.mean:.2f} °C; масштаб {model.scale:.2f} °C",
        fontsize=13)
    save(fig, Path(folder) / f"membership_{model.city}.png")


def plot_results(results, folder, mode):
    configure()
    fig, ax = plt.subplots(figsize=(9, 4.8), layout="constrained")
    names = [CITIES[r["city"]]["name"] for r in results]
    values = [r["fuzzy"]["comfort"] for r in results]
    bars = ax.barh(names, values, color=COLORS[:len(names)], height=.5)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Условный индекс комфорта (не медицинский показатель)")
    for bar, val in zip(bars, values):
        ax.text(min(val + 2, 93), bar.get_y()+bar.get_height()/2, f"{val:.1f}",
                va="center", fontsize=12)
    tag = "Сохранённые ответы OpenWeatherMap" if mode == "cached" else "Исторический пример, НЕ текущая погода"
    fig.suptitle(f"Результат нечёткого вывода Мамдани\n{tag}", fontsize=13)
    save(fig, Path(folder) / "comfort_comparison.png")
