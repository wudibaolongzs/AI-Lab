"""Bounded AST interpreter for data-driven beginner exercises."""
import ast
import math
import operator

LIMIT = 10**12
CALLS = {'sum', 'len', 'abs', 'int', 'str'}
BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
          ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}
COMPARE = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
           ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
           ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}


class SubmissionError(Exception):
    def __init__(self, kind, message, node=None):
        super().__init__(message)
        self.kind, self.line = kind, getattr(node, 'lineno', None)

    def diagnosis(self):
        return {'kind': self.kind, 'message': str(self), 'line': self.line}


def reject(node=None, message='此练习暂不支持这种 Python 写法。'):
    raise SubmissionError('unsupported', message, node)


def bounded(value, node=None):
    if type(value) is bool:
        return value
    if type(value) in (int, float):
        if abs(value) > LIMIT or not math.isfinite(value):
            raise SubmissionError('numeric_range', '数值超出了支持范围。', node)
    elif type(value) is str:
        if len(value) > 4000:
            reject(node, '字符串不能超过 4000 个字符。')
    elif type(value) in (list, tuple):
        if len(value) > 1000:
            reject(node, '序列不能超过 1000 项。')
        for item in value:
            if type(item) not in (int, float, bool, str):
                reject(node, '暂不支持嵌套序列。')
            bounded(item, node)
    else:
        reject(node, '暂不支持这种数据类型。')
    return value


def typed(value, kind):
    if kind == 'number':
        return type(value) in (int, float)
    if kind == 'integer':
        return type(value) is int
    if kind == 'boolean':
        return type(value) is bool
    if kind == 'string':
        return type(value) is str
    if kind == 'number_list':
        return type(value) is list and all(type(x) in (int, float) for x in value)
    return False


def validate_expr(node, names):
    if isinstance(node, ast.Constant):
        bounded(node.value, node)
    elif isinstance(node, ast.Name):
        if node.id not in names:
            reject(node, '变量未定义或尚未赋值：' + node.id)
    elif isinstance(node, (ast.List, ast.Tuple)):
        for item in node.elts:
            validate_expr(item, names)
    elif isinstance(node, ast.BinOp) and type(node.op) in BINARY:
        validate_expr(node.left, names)
        validate_expr(node.right, names)
    elif isinstance(node, ast.UnaryOp) and type(node.op) in (ast.Not, ast.UAdd, ast.USub):
        validate_expr(node.operand, names)
    elif isinstance(node, ast.BoolOp) and type(node.op) in (ast.And, ast.Or):
        for item in node.values:
            validate_expr(item, names)
    elif isinstance(node, ast.Compare) and all(type(op) in COMPARE for op in node.ops):
        for item in [node.left] + node.comparators:
            validate_expr(item, names)
    elif isinstance(node, ast.IfExp):
        for item in (node.test, node.body, node.orelse):
            validate_expr(item, names)
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in CALLS and len(node.args) == 1 and not node.keywords:
        validate_expr(node.args[0], names)
    elif isinstance(node, ast.Subscript):
        validate_expr(node.value, names)
        items = (node.slice.lower, node.slice.upper, node.slice.step) if isinstance(node.slice, ast.Slice) else (node.slice,)
        for item in items:
            if item is not None:
                literal = item.operand if isinstance(item, ast.UnaryOp) and isinstance(item.op, (ast.UAdd, ast.USub)) else item
                if not isinstance(literal, ast.Constant) or type(literal.value) is not int:
                    reject(item, '索引和切片边界请直接填写整数。')
                validate_expr(item, names)
    else:
        reject(node)


def validate_block(body, names):
    names = set(names)
    for node in body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            validate_expr(node.value, names)
            name = node.targets[0].id
            if name in CALLS:
                reject(node, '不能给内置函数名赋值。')
            names.add(name)
        elif isinstance(node, ast.Return) and node.value is not None:
            validate_expr(node.value, names)
        elif isinstance(node, ast.If):
            validate_expr(node.test, names)
            names |= validate_block(node.body, names) & validate_block(node.orelse, names)
        else:
            reject(node)
    return names


def parse(code, spec):
    if not isinstance(code, str) or len(code) > 4000:
        reject(message='代码不能超过 4000 个字符。')
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError) as error:
        raise SubmissionError('syntax', '请检查语法、括号、冒号和缩进。') from error
    nodes = list(ast.walk(tree))
    if len(nodes) > 160:
        reject(message='代码结构过长，请简化到 160 个语法节点以内。')
    pending = [(tree, 0)]
    while pending:
        node, depth = pending.pop()
        if depth > 16:
            reject(node, '代码嵌套过深，请控制在 16 层以内。')
        pending.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        reject(message='请只提交一个函数。')
    fn = tree.body[0]
    args = fn.args
    expected_name = spec['signature'].split('(')[0].split()[-1]
    if fn.name != expected_name or [a.arg for a in args.args] != [p['name'] for p in spec['parameters']] or fn.decorator_list or fn.returns or args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or args.defaults or args.kw_defaults or any(a.annotation for a in args.args):
        reject(fn, '函数名和参数须与题目要求一致。')
    if any(a.arg in CALLS for a in args.args):
        reject(fn)
    validate_block(fn.body, {a.arg for a in args.args})
    return fn.body


