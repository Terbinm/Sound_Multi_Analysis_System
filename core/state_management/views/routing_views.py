"""
路由規則管理視圖
處理路由規則的 CRUD 操作與監控
"""
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required
from views import views_bp
from auth.decorators import admin_required
from forms.config_forms import RoutingRuleForm
from models.routing_rule import RoutingRule
from models.task_execution_log import TaskExecutionLog
import json
import logging

logger = logging.getLogger(__name__)


@views_bp.route('/routing')
@admin_required
def routing_list():
    """
    路由規則列表頁面
    """
    try:
        # 取得查詢參數
        enabled_only = request.args.get('enabled_only', 'true').lower() == 'true'

        # 取得規則列表（依優先級排序）
        rules = RoutingRule.get_all(enabled_only=enabled_only)

        return render_template(
            'routing/list.html',
            rules=rules,
            enabled_only=enabled_only
        )

    except Exception as e:
        logger.error(f"載入路由規則列表失敗: {str(e)}")
        flash('載入路由規則列表失敗', 'danger')
        return render_template('routing/list.html', rules=[], enabled_only=True)


@views_bp.route('/routing/wizard', methods=['GET'])
@admin_required
def routing_wizard():
    """
    路由規則建立嚮導（新版）
    提供多步驟嚮導式介面
    """
    return render_template('routing/wizard.html')


@views_bp.route('/routing/create', methods=['GET', 'POST'])
@admin_required
def routing_create():
    """
    建立新路由規則（舊版，保留向後相容）
    """
    form = RoutingRuleForm()

    if form.validate_on_submit():
        try:
            # 解析 JSON 資料
            try:
                conditions = json.loads(form.conditions.data)
                actions = json.loads(form.actions.data)
                priority = int(form.priority.data)
            except (json.JSONDecodeError, ValueError) as e:
                flash(f'JSON 格式錯誤: {str(e)}', 'danger')
                return render_template('routing/edit.html', form=form, mode='create')

            # 建立規則
            rule = RoutingRule.create({
                'rule_name': form.rule_name.data,
                'description': form.description.data,
                'priority': priority,
                'conditions': conditions,
                'actions': actions,
                'enabled': form.enabled.data
            })

            if rule:
                logger.info(f"路由規則建立成功: {rule.rule_id}")
                flash('路由規則建立成功', 'success')
                return redirect(url_for('views.routing_list'))
            else:
                flash('路由規則建立失敗', 'danger')

        except Exception as e:
            logger.error(f"建立路由規則失敗: {str(e)}")
            flash(f'建立路由規則失敗: {str(e)}', 'danger')

    return render_template('routing/edit.html', form=form, mode='create')


@views_bp.route('/routing/<rule_id>/edit', methods=['GET', 'POST'])
@admin_required
def routing_edit(rule_id):
    """
    編輯路由規則
    """
    rule = RoutingRule.get_by_id(rule_id)
    if not rule:
        flash('路由規則不存在', 'danger')
        return redirect(url_for('views.routing_list'))

    form = RoutingRuleForm()

    if form.validate_on_submit():
        try:
            # 解析 JSON 資料
            try:
                conditions = json.loads(form.conditions.data)
                actions = json.loads(form.actions.data)
                priority = int(form.priority.data)
            except (json.JSONDecodeError, ValueError) as e:
                flash(f'JSON 格式錯誤: {str(e)}', 'danger')
                return render_template(
                    'routing/edit.html',
                    form=form,
                    mode='edit',
                    rule=rule
                )

            # 更新規則
            success = RoutingRule.update(
                rule.rule_id,
                {
                    'rule_name': form.rule_name.data,
                    'description': form.description.data,
                    'priority': priority,
                    'conditions': conditions,
                    'actions': actions,
                    'enabled': form.enabled.data
                }
            )

            if success:
                logger.info(f"路由規則更新成功: {rule_id}")
                flash('路由規則更新成功', 'success')
                return redirect(url_for('views.routing_list'))
            else:
                flash('路由規則更新失敗', 'danger')

        except Exception as e:
            logger.error(f"更新路由規則失敗: {str(e)}")
            flash(f'更新路由規則失敗: {str(e)}', 'danger')

    elif request.method == 'GET':
        # 填充表单数据
        form.rule_name.data = rule.rule_name
        form.description.data = rule.description
        form.priority.data = str(rule.priority)
        form.conditions.data = json.dumps(rule.conditions, indent=2, ensure_ascii=False)
        form.actions.data = json.dumps(rule.actions, indent=2, ensure_ascii=False)
        form.enabled.data = rule.enabled

    return render_template(
        'routing/edit.html',
        form=form,
        mode='edit',
        rule=rule
    )


