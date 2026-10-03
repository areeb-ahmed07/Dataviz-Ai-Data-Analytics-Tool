import numpy as np
from sklearn.linear_model import LogisticRegression, LinearRegression, Ridge, Lasso, ElasticNet
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor, ExtraTreesClassifier, ExtraTreesRegressor, GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.naive_bayes import GaussianNB
from sklearn.svm import SVC, SVR
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering, MiniBatchKMeans, Birch
from typing import Dict, Any

try:
    from xgboost import XGBClassifier, XGBRegressor
    XGBOOST_AVAILABLE = False # Temporarily disabled due to OpenMP crashes on Windows Flask
except ImportError:
    XGBOOST_AVAILABLE = False

try:
    from lightgbm import LGBMClassifier, LGBMRegressor
    LIGHTGBM_AVAILABLE = False # Temporarily disabled due to OpenMP crashes on Windows Flask
except ImportError:
    LIGHTGBM_AVAILABLE = False

def get_model_zoo(task_type: str, fast_mode: bool = False, random_state: int = 42) -> Dict[str, Any]:
    models = {}
    if task_type == 'classification':
        if fast_mode:
            models['Logistic Regression'] = LogisticRegression(max_iter=500, random_state=random_state, n_jobs=1)
            models['Random Forest'] = RandomForestClassifier(n_estimators=30, max_depth=10, random_state=random_state, n_jobs=1)
            if XGBOOST_AVAILABLE:
                models['XGBoost'] = XGBClassifier(n_estimators=30, max_depth=6, eval_metric='logloss', random_state=random_state, n_jobs=1)
        else:
            models['Logistic Regression'] = LogisticRegression(max_iter=1000, random_state=random_state, n_jobs=1)
            models['K-Nearest Neighbors'] = KNeighborsClassifier(n_jobs=1)
            models['Random Forest'] = RandomForestClassifier(n_estimators=100, random_state=random_state, n_jobs=1)
            if XGBOOST_AVAILABLE:
                models['XGBoost'] = XGBClassifier(eval_metric='logloss', random_state=random_state, n_jobs=1)
            if LIGHTGBM_AVAILABLE:
                models['LightGBM'] = LGBMClassifier(random_state=random_state, verbose=-1, n_jobs=1)
    elif task_type == 'regression':
        if fast_mode:
            models['Linear Regression'] = LinearRegression(n_jobs=1)
            models['Random Forest'] = RandomForestRegressor(n_estimators=30, max_depth=10, random_state=random_state, n_jobs=1)
            if XGBOOST_AVAILABLE:
                models['XGBoost'] = XGBRegressor(n_estimators=30, max_depth=6, random_state=random_state, n_jobs=1)
        else:
            models['Linear Regression'] = LinearRegression(n_jobs=1)
            models['K-Nearest Neighbors'] = KNeighborsRegressor(n_jobs=1)
            models['Random Forest'] = RandomForestRegressor(n_estimators=100, random_state=random_state, n_jobs=1)
            if XGBOOST_AVAILABLE:
                models['XGBoost'] = XGBRegressor(random_state=random_state, n_jobs=1)
            if LIGHTGBM_AVAILABLE:
                models['LightGBM'] = LGBMRegressor(random_state=random_state, verbose=-1, n_jobs=1)
    elif task_type == 'clustering':
        models['K-Means'] = KMeans(n_clusters=3, random_state=random_state)
        models['DBSCAN'] = DBSCAN()
        
    trees = 30 if fast_mode else 100
    if task_type == 'classification':
        models.update({
            'Decision Tree': DecisionTreeClassifier(max_depth=10, random_state=random_state),
            'Extra Trees': ExtraTreesClassifier(n_estimators=trees, random_state=random_state, n_jobs=1),
            'Gradient Boosting': GradientBoostingClassifier(n_estimators=trees, random_state=random_state),
            'Naive Bayes': GaussianNB(),
        })
        if not fast_mode:
            models['SVM'] = SVC(probability=True, random_state=random_state)
    elif task_type == 'regression':
        models.update({
            'Ridge Regression': Ridge(),
            'Decision Tree': DecisionTreeRegressor(max_depth=10, random_state=random_state),
            'Extra Trees': ExtraTreesRegressor(n_estimators=trees, random_state=random_state, n_jobs=1),
            'Gradient Boosting': GradientBoostingRegressor(n_estimators=trees, random_state=random_state),
        })
        if not fast_mode:
            models.update({'Lasso': Lasso(max_iter=3000), 'Elastic Net': ElasticNet(max_iter=3000), 'SVM': SVR()})
    elif task_type == 'clustering':
        models.update({
            'Agglomerative': AgglomerativeClustering(n_clusters=3),
            'Mini-Batch K-Means': MiniBatchKMeans(n_clusters=3, random_state=random_state, n_init=10),
            'Birch': Birch(n_clusters=3),
        })
    return models

def build_model(task_type: str, algorithm: str, params: dict, random_state: int = 42):
    # Instantiates model with params
    models = get_model_zoo(task_type, fast_mode=False, random_state=random_state)
    model = models.get(algorithm)
    # Some sklearn estimators implement ``__len__`` and raise until fitted
    # (for example GradientBoostingClassifier). Check identity rather than
    # truthiness while constructing a fresh, unfitted estimator.
    if model is not None and params:
        # Ignore unsupported params for the model gracefully
        supported_params = list(model.get_params().keys())
        filtered_params = {k: v for k, v in params.items() if k in supported_params}
        model.set_params(**filtered_params)
    return model

def default_search_space(algorithm: str) -> dict:
    if algorithm == 'Random Forest':
        return {'n_estimators': [50, 100], 'max_depth': [None, 10, 20]}
    elif algorithm == 'Logistic Regression':
        return {'C': [0.1, 1.0, 10.0]}
    elif algorithm == 'XGBoost':
        return {'n_estimators': [50, 100], 'learning_rate': [0.01, 0.1]}
    elif algorithm == 'LightGBM':
        return {'n_estimators': [50, 100], 'learning_rate': [0.01, 0.1]}
    return {}
