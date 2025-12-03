"""
認證路由
處理使用者登入、登出等功能
"""
from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, current_user
from flask_bcrypt import check_password_hash
from auth import auth_bp
from models.user import User
from forms.auth_forms import LoginForm
import logging

logger = logging.getLogger(__name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    登入頁面與處理
    """
    # 如果已登入，重定向到儀表板
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))

    form = LoginForm()

    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data
        remember = form.remember.data

        # 驗證輸入
        if not username or not password:
            flash('請輸入使用者名稱與密碼', 'danger')
            return render_template('auth/login.html', form=form)

        # 查找使用者
        user = User.find_by_username(username)

        if user is None:
            logger.warning(f"登入失敗：使用者不存在 - {username}")
            flash('使用者名稱或密碼錯誤', 'danger')
            return render_template('auth/login.html', form=form)

        # 檢查帳戶是否啟用
        if not user.is_active:
            logger.warning(f"登入失敗：帳戶未啟用 - {username}")
            flash('您的帳戶已被停用，請聯絡管理員', 'danger')
            return render_template('auth/login.html', form=form)

        # 驗證密碼
        if not check_password_hash(user.password_hash, password):
            logger.warning(f"登入失敗：密碼錯誤 - {username}")
            flash('使用者名稱或密碼錯誤', 'danger')
            return render_template('auth/login.html', form=form)

        # 登入成功
        login_user(user, remember=remember)
        user.update_last_login()

        logger.info(f"使用者登入成功: {username}")
        flash(f'歡迎回來，{username}！', 'success')

        # 重定向到之前嘗試存取的頁面，或儀表板
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for('views.dashboard'))

    if request.method == 'POST':
        flash('請檢查輸入內容', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
def logout():
    """
    登出處理
    """
    if current_user.is_authenticated:
        username = current_user.username
        logout_user()
        logger.info(f"使用者登出: {username}")
        flash('您已成功登出', 'info')
    else:
        flash('您尚未登入', 'warning')

    return redirect(url_for('auth.login'))


@auth_bp.route('/profile')
def profile():
    """
    使用者個人資料頁面（未來擴充）
    """
    if not current_user.is_authenticated:
        flash('請先登入', 'warning')
        return redirect(url_for('auth.login'))

    return render_template('auth/profile.html', user=current_user)
