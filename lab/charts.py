"""Графіки для звіту з results/bench_S.json і bench_L.json.   python -m lab.charts"""
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .common import ROOT

RES = os.path.join(ROOT, "results")
OUT = os.path.join(RES, "charts")
INK, MUTED, GRID = "#1f1f1e", "#6b6a63", "#e4e3dd"
C_MONGO, C_PG = "#2a78d6", "#eb6834"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
                     "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": INK,
                     "axes.spines.top": False, "axes.spines.right": False})

NAMES = {
    "R1_full_course": "R1 Відкрити курс цілком",
    "R3_single_quiz": "R3 Відкрити один тест",
    "W1_create_course": "W1 Створити курс",
    "W2_update_question": "W2 Змінити 1 питання",
    "W4_insert_attempt": "W4 Записати спробу тесту",
    "W5_rename_teacher": "W5 Змінити ПІБ викладача",
    "A1_tag_search": "A1 Пошук за тегом",
    "A2_dept_report": "A2 Звіт по кафедрах",
}


def best(impl, prefix):
    return min(v["p50"] for k, v in impl.items() if k.startswith(prefix))


def ratios(data):
    out = []
    for key, name in NAMES.items():
        impl = data[key]["impl"]
        m, p = best(impl, "MongoDB"), best(impl, "PostgreSQL")
        out.append((name, m, p, p / m))
    return out


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(os.path.join(OUT, name), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def chart_ratio(S, L):
    rl, rs = ratios(L), ratios(S)
    fig, ax = plt.subplots(figsize=(9, 4.4))
    ys = list(range(len(rl)))[::-1]
    for y, (name, m, p, r), s in zip(ys, rl, rs):
        x, xs = math.log10(r), math.log10(s[3])
        ax.barh(y, x, color=C_MONGO if r > 1 else C_PG, height=0.6)
        ax.plot([xs], [y], marker="o", ms=5, mfc="white", mec=INK)
        edge = max(x, xs) if x >= 0 else min(x, xs)
        lab = f"MongoDB ×{r:.1f}" if r > 1 else f"PostgreSQL ×{1 / r:.1f}"
        ax.text(edge + (0.05 if x >= 0 else -0.05), y, lab, va="center",
                ha="left" if x >= 0 else "right", fontsize=9, color=INK)
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_yticks(ys, [r[0] for r in rl])
    ax.set_xticks([-1, -0.5, 0, 0.5, 1], ["PG ×10", "PG ×3", "однаково", "Mongo ×3", "Mongo ×10"])
    ax.set_xlim(-1.4, 1.4)
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.set_title("У скільки разів швидше (медіана; смуга — 20 000 курсів, кружок — 2 000)\n"
                 "синє — швидша MongoDB, помаранчеве — швидший PostgreSQL",
                 loc="left", color=INK, fontsize=10.5)
    save(fig, "ratio_overview.png")


def chart_storage(L):
    st = L["S1_storage"]
    mb = lambda b: b / 1024 / 1024
    rows = [("Курси: MongoDB", st["course"]["mongo_data"], st["course"]["mongo_index"], C_MONGO),
            ("Курси: PostgreSQL (12 таблиць)", st["course"]["pg_data"], st["course"]["pg_index"], C_PG),
            ("Спроби: MongoDB", st["attempts"]["mongo_data"], st["attempts"]["mongo_index"], C_MONGO),
            ("Спроби: PostgreSQL (3 таблиці)", st["attempts"]["pg_data"], st["attempts"]["pg_index"], C_PG)]
    fig, ax = plt.subplots(figsize=(9, 2.8))
    ys = list(range(len(rows)))[::-1]
    for y, (n, d, i, c) in zip(ys, rows):
        ax.barh(y, mb(d), color=c, height=0.6)
        ax.barh(y, mb(i), left=mb(d) + 2, color=c, alpha=0.4, height=0.6)
        ax.text(mb(d) + mb(i) + 8, y, f"{mb(d):.0f} + {mb(i):.0f} МБ", va="center", fontsize=9, color=INK)
    ax.set_yticks(ys, [r[0] for r in rows])
    ax.set_xlabel("МБ на диску (яскраве — дані, бліде — індекси)")
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.set_title("Скільки місця займають дані (20 000 курсів)", loc="left", color=INK, fontsize=11)
    save(fig, "storage.png")


def main():
    S = json.load(open(os.path.join(RES, "bench_S.json"), encoding="utf-8"))
    L = json.load(open(os.path.join(RES, "bench_L.json"), encoding="utf-8"))
    chart_ratio(S, L)
    chart_storage(L)
    for scale, d in (("S", S), ("L", L)):
        print(f"\n== {scale}")
        for name, m, p, r in ratios(d):
            print(f"{name:30s} mongo={m:9.3f}  pg={p:9.3f}  x{r:.2f}")


if __name__ == "__main__":
    main()
