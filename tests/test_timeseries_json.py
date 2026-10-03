import numpy as np
import pandas as pd

from app.routes.timeseries import _json_safe


def test_json_safe_converts_numpy_scalars_and_timestamp_keys():
    value = {
        pd.Timestamp("2024-01-01"): {
            "count": np.int64(4),
            "score": np.float64(0.75),
            "values": np.array([np.int64(1), np.float64("nan")]),
        }
    }

    result = _json_safe(value)

    assert result == {"2024-01-01T00:00:00": {"count": 4, "score": 0.75, "values": [1, None]}}
