"""
Module 2: Automated Machine Learning Pipeline
Additional Libraries: xgboost, lightgbm, optuna
"""
import pandas as pd
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder, LabelEncoder
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.linear_model import LogisticRegression, LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor, GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, r2_score, mean_squared_error
import warnings
import traceback


warnings.filterwarnings('ignore')

# Optional imports with error handling
try:
    from xgboost import XGBClassifier, XGBRegressor
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    print("XGBoost not installed. Install with: pip install xgboost")

try:
    from lightgbm import LGBMClassifier, LGBMRegressor
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False
    print("LightGBM not installed. Install with: pip install lightgbm")

try:
    import optuna
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    print("Optuna is not installed. Install with: pip install optuna")


class AutoMLPipeline:
    """Automated ML pipeline with model selection and hyperparameter tuning"""
    
    def __init__(self, df, target_col, test_size=0.2, random_state=42):
        self.df = df.copy()
        self.target_col = target_col
        self.test_size = test_size
        self.random_state = random_state
        self.models = {}
        self.best_model = None
        self.is_classification = None
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None
        self.preprocessor = None
        
    def auto_preprocess(self):
        """Automated data preprocessing pipeline"""
        X = self.df.drop(columns=[self.target_col])
        y = self.df[self.target_col]
        
        # Determine problem type
        if y.dtype == 'object' or (y.dtype in ['int64', 'float64'] and y.nunique() < 10):
            self.is_classification = True
            # Encode target if categorical
            if y.dtype == 'object':
                le = LabelEncoder()
                y = pd.Series(le.fit_transform(y))
        else:
            self.is_classification = False
        
        # Split data
        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(
            X, y, test_size=self.test_size, random_state=self.random_state
        )
        
        # Identify column types
        numeric_features = X.select_dtypes(include=[np.number]).columns
        categorical_features = X.select_dtypes(include=['object', 'category']).columns
        
        # Create preprocessing pipelines
        numeric_transformer = Pipeline(steps=[
            ('imputer', SimpleImputer(strategy='median')),
            ('scaler', StandardScaler())
        ])
        
        categorical_transformer = Pipeline(steps=[
            ('imputer', SimpleImputer(strategy='constant', fill_value='missing')),
            ('onehot', OneHotEncoder(handle_unknown='ignore', sparse_output=False))
        ])
        
        # Combine transformers
        self.preprocessor = ColumnTransformer(
            transformers=[
                ('num', numeric_transformer, numeric_features),
                ('cat', categorical_transformer, categorical_features)
            ])
        
        # Fit preprocessor
        X_train_processed = self.preprocessor.fit_transform(self.X_train)
        X_test_processed = self.preprocessor.transform(self.X_test)
        
        return X_train_processed, X_test_processed, self.y_train, self.y_test
    
    def compare_models(self, cv_folds=3, fast_mode=True):
        """Compare multiple ML models (fast_mode=True by default for speed)"""
        X_train, X_test, y_train, y_test = self.auto_preprocess()
        
        if fast_mode:
            cv_folds = 2
            if self.is_classification:
                models = {
                    'Logistic Regression': LogisticRegression(max_iter=500, random_state=self.random_state),
                    'Random Forest': RandomForestClassifier(n_estimators=30, max_depth=10, random_state=self.random_state)
                }
                if XGBOOST_AVAILABLE:
                    models['XGBoost'] = XGBClassifier(
                        use_label_encoder=False, 
                        eval_metric='logloss',
                        n_estimators=30, max_depth=6,
                        random_state=self.random_state
                    )
                scoring = 'accuracy'
            else:
                models = {
                    'Linear Regression': LinearRegression(),
                    'Random Forest': RandomForestRegressor(n_estimators=30, max_depth=10, random_state=self.random_state)
                }
                if XGBOOST_AVAILABLE:
                    models['XGBoost'] = XGBRegressor(
                        n_estimators=30, max_depth=6,
                        random_state=self.random_state
                    )
                scoring = 'r2'
        elif self.is_classification:
            models = {
                'Logistic Regression': LogisticRegression(max_iter=1000, random_state=self.random_state),
                'Random Forest': RandomForestClassifier(n_estimators=100, random_state=self.random_state),
                'Gradient Boosting': GradientBoostingClassifier(random_state=self.random_state)
            }
            
            # Add optional models if available
            if XGBOOST_AVAILABLE:
                models['XGBoost'] = XGBClassifier(
                    use_label_encoder=False, 
                    eval_metric='logloss',
                    random_state=self.random_state
                )
            if LIGHTGBM_AVAILABLE:
                models['LightGBM'] = LGBMClassifier(random_state=self.random_state, verbose=-1)
                
            scoring = 'accuracy'
        else:
            models = {
                'Linear Regression': LinearRegression(),
                'Ridge Regression': Ridge(random_state=self.random_state),
                'Random Forest': RandomForestRegressor(n_estimators=100, random_state=self.random_state),
                'Gradient Boosting': GradientBoostingRegressor(random_state=self.random_state)
            }
            
            if XGBOOST_AVAILABLE:
                models['XGBoost'] = XGBRegressor(random_state=self.random_state)
            if LIGHTGBM_AVAILABLE:
                models['LightGBM'] = LGBMRegressor(random_state=self.random_state, verbose=-1)
                
            scoring = 'r2'
        
        results = {}
        for name, model in models.items():
            try:
                cv_scores = cross_val_score(model, X_train, y_train, cv=cv_folds, scoring=scoring)
                results[name] = {
                    'mean_score': cv_scores.mean(),
                    'std_score': cv_scores.std(),
                    'scores': cv_scores.tolist()
                }
                
                # Fit on full training data and evaluate on test set
                model.fit(X_train, y_train)
                y_pred = model.predict(X_test)
                
                if self.is_classification:
                    results[name]['test_accuracy'] = accuracy_score(y_test, y_pred)
                    results[name]['test_precision'] = precision_score(y_test, y_pred, average='weighted')
                    results[name]['test_recall'] = recall_score(y_test, y_pred, average='weighted')
                    results[name]['test_f1'] = f1_score(y_test, y_pred, average='weighted')
                else:
                    results[name]['test_r2'] = r2_score(y_test, y_pred)
                    results[name]['test_rmse'] = np.sqrt(mean_squared_error(y_test, y_pred))
                    
            except Exception as e:
                results[name] = {'error': str(e), 'traceback': traceback.format_exc()}
        
        # Find best model
        valid_results = {k: v for k, v in results.items() if 'mean_score' in v}
        if valid_results:
            best_model_name = max(valid_results, key=lambda x: valid_results[x]['mean_score'])
            self.best_model = (best_model_name, valid_results[best_model_name])
        
        return results
    
    def hyperparameter_tuning(self, model_name='Random Forest', n_trials=10):
        """Automated hyperparameter tuning using Optuna (reduced trials for speed)"""
        if not OPTUNA_AVAILABLE:
            print("Optuna is not installed. Install with: pip install optuna")
            return None, None
        
        X_train, X_test, y_train, y_test = self.auto_preprocess()
        
        def objective(trial):
            if model_name == 'Random Forest':
                params = {
                    'n_estimators': trial.suggest_int('n_estimators', 30, 150),
                    'max_depth': trial.suggest_int('max_depth', 3, 15),
                    'min_samples_split': trial.suggest_int('min_samples_split', 2, 10),
                }
                
                if self.is_classification:
                    model = RandomForestClassifier(**params, random_state=self.random_state)
                    scoring = 'accuracy'
                else:
                    model = RandomForestRegressor(**params, random_state=self.random_state)
                    scoring = 'r2'
            
            elif model_name == 'XGBoost' and XGBOOST_AVAILABLE:
                params = {
                    'n_estimators': trial.suggest_int('n_estimators', 30, 150),
                    'max_depth': trial.suggest_int('max_depth', 3, 10),
                    'learning_rate': trial.suggest_float('learning_rate', 0.05, 0.3),
                }
                
                if self.is_classification:
                    model = XGBClassifier(**params, random_state=self.random_state)
                    scoring = 'accuracy'
                else:
                    model = XGBRegressor(**params, random_state=self.random_state)
                    scoring = 'r2'
            else:
                return 0
            
            score = cross_val_score(model, X_train, y_train, cv=2, scoring=scoring).mean()
            return score
        
        study = optuna.create_study(direction='maximize')
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        
        return study.best_params, study.best_value