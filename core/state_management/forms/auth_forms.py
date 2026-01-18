"""
認證相關表單
"""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Regexp
from models.user import User

# Email 正則表達式驗證器（避免需要安裝 email_validator 套件）
EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'


class LoginForm(FlaskForm):
    """登入表單"""
    username = StringField('使用者名稱',
                          validators=[DataRequired(message='請輸入使用者名稱'),
                                    Length(min=3, max=50, message='使用者名稱長度應在3-50個字元之間')])
    password = PasswordField('密碼',
                            validators=[DataRequired(message='請輸入密碼')])
    remember = BooleanField('記住我')
    submit = SubmitField('登入')


class UserCreateForm(FlaskForm):
    """建立使用者表單（管理員使用）"""
    username = StringField('使用者名稱',
                          validators=[DataRequired(message='請輸入使用者名稱'),
                                    Length(min=3, max=50, message='使用者名稱長度應在3-50個字元之間')])
    email = StringField('電子郵件',
                       validators=[DataRequired(message='請輸入電子郵件'),
                                 Regexp(EMAIL_REGEX, message='請輸入有效的電子郵件位址')])
    password = PasswordField('密碼',
                            validators=[DataRequired(message='請輸入密碼'),
                                      Length(min=6, message='密碼長度至少為6個字元')])
    password_confirm = PasswordField('確認密碼',
                                    validators=[DataRequired(message='請確認密碼'),
                                              EqualTo('password', message='兩次密碼輸入不一致')])
    role = SelectField('角色',
                      choices=[('user', '一般使用者'), ('admin', '管理員')],
                      validators=[DataRequired(message='請選擇角色')])
    submit = SubmitField('建立使用者')

    def validate_username(self, field):
        """驗證使用者名稱是否已存在"""
        if User.find_by_username(field.data):
            raise ValidationError('該使用者名稱已被使用')

    def validate_email(self, field):
        """驗證電子郵件是否已存在"""
        if User.find_by_email(field.data):
            raise ValidationError('該電子郵件已被註冊')


class UserEditForm(FlaskForm):
    """編輯使用者表單（管理員使用）"""
    email = StringField('電子郵件',
                       validators=[DataRequired(message='請輸入電子郵件'),
                                 Regexp(EMAIL_REGEX, message='請輸入有效的電子郵件位址')])
    role = SelectField('角色',
                      choices=[('user', '一般使用者'), ('admin', '管理員')],
                      validators=[DataRequired(message='請選擇角色')])
    is_active = BooleanField('帳戶啟用狀態')
    submit = SubmitField('儲存修改')


class ChangePasswordForm(FlaskForm):
    """修改密碼表單（使用者自行使用）"""
    current_password = PasswordField('目前密碼',
                                    validators=[DataRequired(message='請輸入目前密碼')])
    new_password = PasswordField('新密碼',
                                validators=[DataRequired(message='請輸入新密碼'),
                                          Length(min=6, message='密碼長度至少為6個字元')])
    password_confirm = PasswordField('確認新密碼',
                                    validators=[DataRequired(message='請確認新密碼'),
                                              EqualTo('new_password', message='兩次密碼輸入不一致')])
    submit = SubmitField('修改密碼')
