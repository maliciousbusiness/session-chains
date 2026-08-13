from session_chains.utils import UserContext

"""
You can define custom filters for this project here.
Functions can take:
- value (str) only, for simple transformations
- value (str) and ctx (UserContext) for complex transformations
"""


def example_simple(value: str):
    # Example: Reverse the string
    return value[::-1]


def example_complex(value: str, ctx: UserContext):
    # Example: append role name to value
    return f"{value}_{ctx.role}"
