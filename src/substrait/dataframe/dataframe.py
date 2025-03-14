from substrait.gen.proto import algebra_pb2 as stalg
from substrait.gen.proto import plan_pb2 as stp
from substrait.gen.proto import type_pb2 as stt
from substrait.gen.proto.extensions import extensions_pb2 as ste
from substrait.type_inference import infer_rel_schema
from substrait.dataframe.utils import merge_extensions

class DataFrame:
    def __init__(self, plan: stp.Plan, extensions: dict = {}):
        self.plan = plan
        self.extensions = extensions
        
        if extensions:
            self.plan = stp.Plan(
                extension_uris=[
                    ste.SimpleExtensionURI(extension_uri_anchor=i, uri=e)
                    for i, e in enumerate(self.extensions.keys())
                ],
                extensions=[
                    ste.SimpleExtensionDeclaration(
                        extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                            extension_uri_reference=i,
                            function_anchor=fn_anchor,
                            name=fn_name,
                        )
                    )
                    for i, e in enumerate(self.extensions.items())
                    for fn_name, fn_anchor in e[1].items()
                ],
                version=self.plan.version,
                relations=self.plan.relations,
            )

    def schema(self) -> stt.Type.Struct:
        return infer_rel_schema(self.plan.relations[-1].root.input)

    def project(self, *expressions):
        bound_expressions = [e.bind(self) for e in expressions]

        rel = stalg.Rel(
            project=stalg.ProjectRel(
                input=self.plan.relations[-1].root.input,
                expressions=[e.expression for e in bound_expressions]
            )
        )

        names = [e.alias for e in bound_expressions]

        plan = stp.Plan(
            relations=[
                stp.PlanRel(root=stalg.RelRoot(input=rel, names=names))
            ]
        )

        return DataFrame(plan=plan, extensions=merge_extensions(self.extensions, *[e.extensions for e in bound_expressions]))
    
    

