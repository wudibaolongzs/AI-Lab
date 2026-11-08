"""List exercises and a bounded interpreter for their supported Python syntax."""

import ast
import math
import operator


from collections.abc import Mapping
from pathlib import Path
import json
import question_bank
import bank_engine

_LEGACY = json.loads(Path(__file__).with_name("data").joinpath("builtin.json").read_text(encoding="utf-8"))["problems"]
class _Catalog(Mapping):
    def __getitem__(self, key):
        for problem in question_bank.public_exercises():
            if problem["id"] == key:
                return problem
        raise KeyError(key)
    def items(self):
        return ((problem["id"], problem) for problem in question_bank.public_exercises())
    def values(self):
        return iter(question_bank.public_exercises())
    def __iter__(self):
        return iter([problem["id"] for problem in question_bank.public_exercises()])
    def __len__(self):
        return len(question_bank.public_exercises())

EXERCISES = _Catalog()
EXERCISE = {key: _LEGACY[0][key] for key in ("title", "description", "starter_code")}
EXERCISE_CASES = {p["id"]: tuple((c["id"], tuple(c["args"][0]), c["expected"]) for c in p["cases"]) for p in _LEGACY}
HINT_GUIDANCE = {p["id"]: {kind: tuple(lines) for kind, lines in p["legacy_guidance"].items()} for p in _LEGACY}
HINT_LOCATION = {'zero_division': '用这个输入检查第 {line} 行的除法，追踪右侧表达式如何得到 0。', 'numeric_range': '检查第 {line} 行的中间结果，看哪一步将数值放大。', 'wrong_result': '从第 {line} 行的返回表达式开始，回查参与计算的变量。'}
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
    specification = question_bank.get_problem(exercise_id)
    if specification["engine"] == "luogu_remote":
        return {"status":"invalid", "passed":0, "total":0, "cases":[], "hints":[],
                "diagnosis":{"kind":"unsupported", "message":"洛谷题需要远程评测。", "line":None}}
    if specification["engine"] != "legacy":
        return bank_engine.check(code, specification)
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
