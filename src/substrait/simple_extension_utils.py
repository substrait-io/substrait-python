from substrait.gen.json import simple_extensions as se
from typing import Union


def build_arg(d: dict) -> Union[se.ValueArg, se.TypeArg, se.EnumerationArg]:
    if "value" in d:
        return se.ValueArg(
            value=d["value"],
            name=d.get("name"),
            description=d.get("description"),
            constant=d.get("constant"),
        )
    elif "type" in d:
        return se.TypeArg(
            type=d["type"], name=d.get("name"), description=d.get("description")
        )
    elif "options" in d:
        return se.EnumerationArg(
            options=d["options"], name=d.get("name"), description=d.get("description")
        )


def build_variadic_behavior(d: dict) -> se.VariadicBehavior:
    return se.VariadicBehavior(
        min=d.get("min"),
        max=d.get("max"),
        parameterConsistency=se.ParameterConsistency(d["parameterConsistency"])
        if "parameterConsistency" in d
        else None,
    )


def build_options(d: dict) -> se.Options:
    return {
        k: se.Options1(values=v["values"], description=v.get("description"))
        for k, v in d.items()
    }


def build_scalar_function(d: dict) -> se.ScalarFunction:
    return se.ScalarFunction(
        name=d["name"],
        impls=[
            se.Impl(
                return_=i["return"],
                args=[build_arg(arg) for arg in i["args"]] if "args" in i else None,
                options=build_options(i["options"]) if "options" in i else None,
                variadic=build_variadic_behavior(i["variadic"])
                if "variadic" in i
                else None,
                sessionDependent=i.get("sessionDependent"),
                deterministic=i.get("deterministic"),
                nullability=se.NullabilityHandling(i["nullability"])
                if "nullability" in i
                else None,
                implementation=i.get("implementation"),
            )
            for i in d["impls"]
        ],
        description=d.get("description"),
    )


def build_aggregate_function(d: dict) -> se.AggregateFunction:
    return se.AggregateFunction(
        name=d["name"],
        impls=[
            se.Impl1(
                return_=i["return"],
                args=[build_arg(arg) for arg in i["args"]] if "args" in i else None,
                options=build_options(i["options"]) if "options" in i else None,
                variadic=build_variadic_behavior(i["variadic"])
                if "variadic" in i
                else None,
                sessionDependent=i.get("sessionDependent"),
                deterministic=i.get("deterministic"),
                nullability=se.NullabilityHandling(i["nullability"])
                if "nullability" in i
                else None,
                implementation=i.get("implementation"),
                intermediate=i.get("intermediate"),
                ordered=i.get("ordered"),
                maxset=i.get("maxset"),
                decomposable=se.Decomposable(i["decomposable"])
                if "decomposable" in i
                else None,
            )
            for i in d["impls"]
        ],
        description=d.get("description"),
    )


def build_window_function(d: dict) -> se.WindowFunction:
    return se.WindowFunction(
        name=d["name"],
        impls=[
            se.Impl2(
                return_=i["return"],
                args=[build_arg(arg) for arg in i["args"]] if "args" in i else None,
                options=build_options(i["options"]) if "options" in i else None,
                variadic=build_variadic_behavior(i["variadic"])
                if "variadic" in i
                else None,
                sessionDependent=i.get("sessionDependent"),
                deterministic=i.get("deterministic"),
                nullability=se.NullabilityHandling(i["nullability"])
                if "nullability" in i
                else None,
                implementation=i.get("implementation"),
                intermediate=i.get("intermediate"),
                ordered=i.get("ordered"),
                maxset=i.get("maxset"),
                decomposable=se.Decomposable(i["decomposable"])
                if "decomposable" in i
                else None,
                window_type=se.WindowType(i["window_type"])
                if "window_type" in i
                else None,
            )
            for i in d["impls"]
        ],
        description=d.get("description"),
    )


def build_type_model(d: dict) -> se.TypeModel:
    return se.TypeModel(
        name=d["name"],
        structure=d.get("structure"),
        parameters=d.get("parameters"),
        variadic=d.get("variadic"),
    )


def build_type_variation(d: dict) -> se.TypeVariation:
    return se.TypeVariation(
        parent=d["parent"],
        name=d["name"],
        description=d.get("description"),
        functions=se.Functions(d["functions"]) if "functions" in d else None,
    )


def build_simple_extensions(d: dict) -> se.SimpleExtensions:
    return se.SimpleExtensions(
        dependencies=d.get("dependencies"),
        types=[build_type_model(t) for t in d["types"]] if "types" in d else None,
        type_variations=[build_type_variation(t) for t in d["type_variations"]]
        if "type_variations" in d
        else None,
        scalar_functions=[build_scalar_function(f) for f in d["scalar_functions"]]
        if "scalar_functions" in d
        else None,
        aggregate_functions=[
            build_aggregate_function(f) for f in d["aggregate_functions"]
        ]
        if "aggregate_functions" in d
        else None,
        window_functions=[build_window_function(f) for f in d["window_functions"]]
        if "window_functions" in d
        else None,
    )
