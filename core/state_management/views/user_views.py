"""
使用者管理視圖（僅管理員）
處理使用者的 CRUD 操作
"""
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import current_user
from flask_bcrypt import generate_password_hash, check_password_hash
from views import views_bp
from auth.decorators import admin_required
from forms.auth_forms import UserCreateForm, UserEditForm, ChangePasswordForm
from models.user import User
import logging

logger = logging.getLogger(__name__)


@views_bp.route('/users')
@admin_required
def users_list():
    """
    使用者列表頁面（僅管理員）
    """
    try:
        # 取得查詢參數
        include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'

        # 取得使用者列表
        users = User.get_all(include_inactive=include_inactive)

        return render_template(
            'users/list.html',
            users=users,
            include_inactive=include_inactive
        )

    except Exception as e:
        logger.error(f"載入使用者列表失敗: {str(e)}")
        flash('載入使用者列表失敗', 'danger')
        return render_template('users/list.html', users=[], include_inactive=False)


@views_bp.route('/users/create', methods=['GET', 'POST'])
@admin_required
def user_create():
    """
    建立新使用者（僅管理員）
    """
    form = UserCreateForm()

    if form.validate_on_submit():
        try:
            # 生成密碼雜湊
            password_hash = generate_password_hash(form.password.data).decode('utf-8')

            # 建立使用者
            user = User.create(
                username=form.username.data,
                email=form.email.data,
                password_hash=password_hash,
                role=form.role.data
            )

            if user:
                logger.info(f"使用者建立成功: {user.username} (by {current_user.username})")
                flash(f'使用者 {user.username} 建立成功', 'success')
                return redirect(url_for('views.users_list'))
            else:
                flash('使用者建立失敗', 'danger')

        except Exception as e:
            logger.error(f"建立使用者失敗: {str(e)}")
            flash(f'建立使用者失敗: {str(e)}', 'danger')

    return render_template('users/create.html', form=form)


@views_bp.route('/users/<username>/edit', methods=['GET', 'POST'])
@admin_required
def user_edit(username):
    """
    編輯使用者（僅管理員）
    """
    user = User.find_by_username(username)
    if not user:
        flash('使用者不存在', 'danger')
        return redirect(url_for('views.users_list'))

    # 不允許編輯自己的帳戶
    if user.username == current_user.username:
        flash('不能編輯自己的帳戶，請使用個人資料頁面', 'warning')
        return redirect(url_for('views.users_list'))

    form = UserEditForm()

    if form.validate_on_submit():
        try:
            # 更新使用者資訊
            success = user.update(
                email=form.email.data,
                role=form.role.data,
                is_active=form.is_active.data
            )

            if success:
                logger.info(f"使用者資訊更新成功: {username} (by {current_user.username})")
                flash('使用者資訊更新成功', 'success')
                return redirect(url_for('views.users_list'))
            else:
                flash('使用者資訊更新失敗', 'danger')

        except Exception as e:
            logger.error(f"更新使用者資訊失敗: {str(e)}")
            flash(f'更新使用者資訊失敗: {str(e)}', 'danger')

    elif request.method == 'GET':
        # 填充表单数据
        form.email.data = user.email
        form.role.data = user.role
        form.is_active.data = user.is_active

    return render_template('users/edit.html', form=form, user=user)


@views_bp.route('/users/<username>/view')
@admin_required
def user_view(username):
    """
    查看使用者詳情（僅管理員）
    """
    user = User.find_by_username(username)
    if not user:
        flash('使用者不存在', 'danger')
        return redirect(url_for('views.users_list'))

    return render_template('users/view.html', user=user)


@views_bp.route('/users/<username>/delete', methods=['POST'])
@admin_required
def user_delete(username):
    """
    刪除使用者（軟刪除，僅管理員）
    """
    try:
        # 不允許刪除自己
        if username == current_user.username:
            flash('不能刪除自己的帳戶', 'danger')
            return redirect(url_for('views.users_list'))

        user = User.find_by_username(username)
        if not user:
            flash('使用者不存在', 'danger')
            return redirect(url_for('views.users_list'))

        success = user.delete()

        if success:
            logger.info(f"使用者刪除成功: {username} (by {current_user.username})")
            flash(f'使用者 {username} 已被停用', 'success')
        else:
            flash('使用者刪除失敗', 'danger')

    except Exception as e:
        logger.error(f"刪除使用者失敗: {str(e)}")
        flash(f'刪除使用者失敗: {str(e)}', 'danger')

    return redirect(url_for('views.users_list'))


@views_bp.route('/users/<username>/reset-password', methods=['POST'])
@admin_required
def user_reset_password(username):
    """
    重設使用者密碼（僅管理員）
    """
    try:
        user = User.find_by_username(username)
        if not user:
            return jsonify({'success': False, 'message': '使用者不存在'}), 404

        # 生成臨時密碼（可改為寄送郵件）
        import secrets
        temp_password = secrets.token_urlsafe(12)
        password_hash = generate_password_hash(temp_password).decode('utf-8')

        success = user.update(password_hash=password_hash)

        if success:
            logger.info(f"密碼重設成功: {username} (by {current_user.username})")
            return jsonify({
                'success': True,
                'message': '密碼已重設',
                'temp_password': temp_password
            })
        else:
            return jsonify({'success': False, 'message': '重設失敗'}), 500

    except Exception as e:
        logger.error(f"重設密碼失敗: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@views_bp.route('/profile/change-password', methods=['GET', 'POST'])
def change_password():
    """
    修改自己的密碼
    """
    if not current_user.is_authenticated:
        flash('請先登入', 'warning')
        return redirect(url_for('auth.login'))

    form = ChangePasswordForm()

    if form.validate_on_submit():
        try:
            # 驗證目前密碼
            if not check_password_hash(current_user.password_hash, form.current_password.data):
                flash('目前密碼錯誤', 'danger')
                return render_template('users/change_password.html', form=form)

            # 更新密碼
            new_password_hash = generate_password_hash(form.new_password.data).decode('utf-8')
            success = current_user.update(password_hash=new_password_hash)

            if success:
                logger.info(f"密碼修改成功: {current_user.username}")
                flash('密碼修改成功', 'success')
                return redirect(url_for('views.dashboard'))
            else:
                flash('密碼修改失敗', 'danger')

        except Exception as e:
            logger.error(f"修改密碼失敗: {str(e)}")
            flash(f'修改密碼失敗: {str(e)}', 'danger')

    return render_template('users/change_password.html', form=form)
