"""
資料列表與詳情視圖
提供錄音資料的篩選、查看與分析結果展示
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional

from flask import render_template, request, abort
from flask_login import login_required

from views import views_bp
from utils.mongodb_handler import get_db
from config import get_config

logger = logging.getLogger(__name__)


def _normalize_steps(step_payload: Any) -> List[Dict[str, Any]]:
    """將 steps 轉為可排序的列表，保持動態欄位"""
    if isinstance(step_payload, dict):
        steps = [
            {'name': name, **(content or {})}
            for name, content in step_payload.items()
        ]
        return sorted(steps, key=lambda s: s.get('display_order', 999))
    if isinstance(step_payload, list):
        return step_payload
    return []


def _normalize_runs(record: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    解析 analyze_features.runs 結構，支援 dict/list 與舊版格式
    Returns: (runs, latest_run)
    """
    analyze_features = record.get('analyze_features', {}) or {}
    runs_container = analyze_features.get('runs') if isinstance(analyze_features, dict) else None

    raw_runs: List[Dict[str, Any]] = []
    if isinstance(runs_container, dict):
        raw_runs = list(runs_container.values())
    elif isinstance(runs_container, list):
        raw_runs = runs_container
    elif isinstance(analyze_features, list):
        # legacy: treat top-level list as single run
        raw_runs = [{
            'analysis_id': f"legacy-{record.get('AnalyzeUUID', 'unknown')}",
            'steps': analyze_features,
            'analysis_summary': record.get('analysis_summary', {}),
            'requested_at': record.get('created_at'),
            'started_at': record.get('processing_started_at'),
            'completed_at': record.get('updated_at'),
            'error_message': record.get('error_message')
        }]

    runs: List[Dict[str, Any]] = []
    for idx, run in enumerate(raw_runs, start=1):
        context = run.get('analysis_context', {}) or {}
        routing_ctx = context.get('routing_rule', {}) if isinstance(context, dict) else {}
        config_ctx = context.get('analysis_config', {}) if isinstance(context, dict) else {}
        node_ctx = context.get('node', {}) if isinstance(context, dict) else {}

        analysis_summary = run.get('analysis_summary', {}) or {}
        steps = _normalize_steps(run.get('steps'))

        status = 'completed'
        if run.get('error_message'):
            status = 'failed'
        elif not run.get('completed_at'):
            status = 'processing'

        runs.append({
            'index': idx,
            'analysis_id': run.get('analysis_id'),
            'analysis_summary': analysis_summary,
            'analysis_config_id': run.get('analysis_config_id') or config_ctx.get('config_id'),
            'analysis_method_id': run.get('analysis_method_id') or config_ctx.get('analysis_method_id'),
            'routing_rule_id': run.get('routing_rule_id') or routing_ctx.get('rule_id'),
            'router_id': run.get('router_id') or routing_ctx.get('router_id'),
            'node_id': run.get('node_id') or node_ctx.get('node_id'),
            'analysis_context': context,
            'steps': steps,
            'requested_at': run.get('requested_at'),
            'started_at': run.get('started_at'),
            'completed_at': run.get('completed_at'),
            'error_message': run.get('error_message'),
            'status': status
        })

    runs = sorted(
        runs,
        key=lambda r: r.get('started_at') or r.get('requested_at') or datetime.min
    )
    for i, run in enumerate(runs, start=1):
        run['index'] = i

    latest_run = None
    latest_id = analyze_features.get('latest_analysis_id') if isinstance(analyze_features, dict) else None
    if latest_id:
        latest_run = next((r for r in runs if r.get('analysis_id') == latest_id), None)
    if not latest_run and runs:
        # fallback: 使用完成時間排序
        latest_run = sorted(
            runs,
            key=lambda r: r.get('completed_at') or r.get('started_at') or datetime.min,
            reverse=True
        )[0]

    return runs, latest_run


