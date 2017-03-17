import copy
import sys

from collections import OrderedDict

from django.utils import timezone
from django.db import models
from django.db.models.fields import FieldDoesNotExist, related, Field
from django import dispatch
from django.utils import formats
from django.core.exceptions import ValidationError

try:
    from ..scheduling.models import Schedulable
except ValueError:
    from scheduling.models import Schedulable


from scarlet.versioning.management import get_db_default_schema

try:
    from django.db.transaction import atomic as xact
except ImportError:
    from .transactions import xact
from . import manager

class Cloneable(models.Model):
    """
    Abstract model that knows how to clone itself.

    All version models automatically implement this model.

    If you want to clone reverse relations
    you should add the attribute names of the
    reverse relations to the _clone_related class
    attribute. Any reverse relations must also
    implement Cloneable.

    This model adds the following field:

    **last_save:** Datetime that gets updated every time the object gets saved.
    """

    last_save = models.DateTimeField(editable=False)

    def _gather_m2ms(self):
        old_m2ms = {}
        for field in self._meta.local_many_to_many:
            if (field.rel.through and
                    field.rel.through._meta.auto_created and
                    field.name not in self.clone_related):
                man = getattr(self, field.name)
                l = list(man.all())
                old_m2ms[field.name] = l
        return old_m2ms

    def _get_field_map(self):
        try:
            cache = self._meta._name_map
        except AttributeError:
            try:
                cache = self._meta.init_name_map()
            except AttributeError:
                cache = {
                    field.name: self._meta.get_field_by_name(field.name)
                    for field
                    in self._meta.get_fields()
                }
        return cache

    def _gather_reverse(self, reverse):
        cache = self._get_field_map()
        rel, mod, direct, m2m = cache[reverse]
        if m2m:
            ctype = 'm2m'
            name = reverse
            manager = getattr(self, name)
        else:
            ctype = 'reverse'
            name = rel.field.name
            manager = getattr(self, rel.get_accessor_name())

        l = list(manager.all())
        return ctype, name, l

    def _gather_reverses(self):
        """
        Get all the related objects that point to this
        object that we need to clone. Uses self.clone_related
        to find those objects.
        """

        old_reverses = {'m2m': {}, 'reverse': {}}
        for reverse in self.clone_related:
            ctype, name, l = self._gather_reverse(reverse)
            old_reverses[ctype][reverse] = (name, l)

        return old_reverses

    def _set_m2ms(self, old_m2ms):
        """
        Creates the same m2m relationships that the old
        object had.
        """

        for k, v in old_m2ms.items():
            if v:
                setattr(self, k, v)

    def _clone_reverses(self, old_reverses):
        """
        Clones all the objects that were previously gathered.
        """

        for ctype, reverses in old_reverses.items():
            for parts in reverses.values():
                sub_objs = parts[1]
                field_name = parts[0]

                attrs = {}
                for sub_obj in sub_objs:
                    if ctype != 'm2m' and not attrs:
                        field = sub_obj._meta.get_field(field_name)
                        attrs = {
                            field.column: getattr(self, field.rel.field_name)
                        }
                    sub_obj._clone(**attrs)

                if ctype == 'm2m':
                    setattr(self, field_name, sub_objs)

    def prep_for_clone(self):
        """
        Hook so implementing classes can customize
        what gets cleared before a clone. By default
        the pk is set to None.
        """
        self.pk = None

    def _clone(self, **attrs):
        """
        Makes a copy of an model instance.

        for every key in **attrs value will
        be set on the new instance.
        """

        with xact():
            # Gather objs we'll need save after
            old_m2ms = self._gather_m2ms()
            old_reverses = self._gather_reverses()

            for k, v in attrs.items():
                setattr(self, k, v)

            # Do the clone
            self.prep_for_clone()
            self.validate_unique()
            # Prevent last save from changing
            self.save(last_save=self.last_save)

            # save m2ms
            self._set_m2ms(old_m2ms)
            # Prevent last save from changing
            self.save(last_save=self.last_save)

            # save reverses
            self._clone_reverses(old_reverses)

    def _delete_reverses(self):
        """
        Delete all objects that would have been cloned
        on a clone command. This is done separately because
        there may be m2m and other relationships that
        would have not been deleted otherwise.
        """

        for reverse in self.clone_related:
            self._delete_reverse(reverse)

        for field in self._meta.local_many_to_many:
            if field.rel.through and \
                    field.rel.through._meta.auto_created and not \
                    field.name in self.clone_related:
                man = getattr(self, field.name)
                man.clear()

    def _delete_reverse(self, reverse):
        cache = self._get_field_map()
        rel, mod, direct, m2m = cache[reverse]

        if m2m:
            if direct:
                manager = getattr(self, reverse)
            else:
                assert False, "cloning reverse m2m is not currently supported"
        else:
            manager = getattr(self, rel.get_accessor_name())

        # Have to do this the slow way so all possible
        # objects are deleted
        for obj in manager.all():
            obj.delete()

    def delete(self, *args, **kwargs):
        """
        Delete clonable relations first, since they may be
        objects that wouldn't otherwise be deleted.

        Calls super to actually delete the object.
        """
        skip_reverses = kwargs.pop('skip_reverses', False)
        if not skip_reverses:
            self._delete_reverses()

        return super(Cloneable, self).delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        """
        Takes an optional last_save keyword argument
        other wise last_save will be set to timezone.now()

        Calls super to actually save the object.
        """
        self.last_save = kwargs.pop('last_save', timezone.now())
        super(Cloneable, self).save(*args, **kwargs)

    @property
    def clone_related(self):
        return getattr(self, '_clone_related', [])

    @classmethod
    def register_related(cls, related_name):
        """
        Register a related item that should be cloned
        when this model is.

        :param related_name: Use the name you would use in filtering
            i.e.: book not book_set.
        """

        if not hasattr(cls, '_clone_related'):
            cls._clone_related = []

        if type(cls._clone_related) != type([]):
            cls._clone_related = list(cls._clone_related)

        if not related_name in cls._clone_related:
            cls._clone_related.append(related_name)

    class Meta:
        abstract = True


