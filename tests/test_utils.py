import pytest

from utils.utils import convert_date_jp_to_iso


# 使用 pytest.mark.parametrize 可以一次测试多种情况，让测试更高效
@pytest.mark.parametrize(
    "input_date, expected_output",
    [
        # 1. 标准日文格式
        ("2023年10月26日", "2023-10-26"),
        # 2. 斜杠分割格式
        ("2024/01/05", "2024-01-05"),
        # 3. 横杠分割格式
        ("2022-12-31", "2022-12-31"),
        # 4. 带有时间戳的格式
        ("2021/07/30 00:00", "2021-07-30"),
        # 5. 单数字的月份和日期
        ("2023年1月1日", "2023-01-01"),
        # 6. 无效输入
        ("无效日期", None),
        # 7. 空字符串输入
        ("", None),
        # 8. None 输入
        (None, None),
    ],
)
def test_convert_date_jp_to_iso(input_date, expected_output):
    """
    测试 convert_date_jp_to_iso 函数是否能正确转换各种格式的日期。
    """
    # 调用被测试的函数
    actual_output = convert_date_jp_to_iso(input_date)
    # 断言（assert）函数的结果是否和我们预期的结果一致
    assert actual_output == expected_output
