"""
設定管理相關表單
"""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, BooleanField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Length, Optional


class ConfigForm(FlaskForm):
    """分析設定表單"""
    analysis_method_id = StringField('分析方法 ID',
                                     validators=[DataRequired(message='請輸入分析方法 ID'),
                                               Length(max=100)])
    config_name = StringField('設定名稱',
                             validators=[DataRequired(message='請輸入設定名稱'),
                                       Length(max=200)])
    description = TextAreaField('描述',
                               validators=[Optional(),
                                         Length(max=500)])
    parameters = TextAreaField('參數 (JSON 格式)',
                              validators=[Optional()],
                              render_kw={'rows': 10, 'placeholder': '請輸入 JSON 格式的參數設定'})
    enabled = BooleanField('啟用', default=True)
    submit = SubmitField('儲存')


class ModelUploadForm(FlaskForm):
    """模型檔案上傳表單"""
    file = FileField('模型檔案',
                    validators=[
                        DataRequired(message='請選擇檔案'),
                        FileAllowed(['pkl', 'pth', 'h5', 'onnx', 'pb'],
                                  message='僅支援 .pkl、.pth、.h5、.onnx、.pb 格式檔案')
                    ])
    config_id = HiddenField('設定 ID')
    submit = SubmitField('上傳')


class RoutingRuleForm(FlaskForm):
    """路由規則表單"""
    rule_name = StringField('規則名稱',
                           validators=[DataRequired(message='請輸入規則名稱'),
                                     Length(max=200)])
    description = TextAreaField('描述',
                               validators=[Optional(),
                                         Length(max=500)])
    priority = StringField('優先級',
                          validators=[DataRequired(message='請輸入優先級')],
                          render_kw={'type': 'number', 'min': '0', 'value': '0'})
    conditions = TextAreaField('匹配條件 (JSON 格式)',
                              validators=[DataRequired(message='請輸入匹配條件')],
                              render_kw={'rows': 8, 'placeholder': '請輸入 JSON 格式的匹配條件'})
    actions = TextAreaField('操作 (JSON 格式)',
                           validators=[DataRequired(message='請輸入操作設定')],
                           render_kw={'rows': 8, 'placeholder': '請輸入 JSON 格式的操作設定'})
    enabled = BooleanField('啟用', default=True)
    submit = SubmitField('儲存')


class MongoDBInstanceForm(FlaskForm):
    """MongoDB 實例表單"""
    instance_name = StringField('實例名稱',
                               validators=[DataRequired(message='請輸入實例名稱'),
                                         Length(max=200)])
    description = TextAreaField('描述',
                               validators=[Optional(),
                                         Length(max=500)])
    host = StringField('主機位址',
                      validators=[DataRequired(message='請輸入主機位址'),
                                Length(max=100)])
    port = StringField('連接埠',
                      validators=[DataRequired(message='請輸入連接埠')],
                      render_kw={'type': 'number', 'min': '1', 'max': '65535', 'value': '27017'})
    username = StringField('使用者名稱',
                          validators=[DataRequired(message='請輸入使用者名稱'),
                                    Length(max=100)])
    password = StringField('密碼',
                          validators=[DataRequired(message='請輸入密碼'),
                                    Length(max=200)],
                          render_kw={'type': 'password'})
    database = StringField('資料庫名稱',
                          validators=[DataRequired(message='請輸入資料庫名稱'),
                                    Length(max=100)])
    collection = StringField('集合名稱',
                            validators=[Optional(),
                                      Length(max=100)],
                            render_kw={'value': 'recordings'})
    auth_source = StringField('認證資料庫',
                             validators=[Optional(),
                                       Length(max=100)],
                             render_kw={'value': 'admin'})
    enabled = BooleanField('啟用', default=True)
    submit = SubmitField('儲存')