def get_meta(meta, **kwargs):
    new_meta = type('Meta', (object,), {})
    if meta:
        for k, v in meta.__dict__.items():
            if v is not None:
                setattr(new_meta, k, v)

    for k, v in kwargs.items():
        if v is not None:
            setattr(new_meta, k, v)
    return new_meta


def add_managers(attrs):
    if not 'objects' in attrs and not '_default_manager' in attrs:
        attrs['objects'] = manager.VersionManager()
    attrs['normal'] = models.Manager()
    attrs['_base_manager'] = models.Manager()
    return attrs

class SharedMeta(models.base.ModelBase):
    def add_to_class(cls, name, value):
        if not cls._meta.abstract:
            version_model = cls.version_model
            base_model = cls.base_model

            if isinstance(value, models.ManyToManyField) or \
                    isinstance(value, models.ForeignKey):
                if version_model:
                    if isinstance(value, models.ManyToManyField):
                        from fields import M2MFromVersion
                        if not isinstance(value, M2MFromVersion):
                            raise TypeError('The model %s cannot contain a ManyToManyField use M2MFromVersion instead' % name)
                        value.db_table = version_model._meta.get_field(name).m2m_db_table()
                else:
                    if value.remote_field.related_name and not \
                                value.remote_field.related_name.endswith('+'):
                        value.remote_field.related_name = "%s_version" % value.remote_field.related_name

                # relationships to self should always point
                # to the base model
                if value.remote_field.model == related.RECURSIVE_RELATIONSHIP_CONSTANT:
                    value.remote_field.model = base_model

        return super(SharedMeta, cls).add_to_class(name, value)

