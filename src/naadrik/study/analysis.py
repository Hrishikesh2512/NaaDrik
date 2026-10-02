"""Summarise study results: accuracy per axis and overall, against chance, with charts."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import stats

from naadrik.errors import NaadrikError
from naadrik.stimuli import AXES, OPTIONS
from naadrik.study.records import TrialRecord, read_trials

PHASE_ORDER = ("baseline", "training", "test")
CONDITION_LABELS = {"naadrik": "Naadrik", "voice": "vOICe-style baseline"}
OVERALL = "all four"

# Chart styling: the first two categorical slots of a CVD-validated palette, on a light surface.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e4e3df"
SERIES = {"naadrik": "#2a78d6", "voice": "#eb6834"}
HATCH = {"naadrik": "", "voice": "////"}


@dataclass(frozen=True)
class AxisResult:
    correct: int
    n: int
    chance: float
    ci_low: float
    ci_high: float
    p_value: float

    @property
    def accuracy(self) -> float:
        return self.correct / self.n if self.n else float("nan")


@dataclass(frozen=True)
class GroupSummary:
    condition: str
    phase: str
    axes: dict[str, AxisResult]
    mean_rt_s: float
    participants: int


def wilson_interval(correct: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = correct / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def holm_adjust(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, in the original order."""
    order = np.argsort(p_values)
    m = len(p_values)
    adjusted = np.empty(m)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted.tolist()


def chance_levels(colour_count: int) -> dict[str, float]:
    levels = {axis: 1.0 / len(OPTIONS[axis]) for axis in AXES if axis != "colour"}
    levels["colour"] = 1.0 / colour_count
    levels[OVERALL] = float(np.prod(list(levels.values())))
    return levels


def axis_result(flags: list[bool], chance: float) -> AxisResult:
    correct, n = int(sum(flags)), len(flags)
    low, high = wilson_interval(correct, n)
    p_value = stats.binomtest(correct, n, chance, alternative="greater").pvalue if n else 1.0
    return AxisResult(correct, n, chance, low, high, float(p_value))


@dataclass
class StudyResults:
    records: list[TrialRecord]
    sessions: list[dict]

    @classmethod
    def load(cls, paths: list[Path]) -> StudyResults:
        csvs: list[Path] = []
        for path in paths:
            if path.is_dir():
                csvs.extend(sorted(path.glob("*.csv")))
            elif path.suffix == ".csv":
                csvs.append(path)
        if not csvs:
            raise NaadrikError(f"No result CSV files found in {', '.join(map(str, paths))}.")
        records: list[TrialRecord] = []
        sessions: list[dict] = []
        for csv_path in csvs:
            records.extend(read_trials(csv_path))
            json_path = csv_path.with_suffix(".json")
            if json_path.is_file():
                sessions.append(json.loads(json_path.read_text(encoding="utf-8")))
        if not records:
            raise NaadrikError("The result files contain no trials.")
        return cls(records, sessions)

    @property
    def conditions(self) -> list[str]:
        return [c for c in CONDITION_LABELS if any(r.condition == c for r in self.records)]

    def colour_count(self) -> int:
        counts = {len(s["colours"]) for s in self.sessions if "colours" in s}
        if len(counts) == 1:
            return counts.pop()
        return len({r.colour for r in self.records})

    def summaries(self) -> list[GroupSummary]:
        chance = chance_levels(self.colour_count())
        groups: dict[tuple[str, str], list[TrialRecord]] = defaultdict(list)
        for record in self.records:
            groups[(record.condition, record.phase)].append(record)
        result = []
        for condition in self.conditions:
            for phase in PHASE_ORDER:
                trials = groups.get((condition, phase))
                if not trials:
                    continue
                axes = {
                    axis: axis_result([t.correct(axis) for t in trials], chance[axis])
                    for axis in AXES
                }
                axes[OVERALL] = axis_result([t.all_correct for t in trials], chance[OVERALL])
                result.append(
                    GroupSummary(
                        condition,
                        phase,
                        axes,
                        float(np.mean([t.rt_total_s for t in trials])),
                        len({t.participant for t in trials}),
                    )
                )
        return result

    def training_minutes(self) -> dict[str, float]:
        """Mean training-phase duration per condition, from the session files."""
        durations: dict[str, list[float]] = defaultdict(list)
        for session in self.sessions:
            training = session.get("phases", {}).get("training")
            if training:
                durations[session["condition"]].append(training["duration_s"] / 60.0)
        return {condition: float(np.mean(values)) for condition, values in durations.items()}


