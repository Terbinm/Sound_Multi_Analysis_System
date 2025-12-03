"""
MongoDB 實例管理視圖
處理 MongoDB 實例的 CRUD 操作
"""
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required
from views import views_bp
from auth.decorators import admin_required
from forms.config_forms import MongoDBInstanceForm
from models.mongodb_instance import MongoDBInstance
import logging

logger = logging.getLogger(__name__)


@views_bp.route('/instances')
@login_required
def instances_list():
    """
    MongoDB 實例列表頁面
    """
    try:
        # 取得查詢參數
        enabled_only = request.args.get('enabled_only', 'false').lower() == 'true'

        # 取得實例列表（不包含密碼）
        instances = MongoDBInstance.get_all(
            enabled_only=enabled_only,
            include_password=False,
            ensure_default=True
        )

        return render_template(
            'instances/list.html',
            instances=instances,
            enabled_only=enabled_only
        )

    except Exception as e:
        logger.error(f"載入 MongoDB 實例列表失敗: {str(e)}")
        flash('載入實例列表失敗', 'danger')
        return render_template('instances/list.html', instances=[], enabled_only=False)


@views_bp.route('/instances/create', methods=['GET', 'POST'])
@admin_required
def instance_create():
    """
    建立新 MongoDB 實例
    """
    form = MongoDBInstanceForm()

    if form.validate_on_submit():
        try:
            # 建立實例
            instance = MongoDBInstance.create({
                'instance_name': form.instance_name.data,
                'description': form.description.data,
                'host': form.host.data,
                'port': int(form.port.data),
                'username': form.username.data,
                'password': form.password.data,
                'database': form.database.data,
                'collection': form.collection.data or 'recordings',
                'auth_source': form.auth_source.data or 'admin',
                'enabled': form.enabled.data
            })

            if instance:
                logger.info(f"MongoDB 實例建立成功: {instance.instance_id}")
                flash('MongoDB 實例建立成功', 'success')
                return redirect(url_for('views.instances_list'))
            else:
                flash('MongoDB 實例建立失敗', 'danger')

        except Exception as e:
            logger.error(f"建立 MongoDB 實例失敗: {str(e)}")
            flash(f'建立實例失敗: {str(e)}', 'danger')

    return render_template('instances/edit.html', form=form, mode='create')


@views_bp.route('/instances/<instance_id>/edit', methods=['GET', 'POST'])
@admin_required
def instance_edit(instance_id):
    """
    編輯 MongoDB 實例
    """
    instance = MongoDBInstance.get_by_id(instance_id, include_password=True)
    if not instance:
        flash('MongoDB 實例不存在', 'danger')
        return redirect(url_for('views.instances_list'))

    if instance.is_system:
        flash('系統內建 MongoDB 實例不可修改', 'warning')
        return redirect(url_for('views.instances_list'))

    form = MongoDBInstanceForm()

    if form.validate_on_submit():
        try:
            # 更新實例
            success = instance.update(
                instance_name=form.instance_name.data,
                description=form.description.data,
                host=form.host.data,
                port=int(form.port.data),
                username=form.username.data,
                password=form.password.data,
                database=form.database.data,
                collection=form.collection.data or 'recordings',
                auth_source=form.auth_source.data or 'admin',
                enabled=form.enabled.data
            )

            if success:
                logger.info(f"MongoDB 實例更新成功: {instance_id}")
                flash('MongoDB 實例更新成功', 'success')
                return redirect(url_for('views.instances_list'))
            else:
                flash('MongoDB 實例更新失敗', 'danger')

        except Exception as e:
            logger.error(f"更新 MongoDB 實例失敗: {str(e)}")
            flash(f'更新實例失敗: {str(e)}', 'danger')

    elif request.method == 'GET':
        # 填充表单数据
        form.instance_name.data = instance.instance_name
        form.description.data = instance.description
        form.host.data = instance.host
        form.port.data = str(instance.port)
        form.username.data = instance.username
        form.password.data = instance.password
        form.database.data = instance.database
        form.collection.data = instance.collection
        form.auth_source.data = instance.auth_source
        form.enabled.data = instance.enabled

    return render_template(
        'instances/edit.html',
        form=form,
        mode='edit',
        instance=instance
    )


@views_bp.route('/instances/<instance_id>/view')
@login_required
def instance_view(instance_id):
    """
    查看 MongoDB 實例詳情
    """
    instance = MongoDBInstance.get_by_id(instance_id, include_password=False)
    if not instance:
        flash('MongoDB 實例不存在', 'danger')
        return redirect(url_for('views.instances_list'))

    return render_template('instances/view.html', instance=instance)


@views_bp.route('/instances/<instance_id>/delete', methods=['POST'])
@admin_required
def instance_delete(instance_id):
    """
    刪除 MongoDB 實例
    """
    try:
        instance = MongoDBInstance.get_by_id(instance_id)
        if not instance:
            flash('MongoDB 實例不存在', 'danger')
            return redirect(url_for('views.instances_list'))

        if instance.is_system:
            flash('系統內建 MongoDB 實例不可刪除', 'warning')
            return redirect(url_for('views.instances_list'))

        success = MongoDBInstance.delete(instance_id)

        if success:
            logger.info(f"MongoDB 實例刪除成功: {instance_id}")
            flash('MongoDB 實例刪除成功', 'success')
        else:
            flash('MongoDB 實例刪除失敗', 'danger')

    except Exception as e:
        logger.error(f"刪除 MongoDB 實例失敗: {str(e)}")
        flash(f'刪除實例失敗: {str(e)}', 'danger')

    return redirect(url_for('views.instances_list'))


@views_bp.route('/instances/<instance_id>/toggle', methods=['POST'])
@admin_required
def instance_toggle(instance_id):
    """
    切換 MongoDB 實例啟用狀態
    """
    try:
        instance = MongoDBInstance.get_by_id(instance_id)
        if not instance:
            return jsonify({'success': False, 'message': '實例不存在'}), 404

        if instance.is_system:
            return jsonify({'success': False, 'message': '系統實例不可變更狀態'}), 403

        new_status = not instance.enabled
        success = instance.update(enabled=new_status)

        if success:
            logger.info(f"MongoDB 實例狀態切換成功: {instance_id} -> {new_status}")
            return jsonify({
                'success': True,
                'enabled': new_status,
                'message': f'實例已{"啟用" if new_status else "停用"}'
            })
        else:
            return jsonify({'success': False, 'message': '更新失敗'}), 500

    except Exception as e:
        logger.error(f"切換 MongoDB 實例狀態失敗: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@views_bp.route('/instances/<instance_id>/test', methods=['POST'])
@admin_required
def instance_test(instance_id):
    """
    測試 MongoDB 實例連線
    """
    try:
        instance = MongoDBInstance.get_by_id(instance_id, include_password=True)
        if not instance:
            return jsonify({'success': False, 'message': '實例不存在'}), 404

        # 測試連線
        success, message = instance.test_connection()

        return jsonify({
            'success': success,
            'message': message
        })

    except Exception as e:
        logger.error(f"測試 MongoDB 連線失敗: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
