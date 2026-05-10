"""
Customer segmentation via KMeans clustering.

Pipeline:
    1. Load scaled features from artifacts/
    2. Run elbow method (k=2..12) to find diminishing-returns elbow
    3. Run silhouette analysis on top candidates
    4. Fit final model with chosen k
    5. Profile each cluster (avg feature values, dominant personas)
    6. Save model + cluster assignments + cluster profiles

Why KMeans for this problem:
    - Customer segmentation is a classical use case
    - Interpretable cluster centroids (we can describe each segment)
    - Fast to retrain nightly when new data arrives
    - Industry standard at every bank/fintech

Run from project root:
    python -m ml.segmentation
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

# Range of k values to evaluate
K_MIN = 2
K_MAX = 12

# Final k chosen after analysis (this script will recommend, but we lock it for reproducibility)
# We'll auto-select if below threshold, otherwise use this default
DEFAULT_K = 6

# Reproducibility
RANDOM_STATE = 42


def load_artifacts():
    """Load the feature matrix and metadata produced by features.py"""
    X = np.load(ARTIFACTS_DIR / "X_scaled.npy")
    meta = pd.read_parquet(ARTIFACTS_DIR / "customer_meta.parquet")
    with open(ARTIFACTS_DIR / "feature_names.txt") as f:
        feature_names = [line.strip() for line in f if line.strip()]
    print(f"Loaded artifacts: X{X.shape}, meta{meta.shape}, {len(feature_names)} features")
    return X, meta, feature_names


def run_elbow_method(X: np.ndarray) -> dict:
    """
    Compute inertia for k in [K_MIN, K_MAX].
    Inertia = sum of squared distances to nearest centroid.
    The 'elbow' is where adding more clusters stops reducing inertia much.
    """
    print(f"\n=== Elbow method (k={K_MIN}..{K_MAX}) ===")
    results = {}
    for k in range(K_MIN, K_MAX + 1):
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10)
        km.fit(X)
        results[k] = km.inertia_
        print(f"  k={k:2d}  inertia={km.inertia_:>10.1f}")
    return results


def run_silhouette_analysis(X: np.ndarray, k_range: range) -> dict:
    """
    Silhouette score: -1 to +1, higher is better.
    Measures how well each point fits its cluster vs other clusters.
    """
    print(f"\n=== Silhouette analysis ===")
    results = {}
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10)
        labels = km.fit_predict(X)
        score = silhouette_score(X, labels)
        results[k] = score
        print(f"  k={k:2d}  silhouette={score:.4f}")
    return results


def recommend_k(elbow: dict, silhouette: dict) -> int:
    """
    Heuristic to pick a good k:
    - Take the k with the highest silhouette score in our top candidate range (3-8)
    - Cluster sizes for very large k tend to be too small to be actionable
    """
    candidates = {k: s for k, s in silhouette.items() if 3 <= k <= 8}
    best_k = max(candidates, key=candidates.get)
    print(f"\n→ Recommended k = {best_k} (highest silhouette in 3-8 range)")
    return best_k


def fit_final_model(X: np.ndarray, k: int) -> KMeans:
    print(f"\n=== Fitting final model (k={k}) ===")
    km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=20)
    km.fit(X)
    print(f"  Inertia:    {km.inertia_:.1f}")
    print(f"  Silhouette: {silhouette_score(X, km.labels_):.4f}")
    print(f"  Iterations: {km.n_iter_}")
    return km


def profile_clusters(km: KMeans, X: np.ndarray, meta: pd.DataFrame, feature_names: list) -> pd.DataFrame:
    """
    Build per-cluster summary:
    - Cluster size
    - Top 3 personas in cluster
    - Average values for the most distinguishing features
    """
    print(f"\n=== Cluster profiles ===")

    meta = meta.copy()
    meta["cluster"] = km.labels_

    # Cluster sizes
    sizes = meta["cluster"].value_counts().sort_index()

    # Top personas per cluster
    persona_distribution = (
        meta.groupby(["cluster", "persona_name"])
            .size()
            .unstack(fill_value=0)
    )

    # For each cluster, find the persona that's most over-represented vs population
    population_persona_pct = meta["persona_name"].value_counts(normalize=True)

    rows = []
    for cluster_id in sorted(meta["cluster"].unique()):
        cluster_meta = meta[meta["cluster"] == cluster_id]
        cluster_size = len(cluster_meta)

        # Top 3 personas by raw count
        top_personas = cluster_meta["persona_name"].value_counts().head(3)

        # Top persona by over-indexing (lift)
        cluster_persona_pct = cluster_meta["persona_name"].value_counts(normalize=True)
        lift = (cluster_persona_pct / population_persona_pct).dropna()
        signature_persona = lift.idxmax() if len(lift) else "—"
        signature_lift = lift.max() if len(lift) else 0

        rows.append({
            "cluster": cluster_id,
            "size": cluster_size,
            "size_pct": round(cluster_size / len(meta) * 100, 1),
            "signature_persona": signature_persona,
            "signature_lift": round(signature_lift, 2),
            "top_persona_1": top_personas.index[0] if len(top_personas) > 0 else "—",
            "top_persona_1_n": int(top_personas.iloc[0]) if len(top_personas) > 0 else 0,
            "top_persona_2": top_personas.index[1] if len(top_personas) > 1 else "—",
            "top_persona_2_n": int(top_personas.iloc[1]) if len(top_personas) > 1 else 0,
            "top_persona_3": top_personas.index[2] if len(top_personas) > 2 else "—",
            "top_persona_3_n": int(top_personas.iloc[2]) if len(top_personas) > 2 else 0,
        })

    profiles = pd.DataFrame(rows)
    print(profiles.to_string(index=False))
    return profiles, meta


def feature_importance_per_cluster(km: KMeans, feature_names: list, top_n: int = 5) -> pd.DataFrame:
    """
    For each cluster, find which (scaled) features are most distinctive.
    Centroid coords are in scaled space; features with large absolute values
    (positive or negative) define what makes that cluster unique.
    """
    print(f"\n=== Top {top_n} distinguishing features per cluster ===")
    centroids = km.cluster_centers_  # (k, n_features)

    rows = []
    for cluster_id, center in enumerate(centroids):
        # Sort by absolute distance from population mean (which is ~0 in scaled space)
        feature_signal = sorted(
            zip(feature_names, center),
            key=lambda x: abs(x[1]),
            reverse=True
        )[:top_n]
        for rank, (feat, val) in enumerate(feature_signal, 1):
            direction = "↑ HIGH" if val > 0 else "↓ LOW"
            rows.append({
                "cluster": cluster_id,
                "rank": rank,
                "feature": feat,
                "z_score": round(val, 2),
                "direction": direction,
            })

    feat_df = pd.DataFrame(rows)
    for cluster_id in feat_df["cluster"].unique():
        print(f"\nCluster {cluster_id}:")
        cluster_feats = feat_df[feat_df["cluster"] == cluster_id]
        for _, row in cluster_feats.iterrows():
            print(f"  {row['rank']}. {row['feature']:<30} {row['direction']:<8} (z={row['z_score']:+.2f})")
    return feat_df


def main():
    X, meta, feature_names = load_artifacts()

    # Phase 1: explore k
    elbow = run_elbow_method(X)
    silhouette = run_silhouette_analysis(X, range(K_MIN, K_MAX + 1))
    chosen_k = recommend_k(elbow, silhouette)

    # Phase 2: final model
    km = fit_final_model(X, chosen_k)

    # Phase 3: interpretation
    profiles, meta_with_clusters = profile_clusters(km, X, meta, feature_names)
    feat_importance = feature_importance_per_cluster(km, feature_names)

    # Save everything
    joblib.dump(km, ARTIFACTS_DIR / "kmeans_model.joblib")
    profiles.to_parquet(ARTIFACTS_DIR / "cluster_profiles.parquet", index=False)
    feat_importance.to_parquet(ARTIFACTS_DIR / "cluster_feature_importance.parquet", index=False)
    meta_with_clusters.to_parquet(ARTIFACTS_DIR / "customer_clusters.parquet", index=False)

    # Save the metric scans for the visualization step
    pd.DataFrame({"k": list(elbow.keys()), "inertia": list(elbow.values())}) \
        .to_parquet(ARTIFACTS_DIR / "elbow_scan.parquet", index=False)
    pd.DataFrame({"k": list(silhouette.keys()), "silhouette": list(silhouette.values())}) \
        .to_parquet(ARTIFACTS_DIR / "silhouette_scan.parquet", index=False)

    print(f"\n✓ Saved to {ARTIFACTS_DIR}/")
    print(f"  - kmeans_model.joblib              (k={chosen_k})")
    print(f"  - customer_clusters.parquet        (903 rows w/ cluster id)")
    print(f"  - cluster_profiles.parquet         ({chosen_k} rows)")
    print(f"  - cluster_feature_importance.parquet")
    print(f"  - elbow_scan.parquet, silhouette_scan.parquet")


if __name__ == "__main__":
    main()
