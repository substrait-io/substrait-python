from typing import Optional
from antlr4 import InputStream, CommonTokenStream
from substrait.gen.antlr.SubstraitTypeLexer import SubstraitTypeLexer
from substrait.gen.antlr.SubstraitTypeParser import SubstraitTypeParser
from substrait.gen.proto.type_pb2 import Type


def _evaluate(x, values: dict):
    if isinstance(x, SubstraitTypeParser.BinaryExprContext):
        left = _evaluate(x.left, values)
        right = _evaluate(x.right, values)

        if x.op.text == "+":
            return left + right
        elif x.op.text == "-":
            return left - right
        elif x.op.text == "*":
            return left * right
        elif x.op.text == ">":
            return left > right
        elif x.op.text == ">=":
            return left >= right
        elif x.op.text == "<":
            return left < right
        elif x.op.text == "<=":
            return left <= right
        else:
            raise Exception(f"Unknown binary op {x.op.text}")
    elif isinstance(x, SubstraitTypeParser.LiteralNumberContext):
        return int(x.Number().symbol.text)
    elif isinstance(x, SubstraitTypeParser.ParameterNameContext):
        return values[x.Identifier().symbol.text]
    elif isinstance(x, SubstraitTypeParser.NumericParameterNameContext):
        return values[x.Identifier().symbol.text]
    elif isinstance(x, SubstraitTypeParser.ParenExpressionContext):
        return _evaluate(x.expr(), values)
    elif isinstance(x, SubstraitTypeParser.FunctionCallContext):
        exprs = [_evaluate(e, values) for e in x.expr()]
        func = x.Identifier().symbol.text
        if func == "min":
            return min(*exprs)
        elif func == "max":
            return max(*exprs)
        else:
            raise Exception(f"Unknown function {func}")
    elif isinstance(x, SubstraitTypeParser.TypeDefContext):
        scalar_type = x.scalarType()
        parametrized_type = x.parameterizedType()
        any_type = x.anyType()
        if scalar_type:
            nullability = (
                Type.NULLABILITY_NULLABLE if x.isnull else Type.NULLABILITY_REQUIRED
            )
            if isinstance(scalar_type, SubstraitTypeParser.I8Context):
                return Type(i8=Type.I8(nullability=nullability))
            elif isinstance(scalar_type, SubstraitTypeParser.I16Context):
                return Type(i16=Type.I16(nullability=nullability))
            elif isinstance(scalar_type, SubstraitTypeParser.I32Context):
                return Type(i32=Type.I32(nullability=nullability))
            elif isinstance(scalar_type, SubstraitTypeParser.I64Context):
                return Type(i64=Type.I64(nullability=nullability))
            elif isinstance(scalar_type, SubstraitTypeParser.Fp32Context):
                return Type(fp32=Type.FP32(nullability=nullability))
            elif isinstance(scalar_type, SubstraitTypeParser.Fp64Context):
                return Type(fp64=Type.FP64(nullability=nullability))
            elif isinstance(scalar_type, SubstraitTypeParser.BooleanContext):
                return Type(bool=Type.Boolean(nullability=nullability))
            else:
                raise Exception(f"Unknown scalar type {type(scalar_type)}")
        elif parametrized_type:
            if isinstance(parametrized_type, SubstraitTypeParser.DecimalContext):
                precision = _evaluate(parametrized_type.precision, values)
                scale = _evaluate(parametrized_type.scale, values)
                nullability = (
                    Type.NULLABILITY_NULLABLE
                    if parametrized_type.isnull
                    else Type.NULLABILITY_REQUIRED
                )
                return Type(
                    decimal=Type.Decimal(
                        precision=precision, scale=scale, nullability=nullability
                    )
                )
            raise Exception(f"Unknown parametrized type {type(parametrized_type)}")
        elif any_type:
            any_var = any_type.AnyVar()
            if any_var:
                return values[any_var.symbol.text]
            else:
                raise Exception()
        else:
            raise Exception(
                "either scalar_type, parametrized_type or any_type is required"
            )
    elif isinstance(x, SubstraitTypeParser.NumericExpressionContext):
        return _evaluate(x.expr(), values)
    elif isinstance(x, SubstraitTypeParser.TernaryContext):
        ifExpr = _evaluate(x.ifExpr, values)
        thenExpr = _evaluate(x.thenExpr, values)
        elseExpr = _evaluate(x.elseExpr, values)

        return thenExpr if ifExpr else elseExpr
    elif isinstance(x, SubstraitTypeParser.MultilineDefinitionContext):
        lines = zip(x.Identifier(), x.expr())

        for i, e in lines:
            identifier = i.symbol.text
            expr_eval = _evaluate(e, values)
            values[identifier] = expr_eval

        return _evaluate(x.finalType, values)
    elif isinstance(x, SubstraitTypeParser.TypeLiteralContext):
        return _evaluate(x.typeDef(), values)
    elif isinstance(x, SubstraitTypeParser.NumericLiteralContext):
        return int(str(x.Number()))
    else:
        raise Exception(f"Unknown token type {type(x)}")


def _parse(x: str):
    lexer = SubstraitTypeLexer(InputStream(x))
    stream = CommonTokenStream(lexer)
    parser = SubstraitTypeParser(stream)
    return parser.expr()


def evaluate(x: str, values: Optional[dict] = None):
    return _evaluate(_parse(x), values)
