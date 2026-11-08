"""List exercises and a bounded interpreter for their supported Python syntax."""

import ast
import math
import operator


EXERCISE = {
    "title": "计算列表平均值",
    "description": "补全 average(nums)，返回非空整数列表的算术平均值。"
    "例如 [10, 20, 30, 40] 应返回 25.0。",
    "starter_code": "def average(nums):\n    total = sum(nums)\n    return total / (len(nums) - 1)\n",
}
EXERCISES = {
    "average": {**EXERCISE, "signature": "def average(nums):"},
    "sum": {
        "title": "计算列表总和",
        "description": "补全 list_sum(nums)，返回整数列表中所有元素相加的结果。"
        "例如 [-5, 2, 0] 应返回 -3，空列表应返回 0。",
        "starter_code": "def list_sum(nums):\n    return len(nums)\n",
        "signature": "def list_sum(nums):",
    },
    "count": {
        "title": "计算列表元素个数",
        "description": "补全 list_count(nums)，返回整数列表中元素的个数。"
        "例如 [4, 4, 0] 应返回 3，空列表应返回 0。",
        "starter_code": "def list_count(nums):\n    return sum(nums)\n",
        "signature": "def list_count(nums):",
    },
}
EXERCISE_CASES = {
    "average": (
        ("C01", (10, 20, 30, 40), 25.0),
        ("C02", (-6, -3, 0), -3.0),
        ("C03", (1, 2), 1.5),
        ("C04", (7,), 7.0),
    ),
    "sum": (
        ("S01", (3, 5, 2), 10),
        ("S02", (-5, 2, 0), -3),
        ("S03", (), 0),
        ("S04", (7,), 7),
    ),
    "count": (
        ("N01", (4, 4, 0), 3),
        ("N02", (-5, 2, 0), 3),
        ("N03", (), 0),
        ("N04", (7,), 1),
    ),
}
HINT_LOCATION = {
    "zero_division": "用这个输入检查第 {line} 行的除法，追踪右侧表达式如何得到 0。",
    "numeric_range": "检查第 {line} 行的中间结果，看哪一步将数值放大。",
    "wrong_result": "从第 {line} 行的返回表达式开始，回查参与计算的变量。",
}
# One concept line and one next-step line per exercise and diagnosis kind. The three
# exercises fail for different reasons, so a sum hint may never call the element count the
# answer and a count hint may never call the value total the answer. Another exercise's
# quantity may appear only as something to compare the return value against, which is how a
# level-1 hint stays evidence-supported when the wrong result matches neither quantity.
HINT_GUIDANCE = {
    "average": {
        "zero_division": (
            "先数一数这个列表的元素个数，再想想它与除数的关系。",
            "把总和和实际元素个数分开核对，再用这个失败用例复测。",
        ),
        "numeric_range": (
            "圈出输入中的最小值和最大值，再判断平均值是否应落在两者之间。",
            "分别手算列表总和与元素个数，用这两个量检查各步运算。",
        ),
        "wrong_result": (
            "试着手算这个列表的总和，再数一数元素个数。",
            "把分子和分母分别写在纸上，确认分子等于列表总和、分母等于实际元素个数。",
        ),
    },
    "sum": {
        "zero_division": (
            "求和只要把元素相加，你的式子里为什么出现了除法？",
            "去掉除法，把返回值改成各元素相加的结果，再用这个失败用例复测。",
        ),
        "numeric_range": (
            "圈出输入中的最小值和最大值，估一估这组数相加最多能到多少。",
            "手算这组数的相加结果，看你的式子算出的结果比它大了多少倍，再回到相加那一步。",
        ),
        "wrong_result": (
            "手算这个列表的相加结果，再数一数元素个数，看返回值更接近哪一个。",
            "让返回值表示元素的总和。负数也参与相加，空列表的总和是 0。",
        ),
    },
    "count": {
        "zero_division": (
            "数个数只要数位置，你的式子里为什么出现了除法？",
            "去掉除法，直接数出位置有几个，再用这个失败用例复测。",
        ),
        "numeric_range": (
            "先数一数这组输入一共占几个位置，再判断返回值该有多大。",
            "手数这组输入的元素个数，看你的式子算出的结果比它大了多少倍，再回到计数那一步。",
        ),
        "wrong_result": (
            "先数一数这个列表的元素个数，再算出它的相加结果，看返回值更接近哪一个。",
            "让返回值表示元素个数。相同的值分别计数，0 也占一个位置。",
        ),
    },
}
# Additional local curriculum; the original three fixtures and hint wording stay intact.
_NEW_EXERCISES = {
    "double_sum": ("每个元素翻倍后求和", "将整数列表中每个值翻倍后求和；空列表返回 0。", "sum(nums) * 2", "sum(nums)", "区分每项乘倍数与总和加固定值。", ((3, -1, 0), (), (7,), (-4, -2))),
    "shifted_average": ("每项加二后的平均值", "非空整数列表中每个值加 2，返回新列表的平均值。", "sum(nums) / len(nums) + 2", "(sum(nums) + 2) / len(nums)", "每项加相同数，平均值也增加这个数。", ((2, 6), (-4, 0, 1), (7,), (0, 0))),
    "total_with_fee": ("加上一次固定费用", "返回整数金额列表的总和加上一次固定费用 5；空列表也收取该费用。", "sum(nums) + 5", "sum(nums) + len(nums) * 5", "区分只收一次的固定费用与按件计费。", ((2, 6), (), (7,), (-4, 0, 1))),
    "pair_count": ("每件物品两张标签", "列表中每个元素需要两张标签，返回标签总数；重复值也分别计数。", "len(nums) * 2", "sum(nums) * 2", "计数关注元素位置，不受元素的值影响。", ((4, 4, 0), (), (7,), (-4, 0, 1))),
    "average_with_zero": ("追加一个零后求平均值", "在整数列表末尾追加一个 0，返回新列表的平均值；空输入的结果为 0。", "sum(nums) / (len(nums) + 1)", "sum(nums) / len(nums)", "追加零不改变总和，但会增加元素个数。", ((2, 6), (), (7,), (-4, 0, 1))),
}
for _id, (_title, _description, _correct, _buggy, _goal, _inputs) in _NEW_EXERCISES.items():
    EXERCISES[_id] = {
        "title": _title, "description": _description,
        "signature": f"def {_id}(nums):",
        "starter_code": f"def {_id}(nums):\n    return {_buggy}\n",
        "learning_goal": _goal,
    }
