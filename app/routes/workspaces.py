"""Named, private snapshots of saved dataset analysis settings."""
import json
from flask import Blueprint, render_template, request, jsonify, abort
from app.auth_helpers import login_required, get_current_user
from app.services.dataset_service import DatasetService
from app.services.ml_service import MLService
from auth.database import get_session, WorkspaceDB, SavedChartDB

workspaces_bp = Blueprint('workspaces', __name__)


@workspaces_bp.route('/workspaces', methods=['GET'])
@login_required
def index():
    user = get_current_user()
    db = get_session()
    try:
        rows = db.query(WorkspaceDB).filter_by(user_id=user.id).order_by(WorkspaceDB.created_at.desc()).all()
        return render_template('projects/workspaces.html', user=user, workspaces=rows, active_page='projects')
    finally:
        db.close()


@workspaces_bp.route('/api/datasets/<int:dataset_id>/workspaces', methods=['POST'])
@login_required
def save(dataset_id):
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        abort(404)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error='Provide workspace settings.'), 400
    name = payload.get('name')
    ui = payload.get('ui', [])
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120 or not isinstance(ui, list):
        return jsonify(error='Enter a workspace name between 1 and 120 characters.'), 400
    if len(json.dumps(ui)) > 100000:
        return jsonify(error='Workspace settings are too large.'), 400
    if any(not isinstance(field, dict) or not isinstance(field.get('id'), str)
           or not isinstance(field.get('value', ''), str) for field in ui):
        return jsonify(error='Invalid workspace settings.'), 400
    config, _ = MLService.get_config(user.id, dataset_id)
    if not config:
        return jsonify(error='Save your ML configuration before saving a workspace.'), 400
    db = get_session()
    try:
        charts = db.query(SavedChartDB).filter_by(user_id=user.id, dataset_id=dataset_id).all()
        state = {'config': config, 'ui': ui, 'cleaning_history': dataset.cleaning_pipeline or [], 'charts': [
            {'name': c.name, 'config': c.config} for c in charts]}
        row = WorkspaceDB(user_id=user.id, dataset_id=dataset_id, name=name.strip(), state=json.dumps(state))
        db.add(row)
        db.commit()
        return jsonify(id=row.id), 201
    finally:
        db.close()


@workspaces_bp.route('/workspaces/<int:workspace_id>')
@login_required
def detail(workspace_id):
    user = get_current_user()
    db = get_session()
    try:
        row = db.query(WorkspaceDB).filter_by(id=workspace_id, user_id=user.id).first()
        if not row:
            abort(404)
        dataset = DatasetService.get_dataset(row.dataset_id, user.id)
        if not dataset:
            abort(404)
        return render_template('projects/workspace.html', user=user, workspace=row,
                               dataset=dataset, state=json.loads(row.state), active_page='projects')
    finally:
        db.close()


@workspaces_bp.route('/api/workspaces/<int:workspace_id>')
@login_required
def load(workspace_id):
    user = get_current_user()
    db = get_session()
    try:
        row = db.query(WorkspaceDB).filter_by(id=workspace_id, user_id=user.id).first()
        if not row or not DatasetService.get_dataset(row.dataset_id, user.id):
            abort(404)
        return jsonify(id=row.id, name=row.name, dataset_id=row.dataset_id, **json.loads(row.state))
    finally:
        db.close()


@workspaces_bp.route('/workspaces/<int:workspace_id>/charts/<int:chart_index>')
@login_required
def chart(workspace_id, chart_index):
    user = get_current_user()
    db = get_session()
    try:
        row = db.query(WorkspaceDB).filter_by(id=workspace_id, user_id=user.id).first()
        if not row:
            abort(404)
        dataset = DatasetService.get_dataset(row.dataset_id, user.id)
        charts = json.loads(row.state)['charts']
        if not dataset or chart_index >= len(charts):
            abort(404)
        return render_template('visualization/workspace.html', user=user, dataset=dataset,
                               loaded_config=charts[chart_index]['config'], active_page='visualization')
    finally:
        db.close()