class Runtime:
    def __init__(self, values):
        self.values, self.steps, self.line = values, 0, None

    def expr(self, node):
        self.steps += 1
        if self.steps > 1000:
            reject(node, '执行超过 1000 步，请简化代码。')
        try:
            return bounded(self._expr(node), node)
        except SubmissionError:
            raise
        except ZeroDivisionError:
            raise SubmissionError('zero_division', '此处的除数为 0。', node) from None
        except (TypeError, ValueError, IndexError, OverflowError, KeyError):
            raise SubmissionError('runtime', '这些值不能进行此运算，请检查类型和索引。', node) from None

    def _expr(self, n):
        if isinstance(n, ast.Constant): return n.value
        if isinstance(n, ast.Name): return self.values[n.id]
        if isinstance(n, (ast.List, ast.Tuple)): return [self.expr(x) for x in n.elts]
        if isinstance(n, ast.IfExp): return self.expr(n.body if self.expr(n.test) else n.orelse)
        if isinstance(n, ast.BoolOp):
            for item in n.values:
                value = self.expr(item)
                if (isinstance(n.op, ast.And) and not value) or (isinstance(n.op, ast.Or) and value): return value
            return value
        if isinstance(n, ast.UnaryOp):
            v = self.expr(n.operand)
            if isinstance(n.op, ast.Not): return not v
            if type(v) not in (int, float): raise TypeError()
            return v if isinstance(n.op, ast.UAdd) else -v
        if isinstance(n, ast.Compare):
            left = self.expr(n.left)
            for op, item in zip(n.ops, n.comparators):
                right = self.expr(item)
                if not COMPARE[type(op)](left, right): return False
                left = right
            return True
        if isinstance(n, ast.BinOp):
            a, b = self.expr(n.left), self.expr(n.right)
            if type(a) in (int, float) and type(b) in (int, float): return BINARY[type(n.op)](a, b)
            if isinstance(n.op, ast.Add) and type(a) is str and type(b) is str:
                if len(a) + len(b) > 4000: reject(n)
                return a + b
            if isinstance(n.op, ast.Mult):
                s, count = (a, b) if type(a) is str else (b, a)
                if type(s) is str and type(count) is int:
                    if len(s) * max(count, 0) > 4000: reject(n)
                    return s * count
            raise TypeError()
        if isinstance(n, ast.Subscript):
            value = self.expr(n.value)
            index = n.slice
            if isinstance(index, ast.Slice): index = slice(*(self.expr(x) if x is not None else None for x in (index.lower, index.upper, index.step)))
            else: index = self.expr(index)
            return value[index]
        if isinstance(n, ast.Call):
            value = self.expr(n.args[0]); name = n.func.id
            if name == 'sum':
                if type(value) is not list or not all(type(x) in (int, float) for x in value): raise TypeError()
                return sum(value)
            if name == 'len':
                if type(value) not in (str, list, tuple): raise TypeError()
                return len(value)
            if name == 'abs':
                if type(value) not in (int, float): raise TypeError()
                return abs(value)
            if name == 'int': return int(value)
            if name == 'str': return str(value)
        reject(n)

    def block(self, body):
        for node in body:
            self.steps += 1
            if self.steps > 1000: reject(node)
            if isinstance(node, ast.Assign): self.values[node.targets[0].id] = self.expr(node.value)
            elif isinstance(node, ast.Return):
                self.line = node.lineno
                return True, self.expr(node.value)
            else:
                returned, value = self.block(node.body if self.expr(node.test) else node.orelse)
                if returned: return True, value
        return False, None


def check(code, spec):
    result = {'status': 'invalid', 'passed': 0, 'total': len(spec['cases']), 'cases': [], 'diagnosis': None, 'hints': []}
    try:
        body = parse(code, spec)
    except SubmissionError as error:
        result['diagnosis'] = error.diagnosis()
        return result
    for case in spec['cases']:
        row = {'id': case['id'], 'input': case['args'], 'expected': case['expected'], 'actual': None}
        runtime = Runtime(dict(zip((p['name'] for p in spec['parameters']), case['args'])))
        try:
            if len(case['args']) != len(spec['parameters']): reject(message='用例参数数量不正确。')
            for value, parameter in zip(case['args'], spec['parameters']):
                if not typed(value, parameter['type']): reject(message='用例输入类型不正确。')
                bounded(value)
            returned, actual = runtime.block(body)
            if not returned: raise SubmissionError('runtime', '函数未返回结果，请检查 return 和分支。')
            row['actual'] = actual
            matches = typed(actual, spec['return_type']) and (math.isclose(actual, case['expected'], rel_tol=1e-9, abs_tol=1e-9) if spec['return_type'] == 'number' else actual == case['expected'])
            row['status'] = 'passed' if matches else 'failed'
            diagnosis = {'kind': 'wrong_result', 'message': '返回结果与预期不符。', 'line': runtime.line}
        except SubmissionError as error:
            row['status'], row['error'], diagnosis = 'error', str(error), error.diagnosis()
        result['cases'].append(row)
        if row['status'] == 'passed': result['passed'] += 1
        elif result['diagnosis'] is None:
            result['diagnosis'] = diagnosis
            result['hints'] = list(spec['hints'])
            result['hints'][0] = f"用例 {case['id']} 的输入为 {case['args']}。" + result['hints'][0]
    result['status'] = 'passed' if result['passed'] == result['total'] else 'failed'
    return result
