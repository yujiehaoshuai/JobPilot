"""提供各类数据模型共用的校验规则，不处理具体业务。"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

# 先去掉首尾空白，再检查内容；只包含空格的字符串也视为空值。
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DomainModel(BaseModel):
    """统一校验输入数据，避免拼错字段名或修改后出现无效值。

    未声明的字段会报错，字符串会去掉首尾空白。
    创建对象和给已有字段重新赋值时，都会执行校验。
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )
