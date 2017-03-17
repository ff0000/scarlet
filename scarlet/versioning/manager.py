from threading import local

from django.db import models
from django.db import connections

_mode = local()


class ContextState(object):
    """
    Checks the current context every
    time the query is evaluated.
    """

    def prepare(self):
        return self

    def _prepare(self, val=None):
        return self

    def as_sql(self, qn=None, compiler=None, connection=None):
        current_state = getattr(_mode, "current_state", None)
        if not current_state:
            return '"state"', tuple()
        else:
            return "%s", (current_state,)


def activate(state):
    """
    Activate a state in this thread.
    """

    _mode.current_state = state
    _mode.schema = state


def deactivate():
    """
    Deactivate a state in this thread.
    """

    if hasattr(_mode, "current_state"):
        del _mode.current_state
    if hasattr(_mode, "schema"):
        del _mode.schema

    for k in connections:
        con = connections[k]
        if hasattr(con, 'reset_schema'):
            con.reset_schema()


def get_schema():
    return getattr(_mode, 'schema', None)


class VersionManager(models.Manager):
    """
    Default Manager for version models.

    Looks up the current state and filters on it.
    """

    use_for_related_fields = True

    def get_query_set(self):
        return self.get_queryset()

    def get_queryset(self):
        try:
            qs = super(VersionManager, self).get_query_set()
        except AttributeError:
            qs = super(VersionManager, self).get_queryset()
        qs = qs.filter(state=ContextState())
        return qs


class SwitchSchema(object):
    """
    Context manager for switching schema.
    """

    def __init__(self, schema):
        self.old_schema = get_schema()
        self.schema = schema

    def __enter__(self):
        _mode.schema = self.schema

    def __exit__(self, etype, value, traceback):
        _mode.schema = self.old_schema


class SwitchSchemaManager(SwitchSchema):
    def __enter__(self):
        _mode.schema = self.schema
        _mode.current_state = self.schema

    def __exit__(self, etype, value, traceback):
        _mode.schema = self.old_schema
        _mode.current_state = self.old_schema