def format_report(results: StudyResults) -> str:
    summaries = results.summaries()
    chance = chance_levels(results.colour_count())
    participants = sorted({r.participant for r in results.records})
    lines = [
        "# Naadrik study results",
        "",
        f"Participants: {', '.join(participants)} ({len(results.records)} trials in total).",
    ]
    if any(p.startswith("sim-") for p in participants):
        lines += ["", "**Includes simulated participants (`sim-`): not human data.**"]
    lines += [
        "",
        "Accuracy with 95% Wilson intervals. *p* is a one-sided binomial test against chance;",
        "*p (Holm)* corrects for testing every row of this table.",
        "",
        "| Condition | Phase | Axis | Accuracy | 95% CI | Chance | p | p (Holm) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    rows = [
        (summary, axis, result) for summary in summaries for axis, result in summary.axes.items()
    ]
    adjusted = holm_adjust([result.p_value for _, _, result in rows])
    for (summary, axis, result), p_holm in zip(rows, adjusted, strict=True):
        lines.append(
            f"| {CONDITION_LABELS[summary.condition]} | {summary.phase} | {axis} | "
            f"{result.accuracy:.0%} ({result.correct}/{result.n}) | "
            f"{result.ci_low:.0%} to {result.ci_high:.0%} | {result.chance:.0%} | "
            f"{_format_p(result.p_value)} | {_format_p(p_holm)} |"
        )
    lines += [
        "",
        "| Condition | Phase | Mean axis accuracy | Mean response time |",
        "|---|---|---|---|",
    ]
    for summary in summaries:
        mean_axis = np.mean([summary.axes[axis].accuracy for axis in AXES])
        lines.append(
            f"| {CONDITION_LABELS[summary.condition]} | {summary.phase} | {mean_axis:.0%} | "
            f"{summary.mean_rt_s:.1f} s |"
        )
    training = results.training_minutes()
    if training:
        lines += ["", "Training time (mean per participant):", ""]
        lines += [f"- {CONDITION_LABELS[c]}: {m:.1f} min" for c, m in training.items()]
    lines += [
        "",
        "Chance levels: "
        + ", ".join(f"{axis} {level:.1%}" for axis, level in chance.items())
        + ".",
    ]
    return "\n".join(lines) + "\n"


def _format_p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def _style_axes(ax) -> None:  # type: ignore[no-untyped-def]
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_SECONDARY, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def plot_accuracy(results: StudyResults, phase: str, path: Path) -> Path | None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    summaries = [s for s in results.summaries() if s.phase == phase]
    if not summaries:
        return None
    labels = [*AXES, OVERALL]
    x = np.arange(len(labels))
    width = 0.8 / len(summaries)
    fig, ax = plt.subplots(figsize=(8, 4.2), facecolor=SURFACE)
    _style_axes(ax)
    for i, summary in enumerate(summaries):
        acc = np.array([summary.axes[a].accuracy for a in labels])
        low = np.maximum(acc - np.array([summary.axes[a].ci_low for a in labels]), 0.0)
        high = np.maximum(np.array([summary.axes[a].ci_high for a in labels]) - acc, 0.0)
        offset = (i - (len(summaries) - 1) / 2) * width
        ax.bar(
            x + offset,
            acc,
            width * 0.92,
            color=SERIES[summary.condition],
            hatch=HATCH[summary.condition],
            edgecolor=SURFACE,
            linewidth=0,
            label=CONDITION_LABELS[summary.condition],
        )
        ax.errorbar(
            x + offset, acc, yerr=[low, high], fmt="none", ecolor=INK_SECONDARY, lw=1, capsize=3
        )
        # Label above the whisker so the number never sits on the interval line.
        for xi, value, top in zip(x + offset, acc, acc + high, strict=True):
            ax.text(
                xi, top + 0.015, f"{value:.0%}", ha="center", va="bottom", fontsize=8, color=INK
            )
    chance = summaries[0].axes
    for xi, label in zip(x, labels, strict=True):
        ax.hlines(
            chance[label].chance,
            xi - 0.45,
            xi + 0.45,
            colors=INK_SECONDARY,
            linestyles="--",
            lw=1.2,
        )
    ax.text(
        x[-1] + 0.47,
        chance[labels[-1]].chance,
        " chance",
        va="center",
        fontsize=8,
        color=INK_SECONDARY,
    )
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1.14)
    ax.set_yticks(np.linspace(0, 1, 6), [f"{v:.0%}" for v in np.linspace(0, 1, 6)])
    ax.set_ylabel("Accuracy", color=INK_SECONDARY)
    ax.set_title(
        f"Accuracy per axis, {phase} phase (95% CI; dashed = chance)",
        color=INK,
        fontsize=11,
        loc="left",
    )
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return path


