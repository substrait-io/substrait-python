"""
Substrait Plan Pretty Printer

This module provides a concise pretty printer for Substrait plans and expressions
in a readable format using indentation, -> characters, and colors.
"""

import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.type_pb2 as stt


# ANSI color codes
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    WHITE = "\033[97m"


class PlanPrinter:
    """Concise pretty printer for Substrait plans and expressions"""

    def __init__(
        self, indent_size: int = 2, show_metadata: bool = False, use_colors: bool = None
    ):
        self.indent_size = indent_size
        self.show_metadata = show_metadata
        self.schema_names = []  # Track current schema column names

        # Auto-detect color support if not specified
        if use_colors is None:
            self.use_colors = self._detect_color_support()
        else:
            self.use_colors = use_colors

    def _detect_color_support(self) -> bool:
        """Detect if the terminal supports colors"""
        import os
        import sys

        # Check if we're in a terminal
        if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
            return False

        # Check environment variables
        if "NO_COLOR" in os.environ:
            return False

        # Check if we're in a dumb terminal
        term = os.environ.get("TERM", "")
        if term == "dumb":
            return False

        # Check if we're in Windows Command Prompt (which has limited color support)
        if os.name == "nt" and "ANSICON" not in os.environ:
            return False

        return True

    def _color(self, text: str, color: str) -> str:
        """Apply color to text if colors are enabled"""
        if self.use_colors:
            return f"{color}{text}{Colors.RESET}"
        return text

    def _indent_prefix(self, depth: int) -> str:
        """Generate indentation prefix with -> character"""
        if depth == 0:
            return ""
        return f"{Colors.GRAY if self.use_colors else ''}->{Colors.RESET if self.use_colors else ''}"

    def _get_indent_with_arrow(self, depth: int) -> str:
        """Get proper indentation with arrow for alignment"""
        base_indent = " " * (depth * self.indent_size)
        if depth == 0:
            return base_indent
        # Ensure consistent spacing: base_indent + arrow + space
        return f"{base_indent}{self._indent_prefix(depth)} "

    def _resolve_field_name(self, field_index: int) -> str:
        """Resolve a field index to a column name if available"""
        if 0 <= field_index < len(self.schema_names):
            return self.schema_names[field_index]
        return f"field_{field_index}"

    def print_plan(self, plan: stp.Plan) -> None:
        """Print a Substrait plan to a string"""
        output = self.stringify_plan(plan)
        print(output)

    def print_expression(self, expression: stalg.Expression) -> None:
        """Print a Substrait expression to a string"""
        output = self.stringify_expression(expression)
        print(output)

    def stringify_plan(self, plan: stp.Plan) -> str:
        """Stringify a Substrait plan"""
        import io

        stream = io.StringIO()
        self._stream_plan(plan, stream, 0)
        return stream.getvalue()

    def stringify_expression(self, expression: stalg.Expression) -> str:
        """Stringify a Substrait expression"""
        import io

        stream = io.StringIO()
        self._stream_expression(expression, stream, 0)
        return stream.getvalue()

    def _stream_plan(self, plan: stp.Plan, stream, depth: int):
        """Print a plan concisely"""
        indent = " " * (depth * self.indent_size)

        # Print relations (the main content)
        for i, rel in enumerate(plan.relations):
            if i > 0:
                stream.write(f"{indent}{self._indent_prefix(depth)}\n")
            self._stream_relation(rel, stream, depth)

    def _stream_relation(self, rel: stp.PlanRel, stream, depth: int):
        """Print a plan relation concisely"""

        if rel.HasField("root"):
            self._stream_rel_root(rel.root, stream, depth)
        elif rel.HasField("rel"):
            self._stream_rel(rel.rel, stream, depth)

    def _stream_rel_root(self, root: stalg.RelRoot, stream, depth: int):
        """Print a relation root concisely"""
        indent = " " * (depth * self.indent_size)

        # Show output names if they exist
        if root.names:
            stream.write(
                f"{indent}{self._color('output:', Colors.CYAN)} {self._color(list(root.names), Colors.YELLOW)}\n"
            )

        # Print the input relation
        self._stream_rel(root.input, stream, depth)

    def _stream_rel(self, rel: stalg.Rel, stream, depth: int):
        """Print a relation concisely"""
        indent = " " * (depth * self.indent_size)

        if rel.HasField("read"):
            self._stream_read_rel(rel.read, stream, depth)
        elif rel.HasField("filter"):
            self._stream_filter_rel(rel.filter, stream, depth)
        elif rel.HasField("project"):
            self._stream_project_rel(rel.project, stream, depth)
        elif rel.HasField("aggregate"):
            self._stream_aggregate_rel(rel.aggregate, stream, depth)
        elif rel.HasField("sort"):
            self._stream_sort_rel(rel.sort, stream, depth)
        elif rel.HasField("join"):
            self._stream_join_rel(rel.join, stream, depth)
        elif rel.HasField("cross"):
            self._stream_cross_rel(rel.cross, stream, depth)
        elif rel.HasField("fetch"):
            self._stream_fetch_rel(rel.fetch, stream, depth)
        elif rel.HasField("extension_single"):
            self._stream_extension_single_rel(rel.extension_single, stream, depth)
        elif rel.HasField("extension_multi"):
            self._stream_extension_multi_rel(rel.extension_multi, stream, depth)
        else:
            stream.write(f"{indent}<unknown_relation>\n")

    def _stream_read_rel(self, read: stalg.ReadRel, stream, depth: int):
        """Print a read relation concisely"""
        indent = " " * (depth * self.indent_size)

        if read.HasField("named_table"):
            table_names = list(read.named_table.names)
            stream.write(
                f"{indent}{self._color('read:', Colors.GREEN)} {self._color(table_names[0] if len(table_names) == 1 else table_names, Colors.YELLOW)}\n"
            )
        elif read.HasField("virtual_table"):
            stream.write(
                f"{indent}{self._color('read:', Colors.GREEN)} {self._color('virtual_table', Colors.YELLOW)}\n"
            )
            if read.virtual_table.values:
                stream.write(
                    f"{self._get_indent_with_arrow(depth + 1)}{self._color('values:', Colors.BLUE)} {self._color(len(read.virtual_table.values), Colors.YELLOW)}\n"
                )
                # Show the actual values, not just count
                for i, value in enumerate(read.virtual_table.values):
                    # Handle struct values properly
                    if hasattr(value, "fields"):
                        stream.write(
                            f"{self._get_indent_with_arrow(depth + 2)}value[{i}]: "
                        )
                        self._stream_struct_literal(
                            value, stream, depth + 2, inline=True
                        )
                    else:
                        stream.write(
                            f"{self._get_indent_with_arrow(depth + 2)}value[{i}]: "
                        )
                        self._stream_literal_value(value, stream, depth + 2)

        if read.HasField("base_schema"):
            # Capture schema names for field resolution
            self.schema_names = list(read.base_schema.names)
            if self.show_metadata:
                stream.write(
                    f"{self._get_indent_with_arrow(depth + 1)}{self._color('schema:', Colors.BLUE)} {self._color(self.schema_names, Colors.YELLOW)}\n"
                )

    def _stream_filter_rel(self, filter_rel: stalg.FilterRel, stream, depth: int):
        """Print a filter relation concisely"""
        indent = " " * (depth * self.indent_size)

        stream.write(f"{indent}{self._color('filter', Colors.RED)}\n")
        stream.write(
            f"{self._get_indent_with_arrow(depth + 1)}{self._color('input:', Colors.BLUE)}\n"
        )
        self._stream_rel(filter_rel.input, stream, depth + 1)
        stream.write(
            f"{self._get_indent_with_arrow(depth + 1)}{self._color('condition:', Colors.BLUE)}\n"
        )
        self._stream_expression(filter_rel.condition, stream, depth + 1)

    def _stream_project_rel(self, project: stalg.ProjectRel, stream, depth: int):
        """Print a project relation concisely"""
        indent = " " * (depth * self.indent_size)

        stream.write(f"{indent}{self._color('project', Colors.MAGENTA)}\n")
        stream.write(
            f"{self._get_indent_with_arrow(depth + 1)}{self._color('input:', Colors.BLUE)}\n"
        )
        self._stream_rel(project.input, stream, depth + 1)

        if project.expressions:
            stream.write(
                f"{self._get_indent_with_arrow(depth + 1)}{self._color('expr', Colors.BLUE)}({self._color(len(project.expressions), Colors.YELLOW)}):\n"
            )
            for i, expr in enumerate(project.expressions):
                stream.write(
                    f"{self._get_indent_with_arrow(depth + 2)}{self._color('expr', Colors.BLUE)}[{self._color(f'{i}', Colors.CYAN)}]:\n"
                )
                self._stream_expression(expr, stream, depth + 2)

    def _stream_aggregate_rel(self, aggregate: stalg.AggregateRel, stream, depth: int):
        """Print an aggregate relation concisely"""
        indent = " " * (depth * self.indent_size)

        stream.write(f"{indent}{self._color('aggregate', Colors.CYAN)}\n")
        stream.write(
            f"{self._get_indent_with_arrow(depth + 1)}{self._color('input:', Colors.BLUE)}\n"
        )
        self._stream_rel(aggregate.input, stream, depth + 1)

        if aggregate.groupings:
            stream.write(
                f"{self._get_indent_with_arrow(depth + 1)}{self._color('groups:', Colors.BLUE)} {self._color(len(aggregate.groupings), Colors.YELLOW)}\n"
            )

        if aggregate.measures:
            stream.write(
                f"{self._get_indent_with_arrow(depth + 1)}{self._color('measures:', Colors.BLUE)} {self._color(len(aggregate.measures), Colors.YELLOW)}\n"
            )

    def _stream_sort_rel(self, sort: stalg.SortRel, stream, depth: int):
        """Print a sort relation concisely"""
        indent = " " * (depth * self.indent_size)

        stream.write(
            f"{indent}{self._color('sort:', Colors.YELLOW)} {self._color(f'{len(sort.sorts)} fields', Colors.YELLOW)}\n"
        )
        stream.write(
            f"{self._get_indent_with_arrow(depth + 1)}{self._color('input:', Colors.BLUE)}\n"
        )
        self._stream_rel(sort.input, stream, depth + 1)

    def _stream_join_rel(self, join: stalg.JoinRel, stream, depth: int):
        """Print a join relation concisely"""
        indent = " " * (depth * self.indent_size)

        stream.write(
            f"{indent}{self._color('join:', Colors.GREEN)} {self._color(join.type, Colors.YELLOW)}\n"
        )
        stream.write(
            f"{self._get_indent_with_arrow(depth + 1)}{self._color('left:', Colors.BLUE)}\n"
        )
        self._stream_rel(join.left, stream, depth + 1)
        stream.write(
            f"{self._get_indent_with_arrow(depth + 1)}{self._color('right:', Colors.BLUE)}\n"
        )
        self._stream_rel(join.right, stream, depth + 1)

        if join.HasField("expression"):
            stream.write(
                f"{self._get_indent_with_arrow(depth + 1)}{self._color('on:', Colors.BLUE)}\n"
            )
            self._stream_expression(join.expression, stream, depth + 1)

    def _stream_cross_rel(self, cross: stalg.CrossRel, stream, depth: int):
        """Print a cross relation concisely"""
        indent = " " * (depth * self.indent_size)

        stream.write(f"{indent}{self._color('cross', Colors.GREEN)}\n")
        stream.write(
            f"{self._get_indent_with_arrow(depth + 1)}{self._color('left:', Colors.BLUE)}\n"
        )
        self._stream_rel(cross.left, stream, depth + 1)
        stream.write(
            f"{self._get_indent_with_arrow(depth + 1)}{self._color('right:', Colors.BLUE)}\n"
        )
        self._stream_rel(cross.right, stream, depth + 1)

    def _stream_fetch_rel(self, fetch: stalg.FetchRel, stream, depth: int):
        """Print a fetch relation concisely"""
        indent = " " * (depth * self.indent_size)

        stream.write(
            f"{indent}{self._color('fetch:', Colors.YELLOW)} {self._color(f'offset={fetch.offset}, count={fetch.count}', Colors.YELLOW)}\n"
        )
        stream.write(
            f"{self._get_indent_with_arrow(depth + 1)}{self._color('input:', Colors.BLUE)}\n"
        )
        self._stream_rel(fetch.input, stream, depth + 1)

    def _stream_extension_single_rel(
        self, extension: stalg.ExtensionSingleRel, stream, depth: int
    ):
        """Print an extension single relation concisely"""
        indent = " " * (depth * self.indent_size)

        stream.write(f"{indent}{self._color('extension_single', Colors.MAGENTA)}\n")
        stream.write(
            f"{self._get_indent_with_arrow(depth + 1)}{self._color('input:', Colors.BLUE)}\n"
        )
        self._stream_rel(extension.input, stream, depth + 1)

        if extension.HasField("detail"):
            stream.write(
                f"{self._get_indent_with_arrow(depth + 1)}{self._color('detail:', Colors.BLUE)}\n"
            )
            # Try to unpack and display the detail if it's an Expression
            try:
                detail = extension.detail
                if detail.type_url and detail.value:
                    # Try to unpack as Expression
                    expression = stalg.Expression()
                    detail.Unpack(expression)
                    self._stream_expression(expression, stream, depth + 2)
                else:
                    stream.write(
                        f"{self._get_indent_with_arrow(depth + 2)}<binary_detail>\n"
                    )
            except Exception:
                stream.write(
                    f"{self._get_indent_with_arrow(depth + 2)}<unpackable_detail>\n"
                )

    def _stream_extension_multi_rel(
        self, extension: stalg.ExtensionMultiRel, stream, depth: int
    ):
        """Print an extension multi relation concisely"""
        indent = " " * (depth * self.indent_size)

        stream.write(f"{indent}{self._color('extension_multi', Colors.MAGENTA)}\n")

        if extension.inputs:
            stream.write(
                f"{self._get_indent_with_arrow(depth + 1)}{self._color('inputs', Colors.BLUE)}({self._color(len(extension.inputs), Colors.YELLOW)}):\n"
            )
            for i, input_rel in enumerate(extension.inputs):
                stream.write(
                    f"{self._get_indent_with_arrow(depth + 2)}{self._color('input', Colors.BLUE)}[{self._color(f'{i}', Colors.CYAN)}]:\n"
                )
                self._stream_rel(input_rel, stream, depth + 3)

        if extension.HasField("detail"):
            stream.write(
                f"{self._get_indent_with_arrow(depth + 1)}{self._color('detail:', Colors.BLUE)}\n"
            )
            # Try to unpack and display the detail if it's an Expression
            try:
                detail = extension.detail
                if detail.type_url and detail.value:
                    # Try to unpack as Expression
                    expression = stalg.Expression()
                    detail.Unpack(expression)
                    self._stream_expression(expression, stream, depth + 2)
                else:
                    stream.write(
                        f"{self._get_indent_with_arrow(depth + 2)}<binary_detail>\n"
                    )
            except Exception:
                stream.write(
                    f"{self._get_indent_with_arrow(depth + 2)}<unpackable_detail>\n"
                )

    def _stream_expression(self, expression: stalg.Expression, stream, depth: int):
        """Print an expression concisely"""
        indent = " " * (depth * self.indent_size)

        if expression.HasField("literal"):
            self._stream_literal(expression.literal, stream, depth)
        elif expression.HasField("selection"):
            self._stream_selection(expression.selection, stream, depth)
        elif expression.HasField("scalar_function"):
            self._stream_scalar_function(expression.scalar_function, stream, depth)
        elif expression.HasField("cast"):
            self._stream_cast(expression.cast, stream, depth)
        elif expression.HasField("if_then"):
            self._stream_if_then(expression.if_then, stream, depth)
        elif expression.HasField("window_function"):
            self._stream_window_function(expression.window_function, stream, depth)
        else:
            stream.write(f"{indent}<unknown_expression>\n")

    def _stream_literal(self, literal: stalg.Expression.Literal, stream, depth: int):
        """Print a literal concisely"""
        indent = " " * (depth * self.indent_size)

        if literal.HasField("boolean"):
            stream.write(f"{indent}literal: {literal.boolean}\n")
        elif literal.HasField("i32"):
            stream.write(f"{indent}literal: {literal.i32}\n")
        elif literal.HasField("i64"):
            stream.write(f"{indent}literal: {literal.i64}\n")
        elif literal.HasField("fp32"):
            stream.write(f"{indent}literal: {literal.fp32}\n")
        elif literal.HasField("fp64"):
            stream.write(f"{indent}literal: {literal.fp64}\n")
        elif literal.HasField("string"):
            stream.write(f'{indent}literal: "{literal.string}"\n')
        elif literal.HasField("date"):
            stream.write(f"{indent}literal: date={literal.date}\n")
        elif literal.HasField("timestamp"):
            stream.write(f"{indent}literal: timestamp={literal.timestamp}\n")
        elif literal.HasField("map"):
            stream.write(f"{indent}literal: map\n")
            self._stream_map_literal(literal.map, stream, depth + 1)
        else:
            stream.write(f"{indent}literal: <complex>\n")

    def _stream_selection(
        self, selection: stalg.Expression.FieldReference, stream, depth: int
    ):
        """Print a field reference concisely"""
        indent = " " * (depth * self.indent_size)

        if selection.HasField("direct_reference"):
            if selection.direct_reference.HasField("struct_field"):
                field_idx = selection.direct_reference.struct_field.field
                column_name = self._resolve_field_name(field_idx)
                stream.write(f"{indent}field: {column_name}\n")
            else:
                stream.write(f"{indent}field: direct\n")
        else:
            stream.write(f"{indent}field: root\n")

    def _stream_scalar_function(
        self, func: stalg.Expression.ScalarFunction, stream, depth: int
    ):
        """Print a scalar function concisely"""
        indent = " " * (depth * self.indent_size)

        stream.write(f"{indent}function: {func.function_reference}\n")

        # Print function arguments
        if func.arguments:
            stream.write(
                f"{self._get_indent_with_arrow(depth + 1)}{self._color('args', Colors.BLUE)}({self._color(len(func.arguments), Colors.YELLOW)}):\n"
            )
            for i, arg in enumerate(func.arguments):
                # Check if this is a nested scalar function
                if (
                    hasattr(arg, "value")
                    and arg.HasField("value")
                    and arg.value.HasField("scalar_function")
                ):
                    # Recursively expand nested scalar functions
                    stream.write(
                        f"{self._get_indent_with_arrow(depth + 2)}{self._color('args', Colors.BLUE)}[{self._color(f'{i}', Colors.CYAN)}]:\n"
                    )
                    self._stream_scalar_function(
                        arg.value.scalar_function, stream, depth + 3
                    )
                else:
                    # Always show the full recursive output for all argument types
                    stream.write(
                        f"{self._get_indent_with_arrow(depth + 2)}{self._color('args', Colors.BLUE)}[{self._color(f'{i}', Colors.CYAN)}]:\n"
                    )
                    self._stream_function_argument(arg, stream, depth + 3)

        # Print function options if present
        if func.options:
            stream.write(
                f"{self._get_indent_with_arrow(depth + 1)}{self._color('options', Colors.BLUE)}: {self._color(len(func.options), Colors.YELLOW)}\n"
            )
            for i, option in enumerate(func.options):
                # Handle preference as a list
                if hasattr(option, "preference") and option.preference:
                    pref_str = f"[{', '.join(str(p) for p in option.preference)}]"
                else:
                    pref_str = "[]"
                stream.write(
                    f"{self._get_indent_with_arrow(depth + 2)}{self._color(f'{i}', Colors.CYAN)}: {option.name}={pref_str}\n"
                )

        # Print output type if present
        if func.HasField("output_type"):
            stream.write(
                f"{self._get_indent_with_arrow(depth + 1)}{self._color('output_type', Colors.BLUE)}: {self._type_to_string(func.output_type)}\n"
            )

    def _stream_cast(self, cast: stalg.Expression.Cast, stream, depth: int):
        """Print a cast expression concisely"""
        indent = " " * (depth * self.indent_size)

        stream.write(f"{indent}cast\n")
        stream.write(
            f"{self._get_indent_with_arrow(depth + 1)}{self._color('input', Colors.BLUE)}:\n"
        )
        self._stream_expression(cast.input, stream, depth + 1)
        stream.write(
            f"{self._get_indent_with_arrow(depth + 1)}{self._color('to', Colors.BLUE)}: {self._type_to_string(cast.type)}\n"
        )

    def _stream_if_then(self, if_then: stalg.Expression.IfThen, stream, depth: int):
        """Print an if-then expression concisely"""
        indent = " " * (depth * self.indent_size)

        stream.write(f"{indent}if_then\n")
        if if_then.ifs:
            stream.write(
                f"{self._get_indent_with_arrow(depth + 1)}{self._color('if', Colors.BLUE)}:\n"
            )
            self._stream_expression(if_then.ifs[0].if_, stream, depth + 1)
            stream.write(
                f"{self._get_indent_with_arrow(depth + 1)}{self._color('then', Colors.BLUE)}:\n"
            )
            self._stream_expression(if_then.ifs[0].then, stream, depth + 1)

        if if_then.HasField("else_"):
            stream.write(
                f"{self._get_indent_with_arrow(depth + 1)}{self._color('else', Colors.BLUE)}:\n"
            )
            self._stream_expression(if_then.else_, stream, depth + 1)

    def _stream_window_function(
        self, func: stalg.Expression.WindowFunction, stream, depth: int
    ):
        """Print a window function concisely"""
        indent = " " * (depth * self.indent_size)

        stream.write(f"{indent}window_function: {func.function_reference}\n")
        if func.arguments:
            stream.write(
                f"{self._get_indent_with_arrow(depth + 1)}{self._color('args', Colors.BLUE)}: {self._color(len(func.arguments), Colors.YELLOW)}\n"
            )
            for i, arg in enumerate(func.arguments):
                stream.write(
                    f"{self._get_indent_with_arrow(depth + 2)}{self._color(f'{i}', Colors.CYAN)}:\n"
                )
                self._stream_expression(arg, stream, depth + 2)

    def _get_function_argument_string(self, arg) -> str:
        """Get function argument content as a string without newlines"""
        if hasattr(arg, "value") and arg.HasField("value"):
            if arg.value.HasField("literal"):
                # For simple literals, return the value directly
                if arg.value.literal.HasField("boolean"):
                    return f"literal: {arg.value.literal.boolean}"
                elif arg.value.literal.HasField("i32"):
                    return f"literal: {arg.value.literal.i32}"
                elif arg.value.literal.HasField("i64"):
                    return f"literal: {arg.value.literal.i64}"
                elif arg.value.literal.HasField("fp32"):
                    return f"literal: {arg.value.literal.fp32}"
                elif arg.value.literal.HasField("fp64"):
                    return f"literal: {arg.value.literal.fp64}"
                elif arg.value.literal.HasField("string"):
                    return f'literal: "{arg.value.literal.string}"'
                elif arg.value.literal.HasField("date"):
                    return f"literal: date={arg.value.literal.date}"
                elif arg.value.literal.HasField("timestamp"):
                    return f"literal: timestamp={arg.value.literal.timestamp}"
                elif arg.value.literal.HasField("map"):
                    # For maps, we'll handle them specially in the main printing
                    return "<map_literal>"
                else:
                    return "literal: <complex>"
            elif arg.value.HasField("selection"):
                # For simple field references, return the column name if available
                if arg.value.selection.HasField("direct_reference"):
                    if arg.value.selection.direct_reference.HasField("struct_field"):
                        field_idx = (
                            arg.value.selection.direct_reference.struct_field.field
                        )
                        column_name = self._resolve_field_name(field_idx)
                        return f"field: {column_name}"
                    else:
                        return "field: direct"
                else:
                    return "field: root"
            elif arg.value.HasField("scalar_function"):
                # For nested scalar functions, we'll handle them specially in the main printing
                # Return a placeholder that indicates it needs recursive expansion
                return "<nested_scalar_function>"
            elif arg.value.HasField("enum"):
                return f"enum: {arg.value.enum}"
            else:
                return "<unknown_function_argument_value>"
        else:
            return "<function_argument>"

    def _stream_function_argument(self, arg, stream, depth: int):
        """Print a function argument concisely"""
        indent = " " * (depth * self.indent_size)

        # FunctionArgument can have different types of values
        if hasattr(arg, "value") and arg.HasField("value"):
            if arg.value.HasField("literal"):
                # For simple literals, put the value on the same line
                if arg.value.literal.HasField("boolean"):
                    stream.write(f"{indent}literal: {arg.value.literal.boolean}\n")
                elif arg.value.literal.HasField("i32"):
                    stream.write(f"{indent}literal: {arg.value.literal.i32}\n")
                elif arg.value.literal.HasField("i64"):
                    stream.write(f"{indent}literal: {arg.value.literal.i64}\n")
                elif arg.value.literal.HasField("fp32"):
                    stream.write(f"{indent}literal: {arg.value.literal.fp32}\n")
                elif arg.value.literal.HasField("fp64"):
                    stream.write(f"{indent}literal: {arg.value.literal.fp64}\n")
                elif arg.value.literal.HasField("string"):
                    stream.write(f'{indent}literal: "{arg.value.literal.string}"\n')
                elif arg.value.literal.HasField("date"):
                    stream.write(f"{indent}literal: date={arg.value.literal.date}\n")
                elif arg.value.literal.HasField("timestamp"):
                    stream.write(
                        f"{indent}literal: timestamp={arg.value.literal.timestamp}\n"
                    )
                elif arg.value.literal.HasField("map"):
                    # Handle map literals with proper indentation
                    stream.write(f"{indent}literal: map\n")
                    self._stream_map_literal(arg.value.literal.map, stream, depth + 1)
                else:
                    stream.write(f"{indent}literal: <complex>\n")
            elif arg.value.HasField("selection"):
                # For simple field references, put the column name on the same line
                if arg.value.selection.HasField("direct_reference"):
                    if arg.value.selection.direct_reference.HasField("struct_field"):
                        field_idx = (
                            arg.value.selection.direct_reference.struct_field.field
                        )
                        column_name = self._resolve_field_name(field_idx)
                        stream.write(f"{indent}field: {column_name}\n")
                    else:
                        stream.write(f"{indent}field: direct\n")
                else:
                    stream.write(f"{indent}field: root\n")
            elif arg.value.HasField("scalar_function"):
                self._stream_scalar_function(arg.value.scalar_function, stream, depth)
            elif arg.value.HasField("enum"):
                stream.write(f"{indent}enum: {arg.value.enum}\n")
            else:
                stream.write(f"{indent}<unknown_function_argument_value>\n")
        else:
            stream.write(f"{indent}<function_argument>\n")

    def _stream_map_literal(
        self, map_literal: stalg.Expression.Literal.Map, stream, depth: int
    ):
        """Print a map literal with proper indentation"""
        indent = " " * (depth * self.indent_size)

        if map_literal.key_values:
            stream.write(
                f"{indent}-> {self._color('key_values', Colors.BLUE)}({self._color(len(map_literal.key_values), Colors.YELLOW)}):\n"
            )
            for i, kv in enumerate(map_literal.key_values):
                stream.write(
                    f"{indent}  -> {self._color('key_values', Colors.BLUE)}[{self._color(f'{i}', Colors.CYAN)}]:\n"
                )
                stream.write(
                    f"{indent}    -> {self._color('key', Colors.BLUE)}: {self._color(kv.key.string, Colors.GREEN)}\n"
                )
                stream.write(f"{indent}    -> {self._color('value', Colors.BLUE)}:\n")
                self._stream_literal_value(kv.value, stream, depth + 2)
        else:
            stream.write(f"{indent}-> {self._color('empty map', Colors.YELLOW)}\n")

    def _stream_literal_value(
        self, literal: stalg.Expression.Literal, stream, depth: int
    ):
        """Print a literal value with proper indentation"""
        indent = " " * (depth * self.indent_size)

        if literal.HasField("boolean"):
            stream.write(
                f"{indent}{self._color('boolean', Colors.BLUE)}: {self._color(literal.boolean, Colors.GREEN)}\n"
            )
        elif literal.HasField("i32"):
            stream.write(
                f"{indent}{self._color('i32', Colors.BLUE)}: {self._color(literal.i32, Colors.GREEN)}\n"
            )
        elif literal.HasField("i64"):
            stream.write(
                f"{indent}{self._color('i64', Colors.BLUE)}: {self._color(literal.i64, Colors.GREEN)}\n"
            )
        elif literal.HasField("fp32"):
            stream.write(
                f"{indent}{self._color('fp32', Colors.BLUE)}: {self._color(literal.fp32, Colors.GREEN)}\n"
            )
        elif literal.HasField("fp64"):
            stream.write(
                f"{indent}{self._color('fp64', Colors.BLUE)}: {self._color(literal.fp64, Colors.GREEN)}\n"
            )
        elif literal.HasField("string"):
            stream.write(
                f"{indent}{self._color('string', Colors.BLUE)}: {self._color(f'"{literal.string}"', Colors.GREEN)}\n"
            )
        elif literal.HasField("date"):
            stream.write(
                f"{indent}{self._color('date', Colors.BLUE)}: {self._color(literal.date, Colors.GREEN)}\n"
            )
        elif literal.HasField("timestamp"):
            stream.write(
                f"{indent}{self._color('timestamp', Colors.BLUE)}: {self._color(literal.timestamp, Colors.GREEN)}\n"
            )
        elif literal.HasField("map"):
            # Recursively handle nested maps
            stream.write(f"{indent}{self._color('map', Colors.BLUE)}:\n")
            self._stream_map_literal(literal.map, stream, depth + 1)
        elif literal.HasField("list"):
            # Handle list literals
            stream.write(
                f"{indent}{self._color('list', Colors.BLUE)}({self._color(len(literal.list.values), Colors.YELLOW)}):\n"
            )
            for i, item in enumerate(literal.list.values):
                stream.write(f"{indent}  -> {self._color(f'{i}', Colors.CYAN)}:\n")
                self._stream_literal_value(item, stream, depth + 2)
        else:
            stream.write(
                f"{indent}{self._color('<unknown_literal_type>', Colors.RED)}\n"
            )

    def _stream_struct_literal(
        self, struct_literal, stream, depth: int, inline: bool = False
    ):
        """Print a struct literal value with proper indentation"""
        if inline:
            # When inline, don't add extra indentation since we're already on the same line
            indent = ""
        else:
            indent = " " * (depth * self.indent_size)

        if hasattr(struct_literal, "fields") and struct_literal.fields:
            stream.write(f"{indent}{self._color('struct', Colors.BLUE)}\n")
            for i, field in enumerate(struct_literal.fields):
                # Show field index
                stream.write(f"{self._get_indent_with_arrow(depth + 1)}field[{i}]:\n")
                # Show the actual field value with proper indentation
                if field.HasField("i64"):
                    stream.write(
                        f"{self._get_indent_with_arrow(depth + 2)}{self._color('i64', Colors.BLUE)}: {self._color(field.i64, Colors.GREEN)}\n"
                    )
                elif field.HasField("fp64"):
                    stream.write(
                        f"{self._get_indent_with_arrow(depth + 2)}{self._color('fp64', Colors.BLUE)}: {self._color(field.fp64, Colors.GREEN)}\n"
                    )
                elif field.HasField("fp32"):
                    stream.write(
                        f"{self._get_indent_with_arrow(depth + 2)}{self._color('fp32', Colors.BLUE)}: {self._color(field.fp32, Colors.GREEN)}\n"
                    )
                elif field.HasField("i32"):
                    stream.write(
                        f"{self._get_indent_with_arrow(depth + 2)}{self._color('i32', Colors.BLUE)}: {self._color(field.i32, Colors.GREEN)}\n"
                    )
                elif field.HasField("string"):
                    stream.write(
                        f"{self._get_indent_with_arrow(depth + 2)}{self._color('string', Colors.BLUE)}: {self._color(f'"{field.string}"', Colors.GREEN)}\n"
                    )
                elif field.HasField("boolean"):
                    stream.write(
                        f"{self._get_indent_with_arrow(depth + 2)}{self._color('boolean', Colors.BLUE)}: {self._color(field.boolean, Colors.GREEN)}\n"
                    )
                else:
                    stream.write(
                        f"{self._get_indent_with_arrow(depth + 2)}{self._color('<unknown_field_type>', Colors.RED)}\n"
                    )
        else:
            stream.write(f"{indent}{self._color('empty_struct', Colors.YELLOW)}\n")

    def _type_to_string(self, type_info: stt.Type) -> str:
        """Convert a type to a concise string representation"""
        if type_info.HasField("bool"):
            return f"bool({type_info.bool.nullability})"
        elif type_info.HasField("i32"):
            return f"i32({type_info.i32.nullability})"
        elif type_info.HasField("i64"):
            return f"i64({type_info.i64.nullability})"
        elif type_info.HasField("fp32"):
            return f"fp32({type_info.fp32.nullability})"
        elif type_info.HasField("fp64"):
            return f"fp64({type_info.fp64.nullability})"
        elif type_info.HasField("string"):
            return f"string({type_info.string.nullability})"
        elif type_info.HasField("struct"):
            return f"struct({len(type_info.struct.types)} fields)"
        else:
            return "<unknown_type>"


# Convenience functions for easy usage
def pretty_print_plan(
    plan: stp.Plan,
    indent_size: int = 2,
    show_metadata: bool = False,
    use_colors: bool = False,
) -> None:
    """Convenience function to print a Substrait plan concisely"""
    printer = PlanPrinter(indent_size, show_metadata, use_colors)
    printer.print_plan(plan)


def pretty_print_expression(
    expression: stalg.Expression,
    indent_size: int = 2,
    show_metadata: bool = False,
    use_colors: bool = False,
) -> None:
    """Convenience function to print a Substrait expression concisely"""
    printer = PlanPrinter(indent_size, show_metadata, use_colors)
    printer.print_expression(expression)
