class DispatchRegistry:
    def __init__(self):
        self._registry = {}

    def register(self, cls):
        def decorator(func):
            self._registry[cls] = func
            return func
        return decorator
    
    def __getitem__(self, cls):
        for dispatch_cls, func in self._registry.items():
            if issubclass(cls, dispatch_cls):
                return func
        else:
            raise ValueError(f"Unsupported SQL Node type: {cls}")