# Expected values are fixed fixtures, never evaluated from source strings.
EXERCISE_CASES.update({
    "double_sum": (("DS01", (3, -1, 0), 4), ("DS02", (), 0), ("DS03", (7,), 14), ("DS04", (-4, -2), -12)),
    "shifted_average": (("SA01", (2, 6), 6.0), ("SA02", (-4, 0, 1), 1.0), ("SA03", (7,), 9.0), ("SA04", (0, 0), 2.0)),
    "total_with_fee": (("TF01", (2, 6), 13), ("TF02", (), 5), ("TF03", (7,), 12), ("TF04", (-4, 0, 1), 2)),
    "pair_count": (("PC01", (4, 4, 0), 6), ("PC02", (), 0), ("PC03", (7,), 2), ("PC04", (-4, 0, 1), 6)),
    "average_with_zero": (("AZ01", (2, 6), 8 / 3), ("AZ02", (), 0.0), ("AZ03", (7,), 3.5), ("AZ04", (-4, 0, 1), -0.75)),
})
for _id in _NEW_EXERCISES:
    HINT_GUIDANCE[_id] = {
        "wrong_result": (EXERCISES[_id]["learning_goal"], "按题意手算这个输入，再逐步检查返回表达式。"),
        "zero_division": ("这个输入使除数变成了 0。", "分别写出应有的个数和实际除数，再核对题目的输入范围。"),
        "numeric_range": ("中间结果超过了支持的数值范围。", "手算目标数值，再检查哪一步乘除让你的式子算出的结果放大。"),
    }
EXERCISES["average"]["learning_goal"] = "用总和与实际元素个数计算平均值。"
EXERCISES["sum"]["learning_goal"] = "将正负数相加，理解空列表的总和为 0。"
EXERCISES["count"]["learning_goal"] = "按位置计数，重复值与零都占一个位置。"

MAX_SOURCE_LENGTH = 4000
MAX_AST_NODES = 120
MAX_VALUE = 10**12
BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
LIST_FUNCTIONS = {"sum": sum, "len": len}


class SubmissionError(Exception):
    def __init__(self, kind, message, line=None):
        super().__init__(message)
        self.kind = kind
        self.line = line

    def diagnosis(self):
        return {"kind": self.kind, "message": str(self), "line": self.line}


def unsupported(node, message):
    return SubmissionError("unsupported", message, getattr(node, "lineno", None))


def validate_expression(node, names):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        if abs(node.value) <= MAX_VALUE:
            return
        raise unsupported(node, "数字常量的绝对值须小于或等于 10¹²。")
    if isinstance(node, ast.Name):
        if node.id in names:
            return
        raise unsupported(node, "请先为数值变量赋值，列表参数可传给 sum 或 len。")
    if isinstance(node, ast.BinOp) and type(node.op) in BINARY_OPERATORS:
        validate_expression(node.left, names)
        validate_expression(node.right, names)
        return
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPERATORS:
        validate_expression(node.operand, names)
        return
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in LIST_FUNCTIONS
        and not node.keywords
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "nums"
    ):
        return
    raise unsupported(node, "表达式仅支持数字、已赋值变量、四则运算以及 sum(nums) 和 len(nums)。")


