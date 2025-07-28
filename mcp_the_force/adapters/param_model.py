"""Base class for parameter models with dataclass transform support."""

from typing_extensions import dataclass_transform
from ..tools.descriptors import Route


@dataclass_transform(
    # Tell the checker that these CALLABLES are "field factories"
    field_specifiers=(
        Route.prompt,
        Route.adapter,
        Route.vector_store,
        Route.session,
        Route.vector_store_ids,
        Route.structured_output,
    ),
)
class ParamModel:
    """Base class that enables proper type inference for Route descriptors.

    This class uses @dataclass_transform to tell type checkers (mypy, pyright)
    that the Route.* factory methods should be treated as field specifiers,
    allowing the type annotation on the left side of the assignment to be
    used as the runtime type rather than RouteDescriptor[Any].

    All parameter classes should inherit from this to get proper type checking.
    """

    pass
