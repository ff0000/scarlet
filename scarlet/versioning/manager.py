from threading import local

from django.db import models
from django.db import connections

_mode = local()


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
        current_state = getattr(_mode, "current_state", None)
        q = super(VersionManager, self).get_query_set()
        if current_state:
            q = q.filter(state=current_state)
        return q


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