def plot_learning_curve(results: StudyResults, path: Path, window: int = 9) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 3.8), facecolor=SURFACE)
    _style_axes(ax)
    boundaries: list[tuple[int, str]] = []
    ends: list[tuple[int, float, str]] = []
    for condition in results.conditions:
        trials = sorted(
            (r for r in results.records if r.condition == condition),
            key=lambda r: (r.participant, PHASE_ORDER.index(r.phase), r.trial),
        )
        # Average over participants at each position in the protocol.
        by_position: dict[int, list[float]] = defaultdict(list)
        position_phase: dict[int, str] = {}
        counters: dict[str, int] = defaultdict(int)
        for record in trials:
            position = counters[record.participant]
            counters[record.participant] += 1
            by_position[position].append(np.mean([record.correct(a) for a in AXES]))
            position_phase[position] = record.phase
        positions = sorted(by_position)
        scores = np.array([np.mean(by_position[p]) for p in positions])
        kernel = np.ones(min(window, len(scores))) / min(window, len(scores))
        smooth = np.convolve(scores, kernel, mode="valid")
        start = (len(scores) - len(smooth)) // 2
        xs = np.array(positions[start : start + len(smooth)]) + 1
        ax.plot(xs, smooth, color=SERIES[condition], lw=2, label=CONDITION_LABELS[condition])
        ends.append((int(xs[-1]), float(smooth[-1]), condition))
        if not boundaries:
            previous = None
            for p in positions:
                if position_phase[p] != previous:
                    boundaries.append((p + 1, position_phase[p]))
                    previous = position_phase[p]
    for x_end, y_end, condition in _spread_labels(ends, min_gap=0.06):
        ax.text(x_end + 0.6, y_end, CONDITION_LABELS[condition], color=INK, fontsize=8, va="center")
    for x_start, phase in boundaries:
        ax.axvline(x_start - 0.5, color=GRID, lw=1)
        ax.text(x_start, 1.02, phase, fontsize=8, color=INK_SECONDARY, va="bottom")
    chance_axis = np.mean(
        [v for k, v in chance_levels(results.colour_count()).items() if k in AXES]
    )
    ax.axhline(chance_axis, color=INK_SECONDARY, ls="--", lw=1.2)
    ax.text(1, chance_axis + 0.02, "chance", fontsize=8, color=INK_SECONDARY)
    ax.set_ylim(0, 1.1)
    ax.set_yticks(np.linspace(0, 1, 6), [f"{v:.0%}" for v in np.linspace(0, 1, 6)])
    ax.set_xlabel("Trial (all phases, in order)", color=INK_SECONDARY)
    ax.set_ylabel(f"Mean axis accuracy\n(rolling {window})", color=INK_SECONDARY)
    ax.legend(
        frameon=False,
        fontsize=9,
        labelcolor=INK,
        ncol=2,
        loc="lower left",
        bbox_to_anchor=(0, 1.06),
    )
    if ends:
        ax.set_xlim(0, max(x_end for x_end, _, _ in ends) * 1.2)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return path


def _spread_labels(
    ends: list[tuple[int, float, str]], min_gap: float
) -> list[tuple[int, float, str]]:
    """Nudge end-of-line labels apart vertically so they never overlap."""
    placed: list[tuple[int, float, str]] = []
    for x_end, y_end, condition in sorted(ends, key=lambda item: item[1]):
        if placed and y_end - placed[-1][1] < min_gap:
            y_end = placed[-1][1] + min_gap
        placed.append((x_end, y_end, condition))
    return placed


def analyse(paths: list[Path], out_dir: Path) -> tuple[Path, list[Path]]:
    results = StudyResults.load(paths)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "report.md"
    charts = [
        chart
        for chart in (
            plot_accuracy(results, "test", out_dir / "accuracy_test.png"),
            plot_accuracy(results, "baseline", out_dir / "accuracy_baseline.png"),
            plot_learning_curve(results, out_dir / "learning_curve.png"),
        )
        if chart is not None
    ]
    body = format_report(results)
    body += "\n" + "\n".join(f"![{c.stem}]({c.name})" for c in charts) + "\n"
    report.write_text(body, encoding="utf-8")
    return report, charts
