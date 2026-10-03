"""Batch inference using owned, server-created model bundles."""
import csv
import io
import joblib
import numpy as np
import pandas as pd

from app.services.ml_service import MLService


def predict_csv(user_id, model_id, upload):
    path, error = MLService.download_model(user_id, model_id)
    if error:
        raise ValueError('Model not found or unavailable.')
    if not upload or not upload.filename.lower().endswith('.csv'):
        raise ValueError('Choose a CSV file.')
    raw = upload.stream.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError('Prediction uploads must be 10 MB or smaller.')
    try:
        header = next(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
        if len(header) != len(set(header)):
            raise ValueError('CSV column names must be unique.')
        frame = pd.read_csv(io.BytesIO(raw), nrows=10001)
    except (UnicodeError, StopIteration, pd.errors.ParserError, pd.errors.EmptyDataError):
        raise ValueError('Choose a valid UTF-8 CSV file with a header and data rows.')
    if frame.empty or len(frame) > 10000:
        raise ValueError('Upload between 1 and 10,000 rows.')
    # Never load a user-uploaded pickle: only the owned model saved by training.
    bundle = joblib.load(path)
    if not isinstance(bundle, dict) or not bundle.get('feature_columns'):
        raise ValueError('This older model lacks its preprocessing settings. Train and save it again.')
    features = bundle['feature_columns']
    missing = [name for name in features if name not in frame.columns]
    if missing:
        raise ValueError('Missing required columns: ' + ', '.join(missing))
    model = bundle['model']
    if not hasattr(model, 'predict'):
        raise ValueError('This clustering model cannot predict new rows. Use a model such as K-Means.')
    inputs = frame[features].replace([np.inf, -np.inf], np.nan)
    try:
        transformed = bundle['preprocessor'].transform(inputs)
        predictions = model.predict(transformed)
        classes = bundle.get('label_encoder_classes')
        if classes is not None:
            predictions = np.asarray(classes)[np.asarray(predictions, dtype=int)]
    except (ValueError, TypeError) as exc:
        raise ValueError('The uploaded values do not match the training column types. Check numeric and category columns.') from exc
    column = 'prediction'
    while column in frame.columns:
        column = '_' + column
    frame[column] = predictions
    # CSV exports should be safe to open in spreadsheet software.
    def safe_cell(value):
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
            return "'" + value
        return value
    frame = frame.apply(lambda series: series.map(safe_cell))
    frame.columns = [safe_cell(str(name)) for name in frame.columns]
    return io.BytesIO(frame.to_csv(index=False).encode('utf-8-sig'))
