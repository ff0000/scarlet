# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion
from .. import models as version_models
import django.utils.timezone
import scarlet.versioning.fields


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Author',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('last_save', models.DateTimeField(editable=False)),
                ('is_published', models.BooleanField(default=False, editable=False)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('v_last_save', models.DateTimeField(null=True, editable=False)),
                ('state', models.CharField(max_length=50, editable=False, choices=[(b'published', b'published'), (b'scheduled', b'scheduled'), (b'draft', b'draft'), (b'archived', b'archived')])),
                ('last_scheduled', models.DateTimeField(null=True, editable=False)),
                ('date_published', models.DateTimeField(null=True, editable=False)),
                ('user_published', models.CharField(max_length=255, null=True, editable=False)),
                ('vid', models.PositiveIntegerField(unique=True, editable=False)),
                ('object_id', models.PositiveIntegerField(editable=False)),
                ('name', models.CharField(max_length=255)),
            ],
            options={
                b'db_table': 'version_models_author_base',
                'managed': False,
            },
            bases=(models.Model, version_models.AuthorReferences),
        ),
        migrations.CreateModel(
            name='Book',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('last_save', models.DateTimeField(editable=False)),
                ('is_published', models.BooleanField(default=False, editable=False)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('v_last_save', models.DateTimeField(null=True, editable=False)),
                ('state', models.CharField(max_length=50, editable=False, choices=[(b'published', b'published'), (b'scheduled', b'scheduled'), (b'draft', b'draft'), (b'archived', b'archived')])),
                ('last_scheduled', models.DateTimeField(null=True, editable=False)),
                ('date_published', models.DateTimeField(null=True, editable=False)),
                ('user_published', models.CharField(max_length=255, null=True, editable=False)),
                ('vid', models.PositiveIntegerField(unique=True, editable=False)),
                ('object_id', models.PositiveIntegerField(editable=False)),
                ('name', models.CharField(max_length=255)),
            ],
            options={
                b'db_table': 'version_models_book_base',
                'managed': False,
            },
            bases=(models.Model, version_models.Harmless, version_models.BookReferences),
        ),
        migrations.CreateModel(
            name='BookNoRelated',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('last_save', models.DateTimeField(editable=False)),
                ('is_published', models.BooleanField(default=False, editable=False)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('v_last_save', models.DateTimeField(null=True, editable=False)),
                ('state', models.CharField(max_length=50, editable=False, choices=[(b'published', b'published'), (b'scheduled', b'scheduled'), (b'draft', b'draft'), (b'archived', b'archived')])),
                ('last_scheduled', models.DateTimeField(null=True, editable=False)),
                ('date_published', models.DateTimeField(null=True, editable=False)),
                ('user_published', models.CharField(max_length=255, null=True, editable=False)),
                ('vid', models.PositiveIntegerField(unique=True, editable=False)),
                ('object_id', models.PositiveIntegerField(editable=False)),
                ('name', models.CharField(max_length=255)),
            ],
            options={
                b'db_table': 'version_models_booknorelated_base',
                'managed': False,
            },
            bases=(models.Model, version_models.Harmless, version_models.BookReferences),
        ),
        migrations.CreateModel(
            name='Cartoon',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('last_save', models.DateTimeField(editable=False)),
                ('is_published', models.BooleanField(default=False, editable=False)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('v_last_save', models.DateTimeField(null=True, editable=False)),
                ('state', models.CharField(max_length=50, editable=False, choices=[(b'published', b'published'), (b'scheduled', b'scheduled'), (b'draft', b'draft'), (b'archived', b'archived')])),
                ('last_scheduled', models.DateTimeField(null=True, editable=False)),
                ('date_published', models.DateTimeField(null=True, editable=False)),
                ('user_published', models.CharField(max_length=255, null=True, editable=False)),
                ('vid', models.PositiveIntegerField(unique=True, editable=False)),
                ('object_id', models.PositiveIntegerField(editable=False)),
                ('name', models.CharField(max_length=255)),
            ],
            options={
                b'db_table': 'version_models_cartoon_base',
                'managed': False,
            },
            bases=(models.Model, version_models.CartoonReferences),
        ),
        migrations.CreateModel(
            name='Gun',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('last_save', models.DateTimeField(editable=False)),
                ('is_published', models.BooleanField(default=False, editable=False)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('v_last_save', models.DateTimeField(null=True, editable=False)),
                ('state', models.CharField(max_length=50, editable=False, choices=[(b'published', b'published'), (b'scheduled', b'scheduled'), (b'draft', b'draft'), (b'archived', b'archived')])),
                ('last_scheduled', models.DateTimeField(null=True, editable=False)),
                ('date_published', models.DateTimeField(null=True, editable=False)),
                ('user_published', models.CharField(max_length=255, null=True, editable=False)),
                ('vid', models.PositiveIntegerField(unique=True, editable=False)),
                ('object_id', models.PositiveIntegerField(editable=False)),
                ('reg_number', models.CharField(max_length=20)),
                ('name', models.CharField(max_length=20)),
            ],
            options={
                b'db_table': 'version_models_custommodel',
                'managed': False,
            },
            bases=(models.Model, version_models.GunReferences),
        ),
        migrations.CreateModel(
            name='NoReverse',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('last_save', models.DateTimeField(editable=False)),
                ('is_published', models.BooleanField(default=False, editable=False)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('v_last_save', models.DateTimeField(null=True, editable=False)),
                ('state', models.CharField(max_length=50, editable=False, choices=[(b'published', b'published'), (b'scheduled', b'scheduled'), (b'draft', b'draft'), (b'archived', b'archived')])),
                ('last_scheduled', models.DateTimeField(null=True, editable=False)),
                ('date_published', models.DateTimeField(null=True, editable=False)),
                ('user_published', models.CharField(max_length=255, null=True, editable=False)),
                ('vid', models.PositiveIntegerField(unique=True, editable=False)),
                ('object_id', models.PositiveIntegerField(editable=False)),
                ('name', models.CharField(max_length=255)),
            ],
            options={
                b'db_table': 'version_models_noreverse_base',
                'managed': False,
            },
            bases=(models.Model, version_models.NoReverseReferences),
        ),
        migrations.CreateModel(
            name='Store',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('last_save', models.DateTimeField(editable=False)),
                ('is_published', models.BooleanField(default=False, editable=False)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('v_last_save', models.DateTimeField(null=True, editable=False)),
                ('state', models.CharField(max_length=50, editable=False, choices=[(b'published', b'published'), (b'scheduled', b'scheduled'), (b'draft', b'draft'), (b'archived', b'archived')])),
                ('last_scheduled', models.DateTimeField(null=True, editable=False)),
                ('date_published', models.DateTimeField(null=True, editable=False)),
                ('user_published', models.CharField(max_length=255, null=True, editable=False)),
                ('vid', models.PositiveIntegerField(unique=True, editable=False)),
                ('object_id', models.PositiveIntegerField(editable=False)),
                ('name', models.CharField(max_length=255)),
            ],
            options={
                b'db_table': 'version_models_store_base',
                'managed': False,
            },
            bases=(models.Model, version_models.StoreReferences),
        ),
        migrations.CreateModel(
            name='Author_base',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('is_published', models.BooleanField(default=False, editable=False)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('v_last_save', models.DateTimeField(null=True, editable=False)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Author_version',
            fields=[
                ('last_save', models.DateTimeField(editable=False)),
                ('state', models.CharField(max_length=50, editable=False, choices=[(b'published', b'published'), (b'scheduled', b'scheduled'), (b'draft', b'draft'), (b'archived', b'archived')])),
                ('last_scheduled', models.DateTimeField(null=True, editable=False)),
                ('date_published', models.DateTimeField(null=True, editable=False)),
                ('user_published', models.CharField(max_length=255, null=True, editable=False)),
                ('name', models.CharField(max_length=255)),
                ('vid', models.AutoField(serialize=False, primary_key=True)),
                ('associates', scarlet.versioning.fields.M2MFromVersion(to='version_models.Author_base', blank=True)),
                ('object', models.ForeignKey(related_name='version_version', to='version_models.Author_base')),
            ],
            options={
                'managed': True,
            },
            bases=(models.Model, version_models.AuthorVersionReferences),
        ),
        migrations.CreateModel(
            name='Book_base',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('is_published', models.BooleanField(default=False, editable=False)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('v_last_save', models.DateTimeField(null=True, editable=False)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Book_version',
            fields=[
                ('last_save', models.DateTimeField(editable=False)),
                ('state', models.CharField(max_length=50, editable=False, choices=[(b'published', b'published'), (b'scheduled', b'scheduled'), (b'draft', b'draft'), (b'archived', b'archived')])),
                ('last_scheduled', models.DateTimeField(null=True, editable=False)),
                ('date_published', models.DateTimeField(null=True, editable=False)),
                ('user_published', models.CharField(max_length=255, null=True, editable=False)),
                ('name', models.CharField(max_length=255)),
                ('vid', models.AutoField(serialize=False, primary_key=True)),
                ('author', models.ForeignKey(to='version_models.Author')),
            ],
            options={
                'managed': True,
            },
            bases=(models.Model, version_models.Harmless, version_models.BookVersionReferences),
        ),
        migrations.CreateModel(
            name='BookNoRelated_base',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('is_published', models.BooleanField(default=False, editable=False)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('v_last_save', models.DateTimeField(null=True, editable=False)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='BookNoRelated_version',
            fields=[
                ('last_save', models.DateTimeField(editable=False)),
                ('state', models.CharField(max_length=50, editable=False, choices=[(b'published', b'published'), (b'scheduled', b'scheduled'), (b'draft', b'draft'), (b'archived', b'archived')])),
                ('last_scheduled', models.DateTimeField(null=True, editable=False)),
                ('date_published', models.DateTimeField(null=True, editable=False)),
                ('user_published', models.CharField(max_length=255, null=True, editable=False)),
                ('name', models.CharField(max_length=255)),
                ('vid', models.AutoField(serialize=False, primary_key=True)),
                ('author', models.ForeignKey(to='version_models.Author')),
            ],
            options={
                'managed': True,
            },
            bases=(models.Model, version_models.Harmless, version_models.BookVersionReferences),
        ),
        migrations.CreateModel(
            name='Cartoon_base',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('is_published', models.BooleanField(default=False, editable=False)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('v_last_save', models.DateTimeField(null=True, editable=False)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Cartoon_version',
            fields=[
                ('last_save', models.DateTimeField(editable=False)),
                ('state', models.CharField(max_length=50, editable=False, choices=[(b'published', b'published'), (b'scheduled', b'scheduled'), (b'draft', b'draft'), (b'archived', b'archived')])),
                ('last_scheduled', models.DateTimeField(null=True, editable=False)),
                ('date_published', models.DateTimeField(null=True, editable=False)),
                ('user_published', models.CharField(max_length=255, null=True, editable=False)),
                ('name', models.CharField(max_length=255)),
                ('vid', models.AutoField(serialize=False, primary_key=True)),
                ('author', models.ForeignKey(related_name='works_version', on_delete=django.db.models.deletion.SET_NULL, blank=True, to='version_models.Author', null=True)),
                ('object', models.ForeignKey(related_name='version_version', to='version_models.Cartoon_base')),
            ],
            options={
                'managed': True,
            },
            bases=(models.Model, version_models.CartoonVersionReferences),
        ),
        migrations.CreateModel(
            name='ConcreteModel',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='CustomModel',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('is_published', models.BooleanField(default=False, editable=False)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('v_last_save', models.DateTimeField(null=True, editable=False)),
                ('reg_number', models.CharField(max_length=20)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Gallery',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('last_save', models.DateTimeField(editable=False)),
                ('name', models.CharField(max_length=255)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Gun_version',
            fields=[
                ('last_save', models.DateTimeField(editable=False)),
                ('state', models.CharField(max_length=50, editable=False, choices=[(b'published', b'published'), (b'scheduled', b'scheduled'), (b'draft', b'draft'), (b'archived', b'archived')])),
                ('last_scheduled', models.DateTimeField(null=True, editable=False)),
                ('date_published', models.DateTimeField(null=True, editable=False)),
                ('user_published', models.CharField(max_length=255, null=True, editable=False)),
                ('name', models.CharField(max_length=20)),
                ('vid', models.AutoField(serialize=False, primary_key=True)),
                ('object', models.ForeignKey(related_name='version_version', to='version_models.CustomModel')),
            ],
            options={
                'managed': True,
            },
            bases=(models.Model, version_models.GunVersionReferences),
        ),
        migrations.CreateModel(
            name='Image',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('last_save', models.DateTimeField(editable=False)),
                ('name', models.CharField(max_length=255)),
                ('cartoons', models.ManyToManyField(to='version_models.Cartoon')),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='NoReverse_base',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('is_published', models.BooleanField(default=False, editable=False)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('v_last_save', models.DateTimeField(null=True, editable=False)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='NoReverse_version',
            fields=[
                ('last_save', models.DateTimeField(editable=False)),
                ('state', models.CharField(max_length=50, editable=False, choices=[(b'published', b'published'), (b'scheduled', b'scheduled'), (b'draft', b'draft'), (b'archived', b'archived')])),
                ('last_scheduled', models.DateTimeField(null=True, editable=False)),
                ('date_published', models.DateTimeField(null=True, editable=False)),
                ('user_published', models.CharField(max_length=255, null=True, editable=False)),
                ('name', models.CharField(max_length=255)),
                ('vid', models.AutoField(serialize=False, primary_key=True)),
                ('object', models.ForeignKey(related_name='version_version', to='version_models.NoReverse_base')),
            ],
            options={
                'managed': True,
            },
            bases=(models.Model, version_models.NoReverseVersionReferences),
        ),
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('last_save', models.DateTimeField(editable=False)),
                ('text', models.CharField(max_length=255)),
                ('book', scarlet.versioning.fields.FKToVersion(to='version_models.Book_version', swappable=False)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='RM2M',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('last_save', models.DateTimeField(editable=False)),
                ('no', models.ManyToManyField(to='version_models.NoReverse')),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Store_base',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('is_published', models.BooleanField(default=False, editable=False)),
                ('created_date', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('v_last_save', models.DateTimeField(null=True, editable=False)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Store_version',
            fields=[
                ('last_save', models.DateTimeField(editable=False)),
                ('state', models.CharField(max_length=50, editable=False, choices=[(b'published', b'published'), (b'scheduled', b'scheduled'), (b'draft', b'draft'), (b'archived', b'archived')])),
                ('last_scheduled', models.DateTimeField(null=True, editable=False)),
                ('date_published', models.DateTimeField(null=True, editable=False)),
                ('user_published', models.CharField(max_length=255, null=True, editable=False)),
                ('name', models.CharField(max_length=255)),
                ('vid', models.AutoField(serialize=False, primary_key=True)),
                ('books', scarlet.versioning.fields.M2MFromVersion(to='version_models.Book', blank=True)),
                ('cartoon', scarlet.versioning.fields.FKToVersion(swappable=False, blank=True, to='version_models.Cartoon_version', null=True)),
                ('object', models.ForeignKey(related_name='version_version', to='version_models.Store_base')),
            ],
            options={
                'managed': True,
            },
            bases=(models.Model, version_models.StoreVersionReferences),
        ),
        migrations.AddField(
            model_name='book_version',
            name='galleries',
            field=scarlet.versioning.fields.M2MFromVersion(to='version_models.Gallery'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='booknorelated_version',
            name='galleries',
            field=scarlet.versioning.fields.M2MFromVersion(to='version_models.Gallery'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='book_version',
            name='object',
            field=models.ForeignKey(related_name='version_version', to='version_models.Book_base'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='booknorelated_version',
            name='object',
            field=models.ForeignKey(related_name='version_version', to='version_models.BookNoRelated_base'),
            preserve_default=True,
        ),
    ]
