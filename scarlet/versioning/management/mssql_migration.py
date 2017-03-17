# -----------------------------------------
# Specific MSSQL commands for migrations
# -----------------------------------------
from django.db import connection, transaction
from django import VERSION as DJANGO_VERSION
from django.conf import settings


class MSSQLBackend(object):
    VIEW_SQL = "DECLARE @SQL as varchar(4000) ,\
        @STATE as varchar(20); \
        {declare} \
        SET @SQL = 'SELECT * from {version_model} \
            inner join {base_model} \
            on {base_model}.id = {version_model}.object_id \
            {where}'; \
        IF OBJECT_ID('{schema}.{model_table}') IS NULL \
            SET @SQL = 'CREATE VIEW {schema}.{model_table} AS ' + @SQL \
        ELSE \
            SET @SQL = 'ALTER VIEW {schema}.{model_table} AS ' + @SQL;  \
        EXEC(@SQL);"

    DROP_SQL = "IF OBJECT_ID('{schema}.{model_table}') IS NOT NULL \
        DROP VIEW {schema}.{model_table}"

    DELETE_PROC = "DECLARE @SQL as varchar(4000); \
        SET @SQL = 'CREATE PROCEDURE {name} @old_id int \
        AS \
        BEGIN \
        SET NOCOUNT ON; \
        DELETE FROM {version_model} WHERE object_id=@old_id; \
        DELETE FROM {base_model} WHERE id=@old_id; \
        END;'; \
        IF OBJECT_ID('{name}') IS NOT NULL \
            DROP PROCEDURE {name}; \
        EXEC(@SQL)"

    DELETE_TRIGGER = "DECLARE @SQL as varchar(4000); \
        SET @SQL = 'CREATE TRIGGER {name} ON {schema}.{model_table} \
        INSTEAD OF DELETE \
        AS \
        DECLARE \
        @old_id int \
        BEGIN \
        SET NOCOUNT ON; \
        SELECT @old_id=DELETED.id FROM DELETED; \
        EXEC {proc_name} @old_id; \
        END;'; \
        IF OBJECT_ID('{name}') IS NULL \
        EXEC(@SQL)"

    UPDATE_PROC = "DECLARE @SQL as varchar(4000); \
    SET @SQL = 'CREATE PROCEDURE {name} \
    @new_is_published bit \
    @new_created_date datetime \
    @new_v_last_save datetime \
    @old_id int, \
    @old_vid int, \
    {version_fields_params} \
    AS \
    BEGIN \
    SET NOCOUNT ON; \
    UPDATE {base_model} SET \
        is_published=@new_is_published, \
        created_date=@new_created_date, v_last_save=@new_v_last_save \
    WHERE id=@old_id; \
    UPDATE {version_model} SET \
        {version_fields_update} \
    WHERE object_id=@old_id and vid=@old_vid \
    END;'; \
    IF OBJECT_ID('{name}') IS NOT NULL \
    DROP PROCEDURE {name}; \
    EXEC(@SQL)"

    UPDATE_TRIGGER = "DECLARE @SQL as varchar(4000); \
        SET @SQL = 'CREATE TRIGGER {name} ON {schema}.{model_table} \
        INSTEAD OF UPDATE \
        AS \
        DECLARE \
        @old_id int, \
        @old_vid int, \
        @new_is_published bit, \
        @new_created_date datetime, \
        @new_v_last_save datetime, \
        @new_last_save datetime, \
        {version_fields_declare} \
        BEGIN \
        SET NOCOUNT ON; \
        SELECT @old_id=id, @old_vid=vid FROM {model_table}; \
        SELECT {select_fields} FROM INSERTED; \
        EXEC {proc_name} \
        @new_is_published, \
        @new_created_date, \
        @new_v_last_save, \
        @old_id, \
        @old_vid, \
        {proc_params} \
        END;'; \
        IF OBJECT_ID('{name}') IS NULL \
        EXEC(@SQL)"

    def __init__(self):
        # When tests are running `DEFAULT_SCHEMA` is `dbo`, otherwise
        # `DEFAULT_SCHEMA` is database name in settings
        database_name = settings.DATABASES.get('default').get('NAME')
        self.DEFAULT_SCHEMA = database_name
        # `Azure DB` is using `dbo` as default schema and `MSSQL` for Linux is
        # using dbname as schema. For this reason, we need an addtional setting
        # to check if we're using `Azure DB` or `MSSQL`:
        #  'OPTIONS': {
        #      'is_azuredb': True,
        #   }
        #
        azure_options = settings.DATABASES.get('default').get('OPTIONS').get('is_azuredb')
        if database_name[:5] == 'test_' or azure_options:
            self.DEFAULT_SCHEMA = 'dbo'
        self.cursor = connection.cursor()

    def _get_declare_cols(self, cols, table, prefix):
        declare_st = ''
        for x in cols:
            sql = "SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS \
            where TABLE_NAME='{0}' and column_name='{1}'".format(table, x)
            res = self.cursor.execute(sql)
            column_type = res.fetchall()[0][0]
            declare_st += '@{0}_{1} {2}, '.format(prefix, x, column_type)
        return declare_st

    def do_updates(self, m):
        if getattr(m._meta, '_is_view') is None:
            return

        base_model = m._meta._base_model._meta.db_table
        version_model = m._meta._version_model._meta.db_table
        model_table = m._meta.db_table
        schema = self.DEFAULT_SCHEMA

        version_cols = [f.column for f in m._meta._version_model._meta.local_fields
                        if f.column and f.column != 'vid']

        base_cols = [f.column for f in m._meta._base_model._meta.local_fields \
                     if f.column and f.column != 'id']

        join_version_cols = ', '.join(['{0}=@new_{0}'.format(x) for x in version_cols])
        join_base_cols = ', '.join(['{0}=@new_{0}'.format(x) for x in base_cols])

        unique_states = m._meta._version_model.UNIQUE_STATES
        default_schema_lst = list()
        default_schema_lst.append(self.DEFAULT_SCHEMA)
        schemas = default_schema_lst + [u for u in unique_states]
        where = ''
        declare = ''

        for schema in schemas:
            # Iterating over every schema for creating view, stored procedures
            # and triggers. Notice we must iterate over default schema first
            if schema in unique_states:
                res = self.cursor.execute("select schema_name FROM \
                information_schema.schemata WHERE schema_name = %s", (schema,))
                if len(res.fetchall()) == 0:
                    self.cursor.execute("CREATE SCHEMA %s" % schema)
                where = "WHERE {0}.state=''' + @STATE + '''".format(version_model),
                declare = "SET @STATE = '{0}';".format(schema)

            # View for given schema
            self.cursor.execute(self.DROP_SQL.format(
                schema=schema,
                model_table=model_table,
            ))

            self.cursor.execute(self.VIEW_SQL.format(
                schema=schema,
                version_model=version_model,
                base_model=base_model,
                model_table=model_table,
                where=where,
                declare=declare
            ))

            self.cursor.execute(self.DELETE_PROC.format(
                name='{0}_delete'.format(base_model),
                schema=schema,
                version_model=version_model,
                base_model=base_model,
            ))

            self.cursor.execute(self.DELETE_TRIGGER.format(
                proc_name='{0}_delete'.format(base_model),
                name='{0}_delete_trigger'.format(base_model),
                model_table=model_table,
                schema=schema,
            ))

            self.cursor.execute(self.UPDATE_PROC.format(
                name='{0}_update'.format(base_model),
                schema=schema,
                version_model=version_model,
                base_model=base_model,
                version_fields_params=self._get_declare_cols(
                    version_cols, model_table, 'new',
                ),
                version_fields_update=', '.join(['{0}=@new_{0}'.format(x) for x in version_cols])
            ))

            self.cursor.execute(self.UPDATE_TRIGGER.format(
                proc_name='{0}_update'.format(base_model),
                name='{0}_update_trigger'.format(base_model),
                model_table=model_table,
                schema=schema,
                version_fields_declare=self._get_declare_cols(
                    version_cols, model_table, 'new',
                )[:-2],
                proc_params=', '.join(['@new_{0}'.format(x) for x in version_cols]),
                select_fields=join_base_cols + ', ' + join_version_cols
            ))

        if DJANGO_VERSION < (1, 6):
            transaction.commit_unless_managed()