def parse_submission(code, signature="def average(nums):"):
    if len(code) > MAX_SOURCE_LENGTH:
        raise unsupported(None, f"代码长度上限为 {MAX_SOURCE_LENGTH} 个字符。")
    try:
        module = ast.parse(code)
    except SyntaxError as error:
        raise SubmissionError("syntax", "请检查 Python 语法、括号、冒号和缩进。", error.lineno) from None
    except ValueError:
        raise SubmissionError("syntax", "代码含有无效字符。") from None
    except RecursionError:
        raise unsupported(None, "表达式嵌套过深，请简化代码。") from None
    if sum(1 for _ in ast.walk(module)) > MAX_AST_NODES:
        focus = "计算平均值" if signature == EXERCISES["average"]["signature"] else "完成本题"
        raise unsupported(None, f"代码结构过长，请保留{focus}所需的步骤。")
    if len(module.body) != 1 or not isinstance(module.body[0], ast.FunctionDef):
        raise unsupported(module.body[0] if module.body else None, f"请只提交一个 {signature} 函数。")

    function = module.body[0]
    args = function.args
    if (
        f"def {function.name}(nums):" != signature
        or function.decorator_list
        or function.returns is not None
        or args.posonlyargs
        or args.kwonlyargs
        or args.vararg is not None
        or args.kwarg is not None
        or args.defaults
        or len(args.args) != 1
        or args.args[0].arg != "nums"
        or args.args[0].annotation is not None
        or getattr(function, "type_params", ())
    ):
        raise unsupported(function, f"函数定义请使用 {signature}。")

    names = set()
    for statement in function.body[:-1]:
        if not (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id not in ("nums", "sum", "len", "__debug__")
        ):
            raise unsupported(statement, "返回之前只支持给单个普通数值变量赋值。")
        validate_expression(statement.value, names)
        names.add(statement.targets[0].id)

    final_statement = function.body[-1]
    if not isinstance(final_statement, ast.Return) or final_statement.value is None:
        raise unsupported(final_statement, "函数最后一行需用 return 返回计算结果。")
    validate_expression(final_statement.value, names)
    return function.body


def evaluate_expression(node, values, nums):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return values[node.id]
    if isinstance(node, ast.Call):
        return LIST_FUNCTIONS[node.func.id](nums)
    if isinstance(node, ast.UnaryOp):
        return UNARY_OPERATORS[type(node.op)](evaluate_expression(node.operand, values, nums))

    left = evaluate_expression(node.left, values, nums)
    right = evaluate_expression(node.right, values, nums)
    try:
        result = BINARY_OPERATORS[type(node.op)](left, right)
    except ZeroDivisionError:
        raise SubmissionError("zero_division", "此处的除数为 0。", node.lineno) from None
    if not abs(result) <= MAX_VALUE:
        raise SubmissionError("numeric_range", "计算结果超出了此练习支持的数值范围。", node.lineno)
    return result


def evaluate_case(statements, nums):
    values = {}
    for statement in statements[:-1]:
        values[statement.targets[0].id] = evaluate_expression(statement.value, values, nums)
    return evaluate_expression(statements[-1].value, values, nums)


def feedback(diagnosis, case, exercise_id="average"):
    reference = f"用例 {case['id']} 的输入为 {case['input']}。"
    # Syntax and unsupported-construct diagnoses have no case-level sentence of their own,
    # so they read as a plain wrong result here, exactly as before.
    kind = diagnosis["kind"] if diagnosis["kind"] in HINT_LOCATION else "wrong_result"
    concept, next_step = HINT_GUIDANCE.get(exercise_id, HINT_GUIDANCE["average"])[kind]
    return [reference + concept, HINT_LOCATION[kind].format(line=diagnosis["line"]), next_step]


def check_submission(code: str, exercise_id: str = "average") -> dict:
    exercise = EXERCISES[exercise_id]
    cases = EXERCISE_CASES[exercise_id]
    result = {"status": "invalid", "passed": 0, "total": len(cases),
              "cases": [], "diagnosis": None, "hints": []}
    try:
        statements = parse_submission(code, exercise["signature"])
    except SubmissionError as error:
        result["diagnosis"] = error.diagnosis()
        return result

    for case_id, nums, expected in cases:
        case = {"id": case_id, "input": list(nums), "expected": expected, "actual": None}
        try:
            actual = evaluate_case(statements, nums)
            case["actual"] = actual
            if isinstance(expected, int):
                matches = actual == expected
            else:
                matches = math.isclose(actual, expected, abs_tol=1e-9)
            case["status"] = "passed" if matches else "failed"
            diagnosis = {
                "kind": "wrong_result",
                "message": f"用例 {case_id} 的返回值与预期不同。",
                "line": statements[-1].lineno,
            }
        except SubmissionError as error:
            case["status"] = "error"
            case["error"] = str(error)
            diagnosis = error.diagnosis()

        result["cases"].append(case)
        if case["status"] == "passed":
            result["passed"] += 1
        elif result["diagnosis"] is None:
            result["diagnosis"] = diagnosis
            result["hints"] = feedback(diagnosis, case, exercise_id)

    result["status"] = "passed" if result["passed"] == result["total"] else "failed"
    if exercise_id == "average" and result["status"] == "failed":
        actual_values = {case["actual"] for case in result["cases"]}
        if None not in actual_values and len(actual_values) == 1:
            line = result["diagnosis"]["line"]
            result["hints"][1] = f"不同输入的返回值相同。检查第 {line} 行的返回值是否随输入改变。"
    return result
