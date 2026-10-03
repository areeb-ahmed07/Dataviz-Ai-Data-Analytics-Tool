"""Compare clustering algorithms with metrics computed on non-noise rows."""
import time
import numpy as np
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
from ml.services.model_registry import get_model_zoo


def compare_clusters(X, config, progress=None):
    options = config.experiment_config or {}
    n_clusters = int(options.get('n_clusters', 3))
    if not 2 <= n_clusters < len(X):
        raise ValueError('Number of clusters must be at least 2 and smaller than the number of rows.')
    models = get_model_zoo('clustering', random_state=config.random_state)
    if not config.auto_mode and config.selected_algorithms:
        models = {k: v for k, v in models.items() if k in config.selected_algorithms}
    if not models:
        raise ValueError('Select at least one available clustering model.')
    results = {}
    for name, model in models.items():
        if progress:
            progress(len(results), len(models), name)
        start = time.perf_counter()
        try:
            params = model.get_params()
            if 'n_clusters' in params:
                model.set_params(n_clusters=n_clusters)
            if name == 'DBSCAN':
                model.set_params(eps=float(options.get('dbscan_eps', .5)), min_samples=int(options.get('dbscan_min_samples', 5)))
            if name == 'Agglomerative':
                model.set_params(linkage=options.get('linkage', 'ward'))
            labels = model.fit_predict(X)
            assigned = labels != -1
            groups = np.unique(labels[assigned])
            metrics = dict(silhouette=None, calinski_harabasz=None, davies_bouldin=None)
            if 1 < len(groups) < int(assigned.sum()):
                data, lab = X[assigned], labels[assigned]
                metrics = {
                    'silhouette': float(silhouette_score(data, lab, sample_size=min(2000, len(data)), random_state=config.random_state)),
                    'calinski_harabasz': float(calinski_harabasz_score(data, lab)),
                    'davies_bouldin': float(davies_bouldin_score(data, lab)),
                }
            results[name] = {'valid': True, 'algorithm': name, 'n_clusters': len(groups),
                             'noise_points': int((~assigned).sum()), 'labels': labels.tolist(),
                             'cluster_sizes': [int((labels == g).sum()) for g in groups],
                             'fit_time': round(time.perf_counter() - start, 4), **metrics}
        except Exception as exc:
            results[name] = {'valid': False, 'error': str(exc)}
    if progress:
        progress(len(results), len(models), None)
    ranked = sorted([(name, r) for name, r in results.items() if r['valid']],
                    key=lambda pair: pair[1]['silhouette'] if pair[1]['silhouette'] is not None else -2,
                    reverse=True)
    leaderboard = [{'rank': i + 1, 'model_name': name, 'primary_metric': 'silhouette',
                    'primary_score': r['silhouette'], 'cv_mean': None, 'cv_std': None,
                    'fit_time': r['fit_time'],
                    'metrics': {k: r[k] for k in ('silhouette', 'calinski_harabasz', 'davies_bouldin', 'n_clusters', 'noise_points')}}
                   for i, (name, r) in enumerate(ranked)]
    best = next((name for name, r in ranked if r['silhouette'] is not None), None)
    return results, leaderboard, best