def _build_log_filters(args: Dict[str, Any]) -> Dict[str, Any]:
    filters: Dict[str, Any] = {}
    for key in ('router_id', 'rule_id', 'config_id', 'status', 'analysis_method_id'):
        value = args.get(key, '').strip()
        if value:
            filters[key if key != 'analysis_method_id' else 'analysis_method_id'] = value
    return filters


@views_bp.route('/data')
@login_required
def data_list():
    """資料列表與篩選"""
    try:
        config = get_config()
        db = get_db()
        recordings_col = db[config.COLLECTIONS['recordings']]
        logs_col = db[config.COLLECTIONS['task_execution_logs']]

        page = max(request.args.get('page', 1, type=int), 1)
        page_size = request.args.get('page_size', 20, type=int)
        page_size = max(1, min(page_size, 100))
        skip = (page - 1) * page_size

        keyword = request.args.get('q', '').strip()
        dataset_uuid = request.args.get('dataset_uuid', '').strip()

        base_query: Dict[str, Any] = {}
        if keyword:
            base_query['$or'] = [
                {'AnalyzeUUID': {'$regex': keyword, '$options': 'i'}},
                {'files.raw.filename': {'$regex': keyword, '$options': 'i'}}
            ]
        if dataset_uuid:
            base_query['info_features.dataset_UUID'] = {'$regex': f"^{dataset_uuid}$", '$options': 'i'}

        log_filters = _build_log_filters(request.args)
        if log_filters:
            matched_uuids = list(logs_col.distinct('analyze_uuid', log_filters))
            if not matched_uuids:
                return render_template(
                    'data/list.html',
                    records=[],
                    filters=request.args,
                    pagination={
                        'page': page,
                        'page_size': page_size,
                        'total': 0,
                        'pages': 0
                    }
                )
            base_query['AnalyzeUUID'] = {'$in': matched_uuids}

        total = recordings_col.count_documents(base_query)
        cursor = recordings_col.find(base_query).sort('created_at', -1).skip(skip).limit(page_size)

        records = []
        for doc in cursor:
            runs, latest_run = _normalize_runs(doc)
            latest_summary = (latest_run or {}).get('analysis_summary', {}) or {}
            records.append({
                'analyze_uuid': doc.get('AnalyzeUUID'),
                'filename': doc.get('files', {}).get('raw', {}).get('filename'),
                'dataset_uuid': doc.get('info_features', {}).get('dataset_UUID'),
                'upload_time': doc.get('info_features', {}).get('upload_time') or doc.get('created_at'),
                'runs': runs,
                'latest_run': latest_run,
                'latest_prediction': latest_summary.get('final_prediction'),
                'latest_summary': latest_summary
            })

        pagination = {
            'page': page,
            'page_size': page_size,
            'total': total,
            'pages': (total + page_size - 1) // page_size
        }

        return render_template(
            'data/list.html',
            records=records,
            filters=request.args,
            pagination=pagination
        )

    except Exception as exc:
        logger.error(f"載入資料列表失敗: {exc}", exc_info=True)
        return render_template(
            'data/list.html',
            records=[],
            filters=request.args,
            pagination={'page': 1, 'page_size': 20, 'total': 0, 'pages': 0},
            error=str(exc)
        )


@views_bp.route('/data/<analyze_uuid>')
@login_required
def data_detail(analyze_uuid: str):
    """單筆資料詳情頁"""
    try:
        config = get_config()
        db = get_db()
        recordings_col = db[config.COLLECTIONS['recordings']]
        logs_col = db[config.COLLECTIONS['task_execution_logs']]

        record = recordings_col.find_one({'AnalyzeUUID': analyze_uuid})
        if not record:
            abort(404)

        runs, latest_run = _normalize_runs(record)
        logs = list(
            logs_col.find({'analyze_uuid': analyze_uuid}).sort('created_at', -1).limit(200)
        )

        return render_template(
            'data/detail.html',
            record=record,
            runs=runs,
            latest_run=latest_run,
            logs=logs
        )

    except Exception as exc:
        logger.error(f"載入資料詳情失敗: {exc}", exc_info=True)
        abort(500)