class VersionViewMeta(SharedMeta):
    """
    Meta class for models that are implementing the
    database view to hide the fact there are two
    underlying models and fetch version with a parent
    automatically.
    """

    def __new__(cls, name, bases, attrs):
        meta = attrs.pop('Meta', None)

        # If this is an abstract model don't do anything special
        if meta and getattr(meta, 'abstract', False):
            attrs['Meta'] = meta
            return super(VersionViewMeta, cls).__new__(cls, name,
                                            bases, attrs)
        # List of non field attrs we want to copy
        copy_attrs = attrs.pop('_copy_extra_attrs', [])

        # Construct the base class.

        # An abstract version of the base model
        # needed to make the view model inherit from it.
        ab_base_model = BaseModel

        base_model = None
        base_name = None

        # If we have a custom base model use it
        if meta and hasattr(meta, '_base_model'):
            base_model = meta._base_model
            meta._base_model = None
            assert issubclass(base_model, BaseModel)

            base_name = "%s.%s" % (base_model._meta.app_label,
                                base_model.__name__)

            # Create a new abstract base model we can inherit from
            ab_base_model = type(str(base_name) + "Abs", (BaseModel,), {
                '__module__': base_model.__module__,
                'Meta': get_meta(None, abstract=True)
            })

            # We only copy local fields on purpose
            # No relations allowed on base models
            parent_fields = base_model._meta.local_fields
            for field in parent_fields:
                if not field.primary_key:
                    try:
                        ab_base_model._meta.get_field(field.name)
                    except FieldDoesNotExist:
                        ab_base_model.add_to_class(field.name,
                                               copy.deepcopy(field))

        # Create a base model that isn't abstract
        else:
            base_name = "%s_base" % name
            base_abstract = meta and getattr(meta, 'abstract', False) or False
            base_model = type(base_name, (BaseModel,), {
                '__module__': attrs.get('__module__'),
                'Meta': get_meta(None, abstract=base_abstract)
            })

        versioned_attrs = OrderedDict()
        versioned_attrs['__module__'] = attrs.get('__module__')
        versioned_attrs['Meta'] = get_meta(meta, managed=True)

        # Create the version primary key
        versioned_attrs['vid'] = models.AutoField(primary_key=True)

        # Create a FK to base
        versioned_attrs['object'] = models.ForeignKey(
            base_name, related_name=base_model.get_related_name(name))

        versioned_attrs = add_managers(versioned_attrs)

        # Copy all the fields
        for k, v in attrs.items():
            if k in copy_attrs:
                versioned_attrs[k] = copy.deepcopy(v)
            elif isinstance(v, Field):
                v = copy.deepcopy(v)
                versioned_attrs[k] = v

        version_bases = [BaseVersionedModel]
        custom_version = False
        for base in bases:
            if issubclass(base, models.Model) and not base._meta.abstract:
                raise TypeError('You cannot use a non abstract base model %r with a VersionView model %s.' % (base, name))

            if issubclass(base, BaseModel):
                raise TypeError("VersionView model %r can't inherit from a BaseModel %r" % (cls, base))

            if issubclass(base, BaseVersionedModel):
                if not issubclass(type(base), VersionViewMeta):
                    if custom_version:
                        raise TypeError("Django inheritence will only allow VersionView model %r to inherit from one and only one BaseVersionedModel" % cls)
                    else:
                        version_bases[0] = base
                        custom_version = True
            else:
                version_bases.append(base)

        vname = "%sVersionReferences" % name
        v_mod = type(vname, (object,), {
            '__module__': attrs.get('__module__'),
            'base_model': base_model,
            'version_model': None
        })
        version_bases.append(v_mod)
        setattr(sys.modules[attrs.get('__module__')], vname, v_mod)
        version_model = SharedMeta("%s_version" % name,
                                  tuple(version_bases), versioned_attrs)

        # Make sure the managed = False
        attrs['Meta'] = get_meta(meta, managed=False)

        attrs = add_managers(attrs)

        new_bases = [ab_base_model]
        for base in bases:
            if not issubclass(base, BaseModel):
                new_bases.append(base)

        rname = "%sReferences" % name
        ref_mod = type(rname, (object,), {
            '__module__': attrs.get('__module__'),
            'base_model': base_model,
            'version_model': version_model
        })
        setattr(sys.modules[attrs.get('__module__')], rname, ref_mod)
        new_bases.append(ref_mod)

        mod = super(VersionViewMeta, cls).__new__(cls, name,
                                            tuple(new_bases), attrs)

        # All the models should know about each other
        base_model._meta._view_model = mod
        base_model._meta._version_model = version_model

        version_model._meta._view_model = mod
        version_model._meta._base_model = base_model

        mod._meta._version_model = version_model
        mod._meta._base_model = base_model
        mod._meta._is_view = True

        # Register signals
        published_delete_signal.connect(mod.handle_published_delete_signal,
                            sender=mod,
                            dispatch_uid=mod.__name__ + "delete")
        published_signal.connect(mod.handle_published_signal, sender=mod,
                            dispatch_uid=mod.__name__ + "publish")
        models.signals.pre_delete.connect(mod.handle_pre_delete_signal,
                            sender=mod,
                            dispatch_uid=mod.__name__ + "pre_delete")
        models.signals.post_delete.connect(mod.handle_post_delete_signal,
                            sender=mod,
                            dispatch_uid=mod.__name__ + "post_delete")

        return mod

    def add_to_class(cls, name, value):
        try:
            BaseVersionedModel._meta.get_field(name)
            cls._meta.get_field(name)
            return
        except FieldDoesNotExist:
            pass

        return super(VersionViewMeta, cls).add_to_class(name, value)

