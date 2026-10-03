"""
Module 9: Explainable AI (XAI)
Additional Libraries: shap, lime
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import warnings

warnings.filterwarnings('ignore')

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False
    print("⚠️ SHAP not installed. Install with: pip install shap")

try:
    from lime.lime_tabular import LimeTabularExplainer
    LIME_AVAILABLE = True
except ImportError:
    LIME_AVAILABLE = False
    print("⚠️ LIME not installed. Install with: pip install lime")


class ExplainableAI:
    """Add model interpretability with SHAP and LIME"""
    
    def __init__(self, model, X_train, feature_names=None, class_names=None):
        self.model = model
        self.X_train = X_train
        self.feature_names = feature_names if feature_names else [f'Feature_{i}' for i in range(X_train.shape[1])]
        self.class_names = class_names if class_names else ['Class_0', 'Class_1']
    
    def shap_analysis(self, X_test, max_display=20):
        """SHAP values for model interpretation"""
        if not SHAP_AVAILABLE:
            print("❌ SHAP is not installed. Install with: pip install shap")
            return None
        
        try:
            # Create explainer
            explainer = shap.TreeExplainer(self.model)
            shap_values = explainer.shap_values(X_test)
            
            # Summary plot
            plt.figure(figsize=(12, 8))
            shap.summary_plot(
                shap_values, 
                X_test, 
                feature_names=self.feature_names,
                max_display=max_display,
                show=False
            )
            plt.tight_layout()
            
            # Feature importance plot
            plt.figure(figsize=(12, 8))
            shap.summary_plot(
                shap_values, 
                X_test, 
                feature_names=self.feature_names,
                plot_type="bar",
                max_display=max_display,
                show=False
            )
            plt.tight_layout()
            
            return shap_values
            
        except Exception as e:
            print(f"Error in SHAP analysis: {e}")
            return None
    
    def lime_explanation(self, instance, num_features=10):
        """LIME for local interpretability"""
        if not LIME_AVAILABLE:
            print("❌ LIME is not installed. Install with: pip install lime")
            return None
        
        try:
            # Determine mode
            mode = 'classification' if hasattr(self.model, 'predict_proba') else 'regression'
            
            explainer = LimeTabularExplainer(
                self.X_train,
                feature_names=self.feature_names,
                class_names=self.class_names if mode == 'classification' else None,
                mode=mode
            )
            
            exp = explainer.explain_instance(
                instance,
                self.model.predict_proba if mode == 'classification' else self.model.predict,
                num_features=num_features
            )
            
            return exp
            
        except Exception as e:
            print(f"Error in LIME explanation: {e}")
            return None