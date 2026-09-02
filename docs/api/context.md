# Ambient scope

The request scope a framework adapter opens is bound to a `ContextVar` in
`depi.context`. Code running inside a request can reach it without it being
passed down the call stack. All five functions are re-exported from `depi`.

See [Lifetimes and scopes](../concepts/lifetimes-and-scopes.md#reaching-the-scope-without-passing-it-around).

::: depi.context
    options:
      show_root_heading: false
      members:
        - current_scope
        - get_current_scope
        - set_current_scope
        - reset_current_scope
        - use_scope