class VersionModelMeta(models.base.ModelBase):
    """
    Meta class for models that are transparent
    about there being two models and that fetch
    versions/parents manually.
    """

    def __new__(cls, name, bases, attrs):
        meta = attrs.get('Meta', None)
        base_model = None

        # Only do this work if we have a non-abstract model
        if not getattr(meta, 'abstract', False):
            if not getattr(meta, '_base_model', None) or \
                     not issubclass(meta._base_model, BaseModel):
                raise TypeError("%s must declare a subclass of BaseModel as \
                                it's _base_model in it's meta class" % name)
            else:
                base_model = meta._base_model
                meta._base_model = None

            # Create a FK to base
            attrs['object'] = models.ForeignKey(
                base_model.__name__,
                related_name=base_model.get_related_name(name),
                editable=False,
            )
            attrs = add_managers(attrs)

        mod = super(VersionModelMeta, cls).__new__(cls, name, bases, attrs)

        # The models should know about each other
        if base_model:
            mod._meta._base_model = base_model
            base_model._meta._version_model = mod

        return mod


class BaseModel(models.Model):
    """
    Abstract model for the base model of your versioned model.
    This is the model where there is only one row per
    item and that each version relates to. Any custom base
    models must inherit from this one.

    Provides the following fields:

    `is_published`: Does this item contain any live versions?

    `created_date`: Date this item was originally created.

    `v_last_save`: When the current live item was last saved,
    may be null.
    """

    is_published = models.BooleanField(editable=False, default=False)

    created_date = models.DateTimeField(default=timezone.now,
                                        editable=False)

    v_last_save = models.DateTimeField(null=True, editable=False)

    _version = None

    class Meta:
        abstract = True

    @classmethod
    def get_related_name(cls, name=None):
        """
        Override this method and provide a unique related_name to avoid
        conflicts if multiple VersionViews are using the same _base_model
        in their Meta attributes.
        """
        return 'version'

    def get_version(self, state=None, date=None):
        """
        Get a particular version of an item

        :param state: The state you want to get.
        :param date: Get a version that was published before or on this date.
        """

        version_model = self._meta._version_model
        q = version_model.objects.filter(object_id=self.pk)
        if state:
            q = version_model.normal.filter(object_id=self.pk, state=state)

        if date:
            q = q.filter(date_published__lte=date)

        q = q.order_by('-date_published')

        results = q[:1]
        if results:
            return results[0]
        return None

    def _get_version(self):
        if self._version is None:
            self._version = self.get_version()
        return self._version

    def _set_version(self, version):
        self._version = version

    current_version = property(_get_version, _set_version)


