from django.db.backends.postgresql_psycopg2.base import DatabaseWrapper, \
                                                        DatabaseCreation
from django import VERSION as DJANGO_VERSION


class DatabaseWrapper(DatabaseWrapper):
    UNTOUCHED = 1

    def __init__(self, *args, **kwargs):
        super(DatabaseWrapper, self).__init__(*args, **kwargs)
        self.creation = ViewDatabaseCreation(self)
        self.schema = self.UNTOUCHED

    def _cursor(self, name=None):
        from ..manager import get_schema

        cursor = super(DatabaseWrapper, self)._cursor()
        schema = get_schema()
        if schema != self.schema:
            self.schema = schema
            if schema:
                cursor.execute('SET search_path = %s, public', [schema])
            else:
                cursor.execute('SET search_path = public')
        return cursor

    def reset_schema(self):
        self.schema = self.UNTOUCHED


class ViewDatabaseCreation(DatabaseCreation):
    def _sql_for_inline_fk_refs(self, field, known_models, style, model=None):
        # Hack to point references to the correct table.
        view_table = field.rel.to._meta.db_table
        if getattr(field.rel.to._meta, '_is_view', False):
            if field.rel.field_name == field.rel.to._meta.pk.name:
                # Base model might not be created
                if field.rel.to._meta._base_model in known_models:
                    base_table = field.rel.to._meta._base_model._meta.db_table
                    field.rel.to._meta.db_table = base_table
                else:
                    output = []
                    pending = True
                    return output, pending
            else:
                version_table = field.rel.to._meta._version_model._meta.db_table
                field.rel.to._meta.db_table = version_table

        # Create the references
        if DJANGO_VERSION < (1, 6):
            ret_val = super(ViewDatabaseCreation, self
                            ).sql_for_inline_foreign_key_references(field,
                                                                    known_models,
                                                                    style)
        else:
            ret_val = super(ViewDatabaseCreation, self
                            ).sql_for_inline_foreign_key_references(model,
                                                                    field,
                                                                    known_models,
                                                                    style)

        # Restore the db_table value
        field.rel.to._meta.db_table = view_table

        return ret_val

    if DJANGO_VERSION < (1, 6):
        def sql_for_inline_foreign_key_references(self, field, known_models,
                                                  style):
            return self._sql_for_inline_fk_refs(field, known_models,
                                                    style)
    else:
        def sql_for_inline_foreign_key_references(self, model, field, known_models,
                                                  style):
            return self._sql_for_inline_fk_refs(field, known_models,
                                                    style, model)

    def sql_for_pending_references(self, model, style, pending_references):
        from ..fields import FKToVersion

        # Hack to create references after the fact.
        changed = []
        if model in pending_references:
            for rel_class, field in pending_references[model]:
                if getattr(rel_class, '_is_view', False):
                    changed.append((rel_class, rel_class._meta.db_table))

                    # which table do we point to
                    if isinstance(field, FKToVersion):
                        version_table = rel_class._meta._version_model._meta.db_table
                        rel_class._meta.db_table = version_table
                    else:
                        base_table = rel_class._meta._base_model._meta.db_table
                        rel_class._meta.db_table = base_table

        # Create the references
        ret_val = super(ViewDatabaseCreation, self
                        ).sql_for_pending_references(model, style,
                                                     pending_references)

        # Restore the db_table values
        for rel_class, table in changed:
            rel_class._meta.db_table = table

        return ret_val
