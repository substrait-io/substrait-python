import types


class DispatchRegistry:
    """Dispatch a function based on the class of the argument.

    This class allows to register a function to execute for a specific class
    and expose this as a method of an object which will be dispatched
    based on the argument.

    It is similar to functools.singledispatch but it allows more
    customization in case the dispatch rules grow in complexity
    and works for class methods as well
    (singledispatch supports methods only in more recent versions)
    """

    def __init__(self):
        self._registry = {}

    def register(self, cls):
        def decorator(func):
            self._registry[cls] = func
            return func

        return decorator

    def bind(self, obj):
        return types.MethodType(self, obj)

    def __getitem__(self, argument):
        for dispatch_cls, func in self._registry.items():
            if isinstance(argument, dispatch_cls):
                return func
        else:
            raise ValueError(f"Unsupported SQL Node type: {cls}")

    def __call__(self, obj, dispatch_argument, *args, **kwargs):
        return self[dispatch_argument](obj, dispatch_argument, *args, **kwargs)
