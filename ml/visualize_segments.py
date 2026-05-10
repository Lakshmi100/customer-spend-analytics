"""
Generate portfolio-quality visualizations of the segmentation results.

Produces 4 PNG charts in ml/artifacts/:
    1. elbow_plot.png            — inertia vs k (justifies k choice)
    2. silhouette_plot.png       — silhouette vs k (validates k choice)
    3. cluster_persona_heatmap.png — confusion matrix of personas vs clusters
    4. cluster_feature_heatmap.png — what makes each cluster distinctive

These go DIRECTLY into your portfolio README. The cluster-persona heatmap
in particular is the "money shot" — it visually proves the clustering
recovered meaningful customer segments.

Run from project root:
    python -m ml.visualize_segments
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)

# Consistent style for portfolio look
sns.set_style("whitegrid")
plt.rcParams["figure.dpi"] = 110
plt.rcParams["savefig.dpi"] = 150
plt.rcParams["axes.titlesize"] = 14
plt.rcParams["axes.labelsize"] = 11


def plot_elbow():
    df = pd.read_parquet(ARTIFACTS_DIR / "elbow_scan.parquet")
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(df["k"], df["inertia"], marker="o", linewidth=2, markersize=8, color="#2E86AB")
    ax.set_xlabel("Number of clusters (k)")
    ax.set_ylabel("Inertia (within-cluster sum of squares)")
    ax.set_title("Elbow Method — finding the optimal number of clusters")
    ax.set_xticks(df["k"])
    ax.grid(True, alpha=0.3)

    # Annotate where the curve flattens
    inertia_decrease = -np.diff(df["inertia"].values)
    relative_drop = inertia_decrease / df["inertia"].values[:-1]
    elbow_idx = np.argmin(np.abs(relative_drop - 0.10))  # roughly where drop is ~10%
    elbow_k = df["k"].values[elbow_idx + 1]
    ax.axvline(elbow_k, color="orange", linestyle="--", alpha=0.6,
               label=f"Approximate elbow at k≈{elbow_k}")
    ax.legend()

    out = ARTIFACTS_DIR / "elbow_plot.png"
    plt.tight_layout()
    plt.savefig(out, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out.name}")


def plot_silhouette():
    df = pd.read_parquet(ARTIFACTS_DIR / "silhouette_scan.parquet")
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(df["k"], df["silhouette"], color="#A23B72", edgecolor="white", linewidth=1)

    # Highlight the max
    best_k = df.loc[df["silhouette"].idxmax(), "k"]
    best_score = df["silhouette"].max()
    for bar, k in zip(bars, df["k"]):
        if k == best_k:
            bar.set_color("#F18F01")

    ax.set_xlabel("Number of clusters (k)")
    ax.set_ylabel("Silhouette score (higher = better separation)")
    ax.set_title(f"Silhouette Analysis — optimal at k={best_k} (score={best_score:.3f})")
    ax.set_xticks(df["k"])
    ax.set_ylim(0, max(df["silhouette"]) * 1.2)
    ax.grid(axis="y", alpha=0.3)

    # Add value labels on bars
    for bar, score in zip(bars, df["silhouette"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.005,
                f"{score:.3f}", ha="center", fontsize=9)

    out = ARTIFACTS_DIR / "silhouette_plot.png"
    plt.tight_layout()
    plt.savefig(out, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out.name}")


def plot_persona_cluster_heatmap():
    df = pd.read_parquet(ARTIFACTS_DIR / "customer_clusters.parquet")
    crosstab = pd.crosstab(df["persona_name"], df["cluster"])

    # Convert to row-percentages so we see "what % of each persona ended up in each cluster"
    pct = crosstab.div(crosstab.sum(axis=1), axis=0) * 100

    # Sort personas by their dominant cluster (so the heatmap reads diagonally)
    pct["dominant_cluster"] = pct.idxmax(axis=1)
    pct = pct.sort_values("dominant_cluster").drop(columns="dominant_cluster")

    fig, ax = plt.subplots(figsize=(11, 9))
    sns.heatmap(
        pct, annot=True, fmt=".0f", cmap="YlOrRd",
        cbar_kws={"label": "% of persona in cluster"},
        linewidths=0.5, linecolor="white", ax=ax,
    )
    ax.set_title("Persona × Cluster mapping  (row = persona, col = cluster)\nDiagonal pattern means clusters captured persona structure")
    ax.set_xlabel("Cluster ID")
    ax.set_ylabel("Persona")

    out = ARTIFACTS_DIR / "cluster_persona_heatmap.png"
    plt.tight_layout()
    plt.savefig(out, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out.name}")


def plot_feature_heatmap():
    df = pd.read_parquet(ARTIFACTS_DIR / "cluster_feature_importance.parquet")

    # Pivot to cluster × feature with z-scores
    pivot = df.pivot(index="feature", columns="cluster", values="z_score").fillna(0)

    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(
        pivot, annot=True, fmt=".2f", cmap="RdBu_r", center=0,
        cbar_kws={"label": "Z-score (deviation from population mean)"},
        linewidths=0.5, linecolor="white", ax=ax, vmin=-3, vmax=3,
    )
    ax.set_title("Cluster Feature Signatures\n(red = above population avg, blue = below avg)")
    ax.set_xlabel("Cluster ID")
    ax.set_ylabel("Feature")

    out = ARTIFACTS_DIR / "cluster_feature_heatmap.png"
    plt.tight_layout()
    plt.savefig(out, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out.name}")


def main():
    print("Generating segmentation visualizations...")
    plot_elbow()
    plot_silhouette()
    plot_persona_cluster_heatmap()
    plot_feature_heatmap()
    print(f"\n✓ All charts saved to {ARTIFACTS_DIR}/")
    print(f"\nPortfolio tip: embed cluster_persona_heatmap.png in your README.")
    print(f"It's the most compelling visual — shows clusters captured real persona structure.")


if __name__ == "__main__":
    main()