@views_bp.route('/routing/<rule_id>/view')
@admin_required
def routing_view(rule_id):
    """
    查看路由規則詳情
    """
    rule = RoutingRule.get_by_id(rule_id)
    if not rule:
        flash('路由規則不存在', 'danger')
        return redirect(url_for('views.routing_list'))

    stats = rule.get_statistics()

    return render_template('routing/view.html', rule=rule, stats=stats)


@views_bp.route('/routing/<rule_id>/delete', methods=['POST'])
@admin_required
def routing_delete(rule_id):
    """
    刪除路由規則
    """
    try:
        success = RoutingRule.delete(rule_id)

        if success:
            logger.info(f"路由規則刪除成功: {rule_id}")
            flash('路由規則刪除成功', 'success')
        else:
            flash('路由規則刪除失敗', 'danger')

    except Exception as e:
        logger.error(f"刪除路由規則失敗: {str(e)}")
        flash(f'刪除路由規則失敗: {str(e)}', 'danger')

    return redirect(url_for('views.routing_list'))


@views_bp.route('/routing/<rule_id>/toggle', methods=['POST'])
@admin_required
def routing_toggle(rule_id):
    """
    切換路由規則啟用狀態
    """
    try:
        rule = RoutingRule.get_by_id(rule_id)
        if not rule:
            return jsonify({'success': False, 'message': '路由規則不存在'}), 404

        new_status = not rule.enabled
        success = RoutingRule.update(rule.rule_id, {'enabled': new_status})

        if success:
            logger.info(f"路由規則狀態切換成功: {rule_id} -> {new_status}")
            return jsonify({
                'success': True,
                'enabled': new_status,
                'message': f'路由規則已{"啟用" if new_status else "停用"}'
            })
        else:
            return jsonify({'success': False, 'message': '更新失敗'}), 500

    except Exception as e:
        logger.error(f"切換路由規則狀態失敗: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@views_bp.route('/routing/test', methods=['POST'])
@admin_required
def routing_test():
    """
    測試路由規則匹配
    """
    try:
        data = request.get_json()
        if not data or 'info_features' not in data:
            return jsonify({
                'success': False,
                'message': '請提供 info_features 資料'
            }), 400

        info_features = data['info_features']

        # 測試匹配
        matched_rules = RoutingRule.test_match(info_features)

        return jsonify({
            'success': True,
            'matched_count': len(matched_rules),
            'matched_rules': [
                {
                    'rule_id': rule.rule_id,
                    'rule_name': rule.rule_name,
                    'priority': rule.priority,
                    'actions': rule.actions
                }
                for rule in matched_rules
            ]
        })

    except Exception as e:
        logger.error(f"測試路由規則失敗: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@views_bp.route('/routing/<router_id>/monitor')
@admin_required
def routing_monitor(router_id):
    """
    監控 routerID 的執行狀態
    顯示執行統計與最近的任務記錄
    """
    try:
        # 根據 router_id 查找規則
        rule = RoutingRule.get_by_router_id(router_id)
        if not rule:
            flash(f'找不到 router_id: {router_id}', 'danger')
            return redirect(url_for('views.routing_list'))

        # 獲取統計資訊
        stats = TaskExecutionLog.get_statistics(router_id)

        return render_template(
            'routing/monitor.html',
            router_id=router_id,
            rule=rule,
            stats=stats
        )

    except Exception as e:
        logger.error(f"載入監控頁面失敗: {str(e)}")
        flash('載入監控頁面失敗', 'danger')
        return redirect(url_for('views.routing_list'))
