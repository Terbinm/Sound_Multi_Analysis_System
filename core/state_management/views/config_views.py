"""
設定管理視圖
處理分析設定的 CRUD 操作

注意：模型需求和配置 Schema 現在統一由 config_schema.py 管理，
前端透過 /api/configs/schema API 取得完整 Schema。
"""
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from views import views_bp
from auth.decorators import admin_required
from forms.config_forms import ConfigForm, ModelUploadForm
from models.analysis_config import AnalysisConfig
from models.node_status import NodeStatus
from utils.mongodb_handler import get_db
from bson.objectid import ObjectId
from datetime import datetime, timezone
import gridfs
import json
import logging

logger = logging.getLogger(__name__)


def _link_temp_files_to_config(config_id: str, session_id: str, temp_files: dict):
    """
    將暫存檔案關聯到正式配置

    Args:
        config_id: 配置 ID
        session_id: 暫存 session ID
        temp_files: {file_key: file_id, ...} 映射
    """
    db = get_db()
    files_collection = db['fs.files']

    for file_key, file_id in temp_files.items():
        try:
            # 驗證並更新檔案 metadata
            result = files_collection.update_one(
                {
                    '_id': ObjectId(file_id),
                    'metadata.temp': True
                },
                {
                    '$set': {
                        'metadata.temp': False,
                        'metadata.config_id': config_id,
                        'metadata.linked_at': datetime.now(timezone.utc)
                    },
                    '$unset': {
                        'metadata.expires_at': '',
                        'metadata.session_id': ''
                    }
                }
            )

            if result.modified_count > 0:
                # 取得檔案資訊
                file_doc = files_collection.find_one({'_id': ObjectId(file_id)})
                if file_doc:
                    file_info = {
                        'file_id': str(file_id),
                        'filename': file_doc.get('filename'),
                        'uploaded_at': datetime.now(timezone.utc),
                        'size': file_doc.get('metadata', {}).get('size', 0)
                    }
                    # 更新配置的 model_files
                    AnalysisConfig.set_model_file(config_id, file_key, file_info)
                    logger.info(f"暫存檔案已關聯: {file_key} -> {config_id}")
            else:
                logger.warning(f"暫存檔案關聯失敗 (檔案不存在或已關聯): {file_key}")

        except Exception as e:
            logger.error(f"關聯暫存檔案失敗: {file_key}, error: {e}")


def _collect_capabilities():
    caps = set()
    try:
        for node in NodeStatus.get_all_nodes():
            for cap in node.get('capabilities', []):
                if cap:
                    caps.add(cap)
    except Exception:
        pass
    try:
        for cfg in AnalysisConfig.get_all(enabled_only=False):
            if cfg.analysis_method_id:
                caps.add(cfg.analysis_method_id)
    except Exception:
        pass
    return sorted(caps)


@views_bp.route('/configs')
@admin_required
def configs_list():
    """
    設定列表頁面
    """
    try:
        # 取得查詢參數
        enabled_only = request.args.get('enabled_only', 'false').lower() == 'true'

        # 取得設定列表
        configs = AnalysisConfig.get_all(enabled_only=enabled_only)

        return render_template(
            'configs/list.html',
            configs=configs,
            enabled_only=enabled_only,
            capability_options=_collect_capabilities()
        )

    except Exception as e:
        logger.error(f"載入設定列表失敗: {str(e)}")
        flash('載入設定列表失敗', 'danger')
        return render_template('configs/list.html', configs=[], enabled_only=False)


@views_bp.route('/configs/create', methods=['GET', 'POST'])
@admin_required
def config_create():
    """
    建立新設定
    """
    form = ConfigForm()
    capability_options = _collect_capabilities()

    if form.validate_on_submit():
        try:
            # 解析參數 JSON
            parameters = {}
            if form.parameters.data:
                try:
                    parameters = json.loads(form.parameters.data)
                except json.JSONDecodeError:
                    flash('參數 JSON 格式錯誤', 'danger')
                    return render_template('configs/edit.html', form=form, mode='create')

            # 取得分類方法（從前端傳來）
            classification_method = request.form.get('classification_method', 'random')

            # 建立設定
            config = AnalysisConfig.create({
                'analysis_method_id': form.analysis_method_id.data,
                'config_name': form.config_name.data,
                'description': form.description.data,
                'parameters': parameters,
                'enabled': form.enabled.data,
                'model_files': {
                    'classification_method': classification_method,
                    'files': {}
                }
            })

            if config:
                logger.info(f"設定建立成功: {config.config_id}")

                # 處理暫存檔案關聯
                temp_session_id = request.form.get('temp_session_id', '')
                temp_files_str = request.form.get('temp_files', '{}')

                if temp_session_id and temp_files_str:
                    try:
                        temp_files = json.loads(temp_files_str)
                        if temp_files:
                            # 調用 API 將暫存檔案關聯到配置
                            _link_temp_files_to_config(config.config_id, temp_session_id, temp_files)
                            logger.info(f"暫存檔案已關聯到配置: {config.config_id}")
                    except json.JSONDecodeError:
                        logger.warning(f"解析暫存檔案資訊失敗: {temp_files_str}")
                    except Exception as e:
                        logger.error(f"關聯暫存檔案失敗: {e}")

                flash('設定建立成功', 'success')
                return redirect(url_for('views.configs_list'))
            else:
                flash('設定建立失敗', 'danger')

        except Exception as e:
            logger.error(f"建立設定失敗: {str(e)}")
            flash(f'建立設定失敗: {str(e)}', 'danger')

    return render_template(
        'configs/edit.html',
        form=form,
        mode='create',
        capability_options=capability_options
    )