class BaseVersionedModel(Cloneable, Schedulable):
    """
    Base abstract model for the versioned model data.

    Inherits from both Cloneable and Schedulable.

    Implemented by both VersionView and VersionModel.
    """

    # How many archived versions should we keep?
    NUM_KEEP_ARCHIVED = 5

    # Supported States
    PUBLISHED = 'published'
    DRAFT = 'draft'
    SCHEDULED = 'scheduled'
    ARCHIVED = 'archived'

    UNIQUE_STATES = (
        PUBLISHED,
        DRAFT
    )

    STATES = (
        (PUBLISHED, PUBLISHED),
        (SCHEDULED, SCHEDULED),
        (DRAFT, DRAFT),
        (ARCHIVED, ARCHIVED),
    )

    state = models.CharField(max_length=50, choices=STATES,
                             editable=False)

    # Date the item was last scheduled to go live
    last_scheduled = models.DateTimeField(null=True, editable=False)

    # The date the item is supposed-to/actually went live
    date_published = models.DateTimeField(null=True, editable=False)

    # username who scheduled the publish
    user_published = models.CharField(max_length=255, null=True,
                                      editable=False)

    class Meta:
        abstract = True

    def prep_for_clone(self):
        self.vid = None
        self.user_published = None

    def unpublish(self):
        """
        Unpublish this item.

        This will set and currently published versions to
        the archived state and delete all currently scheduled
        versions.
        """
        assert self.state == self.DRAFT

        with xact():
            self._publish(published=False)

            # Delete all scheduled items
            klass = self.get_version_class()
            for obj in klass.normal.filter(object_id=self.object_id,
                                            state=self.SCHEDULED):
                obj.delete()

    def publish(self, user=None, when=None):
        """
        Publishes a item and any sub items.
        A new transaction will be started if
        we aren't already in a transaction.

        Should only be run on draft items
        """

        assert self.state == self.DRAFT

        user_published = 'code'
        if user:
            user_published = user.username

        now = timezone.now()

        with xact():
            # If this item hasn't got live yet and no new date was specified
            # delete the old scheduled items and schedule this one on that date
            published = False
            if getattr(self._meta, '_is_view', False):
                published = self.is_published
            else:
                published = self.object.is_published

            if not when and not published and self.last_scheduled:
                klass = self.get_version_class()
                for obj in klass.normal.filter(object_id=self.object_id,
                                        last_scheduled=self.last_scheduled,
                                        state=self.SCHEDULED):
                    when = self.date_published
                    obj.delete()

            when = when or now

            # Drafts get preserved so save the
            # time we last cloned this
            if self.state == self.DRAFT:
                self.last_scheduled = now
                self.date_published = when
                self.save(last_save=now)

            self._clone()

            self.user_published = user_published
            self.state = self.SCHEDULED
            self.save()

            self.schedule(when=when)

    def _delete_reverse(self, reverse):
        try:
            return super(BaseVersionedModel, self)._delete_reverse(reverse)
        except KeyError:
            # Could this be on the view model?
            if not hasattr(self._meta, '_view_model'):
                raise

            # XXX: These query CAN'T do any joins with a
            # version view table, or bad things will happen
            # need to test for that
            sub = self._meta._view_model(object_id=self.object_id,
                                         vid=self.vid)
            return sub._delete_reverse(reverse)

    def _gather_reverse(self, reverse):
        try:
            return super(BaseVersionedModel, self)._gather_reverse(reverse)
        except KeyError:
            # Could this be on the view model?
            if not hasattr(self._meta, '_view_model'):
                raise

            # These query CAN'T do any joins with a
            # version view table, or bad things will happen
            # need to test for that
            sub = self._meta._view_model(object_id=self.object_id,
                                         vid=self.vid)
            return sub._gather_reverse(reverse)

    @property
    def clone_related(self):
        if hasattr(self._meta, '_view_model'):
            return getattr(self._meta._view_model, '_clone_related', [])
        return getattr(self, '_clone_related', [])

    def make_draft(self):
        """
        Make this version the draft
        """
        assert self.__class__ == self.get_version_class()

        # If this is draft do nothing
        if self.state == self.DRAFT:
            return

        with xact():
            # Delete whatever is currently this draft
            try:
                klass = self.get_version_class()
                old_draft = klass.normal.get(object_id=self.object_id,
                                             state=self.DRAFT)
                old_draft.delete()
            except klass.DoesNotExist:
                pass

            # Set this to draft and save
            self.state = self.DRAFT
            # Make last_scheduled and last save match on draft
            self.last_save = self.last_scheduled
            self._clone()

    def get_version_class(self):
        klass = self.__class__
        if getattr(self._meta, '_is_view', False):
            klass = self._meta._version_model
        return klass

    def _publish(self, published=True, **kwargs):
        with xact():
            filter_args = {
                'state': self.PUBLISHED,
                'object_id': self.object_id,
            }

            klass = self.get_version_class()
            klass.normal.filter(**filter_args).update(
                                  state=self.ARCHIVED)

            now = timezone.now()

            if published:
                self.state = self.PUBLISHED
                self.date_published = now
            else:
                self.last_scheduled = None
                self.date_published = None

            self.save()

            # Update the base model as published and cache the scheduled
            # date for comparisons.
            self._meta._base_model.objects.filter(pk=self.object_id
                                    ).update(is_published=published,
                                             v_last_save=self.last_scheduled)
            self.is_published = published
            self.v_last_save = self.last_scheduled

        # Send published signal
        klass = self.__class__
        if hasattr(self._meta, '_view_model'):
            klass = self.__class__

        published_signal.send(sender=klass, instance=self)

    def purge_archives(self):
        """
        Delete older archived items.

        Use the class attribute NUM_KEEP_ARCHIVED to control
        how many items are kept.
        """

        klass = self.get_version_class()
        qs = klass.normal.filter(object_id=self.object_id,
                        state=self.ARCHIVED
                        ).order_by('-last_save')[self.NUM_KEEP_ARCHIVED:]

        for obj in qs:
            obj._delete_reverses()
            klass.normal.filter(vid=obj.vid).delete()

    def status_line(self):
        """
        Returns a status line for an item.

        Only really interesting when called for a draft
        item as it can tell you if the draft is the same as
        another version.
        """

        date = self.date_published
        status = self.state.title()
        if self.state == self.DRAFT:
            # Check if this item has changed since
            # our last publish
            status = "Draft saved"
            date = self.last_save
            if date and self.last_save == self.last_scheduled:
                # We need to figure out if the item it is based on
                # is either live now or will be live at some point.

                # If last_scheduled is less than or equal to
                # v_last_save this item is or will go live
                # at some point. Otherwise it won't
                # so we'll leave state as draft.
                if self.v_last_save:
                    if self.last_scheduled >= self.v_last_save:
                        status = self.PUBLISHED.title()

                    # The date this was scheduled is greater than
                    # what is currently live, this will go live at
                    # some point
                    if self.last_scheduled > self.v_last_save:
                        status = "Publish Scheduled"
                else:
                    status = "Publish Scheduled"

                date = self.date_published

        if date:
            status = "%s: %s" % (status,
                             formats.date_format(date, "SHORT_DATE_FORMAT"))
        return status

    def schedule(self, when=None, action=None, **kwargs):
        """
        Schedule this item to be published.

        :param when: Date/time when this item should go live. None means now.
        """
        action = '_publish'
        super(BaseVersionedModel, self).schedule(when=when, action=action,
                                                 **kwargs)


