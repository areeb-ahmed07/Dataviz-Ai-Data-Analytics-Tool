"""Prepare complete, JSON-safe chart data without changing the source frame."""
import json

import numpy as np
import pandas as pd


def prepare_chart_data(df, chart_type, x=None, y=None, z=None, agg='none'):
    types = {'bar', 'line', 'scatter', 'pie', 'histogram', 'box', 'violin',
             'heatmap', 'correlation', 'treemap'}
    if chart_type not in types:
        raise ValueError('Please select a supported chart type.')
    if agg not in {'none', 'count', 'sum', 'mean', 'min', 'max'}:
        raise ValueError('Please select a supported aggregation.')
    if df.empty:
        raise ValueError('The dataset has no rows to plot.')
    df = df.replace([np.inf, -np.inf], np.nan)

    def values(series):
        # Series.apply(None) coerces nulls back to NaN for numeric columns.
        # Pandas JSON serialization preserves them as standards-compliant nulls.
        return json.loads(series.to_json(orient='values', date_format='iso'))

    def require(col, label):
        if not col or col not in df.columns:
            raise ValueError(f'Please select a valid {label} column.')

    def numeric(col):
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(f'"{col}" must contain numbers for this chart. Select a numeric value column or use Count.')

    if chart_type == 'correlation':
        corr = df.select_dtypes(include='number').corr().round(4)
        if len(corr.columns) < 2:
            raise ValueError('Correlation requires at least two numeric columns.')
        return {'x': list(corr.columns), 'y': list(corr.index),
                'z': json.loads(corr.to_json(orient='values'))}

    require(x, 'X/label')
    if chart_type not in {'bar', 'pie', 'treemap', 'heatmap'}:
        agg = 'none'
    if chart_type != 'histogram' and agg != 'count':
        require(y, 'Y/value')
    if y:
        require(y, 'Y/value')

    if chart_type == 'heatmap':
        require(y, 'Y')
        require(z, 'Z/value')
        numeric(z)
        work = df[[x, y, z]].dropna()
        if len({x, y, z}) < 3:
            raise ValueError('Select different X, Y, and Z columns for the heatmap.')
        if agg == 'none' and work.duplicated([x, y]).any():
            raise ValueError('Several rows share the same X and Y. Select an aggregation for the heatmap.')
        matrix = work.pivot_table(index=y, columns=x, values=z,
                                  aggfunc='first' if agg == 'none' else agg, observed=True)
        if matrix.empty:
            raise ValueError('No valid values are available for this heatmap.')
        return {'x': values(matrix.columns.to_series()), 'y': values(matrix.index.to_series()),
                'z': json.loads(matrix.to_json(orient='values'))}

    if chart_type in {'bar', 'pie', 'treemap', 'box', 'violin'} and agg != 'count':
        numeric(y)
    if chart_type == 'histogram':
        numeric(x)
        return {'x': values(df[x].dropna())}

    if agg != 'none':
        grouped = df.groupby(x, dropna=False, observed=True, sort=True)
        if agg == 'count':
            series = grouped.size()  # Count rows, including null Y values.
        else:
            numeric(y)
            series = (grouped[y].sum(min_count=1) if agg == 'sum'
                      else grouped[y].agg(agg))
        result = {'x': values(series.index.to_series()), 'y': values(series)}
    else:
        work = df.dropna(subset=[x, y])
        if chart_type == 'line':
            work = work.sort_values(x, kind='stable')
        result = {'x': values(work[x]), 'y': values(work[y])}

    if not result['x']:
        raise ValueError('No valid values are available for these columns.')
    if chart_type in {'pie', 'treemap'}:
        # Plotly drops treemap nodes with null labels; retain their totals.
        missing_label = '(Missing)'
        while missing_label in result['x']:
            missing_label = '_' + missing_label
        result['x'] = [missing_label if v is None else v for v in result['x']]
        amounts = [v for v in result['y'] if v is not None]
        if any(v < 0 for v in amounts) or not any(v > 0 for v in amounts):
            raise ValueError('Pie and treemap values must be nonnegative, with at least one positive value.')
    return result