@views_bp.route('/configs/<config_id>/edit', methods=['GET', 'POST'])
@admin_required
def config_edit(config_id):
    """
    編輯設定
    """
    config = AnalysisConfig.get_by_id(config_id)
    if not config:
        flash('設定不存在', 'danger')
        return redirect(url_for('views.configs_list'))

    if config.is_system:
        flash('系統內建設定不可修改', 'warning')
        return redirect(url_for('views.configs_list'))

    form = ConfigForm()
    capability_options = _collect_capabilities()

    if form.validate_on_submit():
        try:
            # 解析參數 JSON
            parameters = {}
            if form.parameters.data:
                try:
                    parameters = json.loads(form.parameters.data)
                except json.JSONDecodeError:
                    flash('參數 JSON 格式錯誤', 'danger')
                    return render_template(
                        'configs/edit.html',
                        form=form,
                        mode='edit',
                        config=config
                    )

            # 更新設定
            success = config.update_fields(
                config_name=form.config_name.data,
                description=form.description.data,
                parameters=parameters,
                enabled=form.enabled.data
            )

            if success:
                logger.info(f"設定更新成功: {config_id}")
                flash('設定更新成功', 'success')
                return redirect(url_for('views.configs_list'))
            else:
                flash('設定更新失敗', 'danger')

        except Exception as e:
            logger.error(f"更新設定失敗: {str(e)}")
            flash(f'更新設定失敗: {str(e)}', 'danger')

    elif request.method == 'GET':
        # 填充表单数据
        form.analysis_method_id.data = config.analysis_method_id
        form.config_name.data = config.config_name
        form.description.data = config.description
        form.parameters.data = json.dumps(config.parameters, indent=2, ensure_ascii=False)
        form.enabled.data = config.enabled

    return render_template(
        'configs/edit.html',
        form=form,
        mode='edit',
        config=config,
        capability_options=capability_options
    )


@views_bp.route('/configs/<config_id>/view')
@admin_required
def config_view(config_id):
    """
    查看設定詳情
    """
    config = AnalysisConfig.get_by_id(config_id)
    if not config:
        flash('設定不存在', 'danger')
        return redirect(url_for('views.configs_list'))

    return render_template('configs/view.html', config=config)


@views_bp.route('/configs/<config_id>/delete', methods=['POST'])
@admin_required
def config_delete(config_id):
    """
    刪除設定
    """
    try:
        config = AnalysisConfig.get_by_id(config_id)
        if not config:
            flash('設定不存在', 'danger')
            return redirect(url_for('views.configs_list'))

        if config.is_system:
            flash('系統內建設定不可刪除', 'warning')
            return redirect(url_for('views.configs_list'))

        success = AnalysisConfig.delete(config_id)

        if success:
            logger.info(f"設定刪除成功: {config_id}")
            flash('設定刪除成功', 'success')
        else:
            flash('設定刪除失敗', 'danger')

    except Exception as e:
        logger.error(f"刪除設定失敗: {str(e)}")
        flash(f'刪除設定失敗: {str(e)}', 'danger')

    return redirect(url_for('views.configs_list'))


@views_bp.route('/configs/<config_id>/toggle', methods=['POST'])
@admin_required
def config_toggle(config_id):
    """
    切換設定啟用狀態
    """
    try:
        config = AnalysisConfig.get_by_id(config_id)
        if not config:
            return jsonify({'success': False, 'message': '設定不存在'}), 404

        if config.is_system:
            return jsonify({'success': False, 'message': '系統設定不可變更狀態'}), 403

        new_status = not config.enabled
        success = config.update_fields(enabled=new_status)

        if success:
            logger.info(f"設定狀態切換成功: {config_id} -> {new_status}")
            return jsonify({
                'success': True,
                'enabled': new_status,
                'message': f'設定已{"啟用" if new_status else "停用"}'
            })
        else:
            return jsonify({'success': False, 'message': '更新失敗'}), 500

    except Exception as e:
        logger.error(f"切換設定狀態失敗: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
