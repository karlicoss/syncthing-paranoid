[default,parallel]
quick: ruff ty mypy format # quick run, no tests

[parallel]
check: ruff ty mypy format test

# no parallel; since they can write concurrently
fix: ruff-fix format-fix

@_uv   *args:
  uv run {{args}}

@ruff       *args: (_uv "ruff" "check"           args)
@ruff-fix   *args: (_uv "ruff" "check" "--fix"   args)
# mypy targets (script + tests) come from [tool.mypy] files in pyproject.toml
@mypy       *args: (_uv "mypy"                   args)
@ty         *args: (_uv "ty" "check"             args)  # paths come from [tool.ty.src] in pyproject.toml
@format     *args: (_uv "ruff" "format" "--diff" args)
@format-fix *args: (_uv "ruff" "format"          args)
@test       *args: (_uv "pytest" "tests"         args)