class VersionView(BaseVersionedModel):
    """
    Abstract base model for implementations
    that are pointing to a database view
    that handles the joining of the two tables for you.

    Implementations can then rely on schema path switching
    to filter on either draft or published states.

    Outside of that you will either need to query the underlying
    model or use the public schema and specify the correct
    filter parameters to filter out the states/versions that you
    are not interested in wherever this model is used in a query.

    Inherits from `BaseVersionedModel`

    Contains the following fields:

    vid: The unique id of this version, this is unique within this table.

    object_id: The id of the item on the base_model.

    last_scheduled: Date the item was last scheduled to go live. May be null.

    date_published: The date the item is supposed-to/actually went live.
    May be null.

    user_published: The username of the user who published. May be null.

    last_save: The date this version was last_saved.
    """
    __metaclass__ = VersionViewMeta

    # What version id is this
    vid = models.PositiveIntegerField(unique=True, editable=False)

    # What the object id, same as pk just for consistency
    object_id = models.PositiveIntegerField(editable=False)

    class Meta:
        abstract = True

    def get_scheduled_filter_args(self):
        return {
            'vid': self.vid
        }

    def _clone(self):
        # We should only clone from a draft view in that mode
        assert self.state == self.DRAFT
        return super(VersionView, self)._clone()

    def delete(self, **kwargs):
        with xact():
            # Delete's happen in default schema so that all
            # versions are found.
            with manager.SwitchSchema(get_db_default_schema()):
                super(VersionView, self).delete(**kwargs)

    def _get_should_save_base(self):
        if not hasattr(self, '_should_save_base'):
            self._should_save_base = False
        return self._should_save_base

    def _set_should_save_base(self, value):
        self._should_save_base = value

    should_save_base = property(_get_should_save_base, _set_should_save_base)

    def save(self, *args, **kwargs):
        models.signals.pre_save.send(sender=self.__class__, instance=self,
            raw=kwargs.get('raw'), using=kwargs.get('using'))

        last_save = kwargs.pop('last_save', timezone.now())
        with xact():
            # Make sure we have a state
            if not self.vid:
                self.state = self.DRAFT

            # Get a version instance
            version = self._meta._version_model()
            base = self._meta._base_model()

            # Build out the version
            for f in self._meta.local_fields:
                try:
                    attname = f.name
                    version._meta.get_field(attname)
                    if isinstance(f, models.ForeignKey):
                        attname = "%s_id" % f.name

                    setattr(version, attname, getattr(self, attname))

                # version doesn't have this field
                except FieldDoesNotExist:
                    if self.should_save_base:
                        setattr(base, f.name, getattr(self, attname))

            # Make sure we have a base
            if not self.object_id or self.should_save_base:
                base.is_published = self.is_published
                base.pk = self.pk

                base.save(*args, **kwargs)
                self.pk = base.pk

                # set base object
                version.object = base
            else:
                version.object_id = self.object_id

            # Save the version and copy the db state
            version.save(last_save=last_save)

            self.vid = version.vid
            self._state = version._state
            self.state = version.state
            self.last_save = version.last_save
        models.signals.post_save.send(sender=self.__class__, instance=self,
            raw=kwargs.get('raw'), using=kwargs.get('using'))

    def validate_unique(self, *args, **kwargs):
        """
        Calls super validate_unique and, after that is done, runs
        through any field_names listed in `self.versioned_unique`
        and checks that this is the only item with this name.

        This relies on using the public schema when running this
        check.

        These checks contain race conditions since it all happens
        before saves and so should not be relied upon for uniqueness
        but help with form validation.
        """

        super(BaseVersionedModel, self).validate_unique(*args, **kwargs)
        if hasattr(self, 'versioned_unique'):
            unique_checks = []
            for field in self.versioned_unique:
                unique_checks.append((self.__class__, (field,)))
            errors = self._perform_unique_checks(unique_checks)

            if errors:
                raise ValidationError(errors)

    @classmethod
    def register_related(cls, related_name):
        super(VersionView, cls).register_related(related_name)
        cls._meta._version_model.register_related(related_name)

    @classmethod
    def invalidate_cache(cls, sender, instance, **kwargs):
        try:
            try:
                from ..cache import cache_manager
            except ValueError:
                from cache import cache_manager
            cache_manager.invalidate_cache(cls, instance=instance)
        except ImportError:
            pass

    @classmethod
    def handle_published_delete_signal(cls, sender, instance, **kwargs):
        cls.invalidate_cache(sender, instance, **kwargs)

    @classmethod
    def handle_published_signal(cls, sender, instance, **kwargs):
        cls.invalidate_cache(sender, instance, **kwargs)

    @classmethod
    def handle_pre_delete_signal(cls, sender, instance, **kwargs):
        with xact():
            klass = cls._meta._version_model
            for obj in klass.normal.filter(object_id=instance.object_id):
                obj._delete_reverses()

    @classmethod
    def handle_post_delete_signal(cls, sender, instance, **kwargs):
        published_delete_signal.send(sender, instance=instance)


class VersionModel(BaseVersionedModel):
    """
    Abstract base model for implementations
    that are transparent about the fact that
    there are two models/tables for this model.

    Implementations that use this model will need to take
    care to specify the correct filter parameters to filter
    out the states/versions that you are not interested in
    wherever this model is used in a query. This may not
    always be obvious especially in complex joins or when
    using select_related or prefetch_related.

    Inherits from `BaseVersionedModel`

    Contains the following fields:

    vid: The unique id of this version, this is unique within this table.

    object: A foreign key to the base item model.

    last_scheduled: Date the item was last scheduled to go live. May be null.

    date_published: The date the item is supposed-to/actually went live.
    May be null.

    user_published: The username of the user who published. May be null.

    last_save: The date this version was last_saved.
    """

    __metaclass__ = VersionModelMeta

    # Setup the primary key
    vid = models.AutoField(primary_key=True)

    class Meta:
        abstract = True

    def _get_v_last_save(self):
        return self.object.v_last_save

    def _set_v_last_save(self, value):
        return None

    v_last_save = property(_get_v_last_save, _set_v_last_save)

    def validate_unique(self, *args, **kwargs):
        """
        Calls super validate_unique and, after that is done, runs
        through any field_names listed in `self.versioned_unique`
        and checks that this is the only item with this name.

        These checks contain race conditions since it all happens
        before saves and so should not be relied upon for uniqueness
        but help with form validation.
        """

        super(BaseVersionedModel, self).validate_unique(*args, **kwargs)
        if hasattr(self, 'versioned_unique'):
            errors = {}

            for field in self.versioned_unique:
                lookup_kwargs = {field: getattr(self, field)}
                qs = self.__class__._default_manager.filter(**lookup_kwargs)

                # Exclude the current object from the query if we are editing
                # an instance (as opposed to creating a new one)
                if self.object_id:
                    qs = qs.exclude(object_id=self.object_id)

                if qs.exists():
                    msg = self.unique_error_message(self.__class__, (field,))
                    errors[field] = msg

            if errors:
                raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """
        Saves this item.

        Creates a default base if there isn't
        one already.
        """
        with xact():
            if not self.vid:
                self.state = self.DRAFT

                if not self.object_id:
                    base = self._meta._base_model(is_published=False)
                    base.save(*args, **kwargs)
                    self.object = base

            super(VersionModel, self).save(*args, **kwargs)

# Setup signal for published
published_signal = dispatch.Signal(providing_args=['instance'])
published_delete_signal = dispatch.Signal(providing_args=['instance'])
