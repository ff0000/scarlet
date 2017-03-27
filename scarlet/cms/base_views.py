from functools import update_wrapper
import urlparse
import copy

from django import VERSION as DJANGO_VERSION
from django import http
from django.views import generic
from django.utils.decorators import method_decorator, classonlymethod
from django.views.decorators.csrf import csrf_protect
from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils.encoding import force_unicode

from . import helpers
from . import renders
from . import widgets
from .models import CMSLog
from .internal_tags import handler as tag_handler


class BaseView(generic.base.View):
    """
    Base view for all Views. This is a class based view
    that uses render classes to handle the preparation of an
    response.

    Render classes are classes that return a response of
    some kind from a view, such as a HttpResponse object or a string.
    The only requirement is that they have a render method that takes
    a request and keyword arguments. Those keyword arguments should be
    considered the context.

    :param renders: A dictionary where the values are render \
    class instances.
    :param render_type: A string that denotes what renderer \
    should be used. This must but a key in the renders dictionary. \
    Default is 'response'.
    """

    render_type = 'response'

    def get_render_data(self, **kwargs):
        """
        Because of the way mixin inheritance works
        we can't have a default implementation of
        get_context_data on the this class, so this
        calls that method if available and returns
        the resulting context.
        """
        if hasattr(self, 'get_context_data'):
            data = self.get_context_data(**kwargs)
        else:
            data = kwargs
        return data

    def render(self, request, collect_render_data=True, **kwargs):
        """
        Render this view. This will call the render method
        on the render class specified.

        :param request: The request object
        :param collect_render_data: If True we will call \
        the get_render_data method to pass a complete context \
        to the renderer.
        :param kwargs: Any other keyword arguments that should \
        be passed to the renderer.
        """
        assert self.render_type in self.renders
        render = self.renders[self.render_type]
        if collect_render_data:
            kwargs = self.get_render_data(**kwargs)

        return render.render(request, **kwargs)


class SiteView(BaseView):
    """
    Base view that provides a classmethod to render
    the view as a string instead of as a HttpResponse.
    """

    def get_as_string(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)

    @classonlymethod
    def as_string(cls, **initkwargs):
        """
        Similar to the as_view classmethod except this method will
        render this view as a string. When rendering a view this way
        the request will always be routed to the get method.
        The default render_type is 'string' unless you specify
        something else. If you provide your own render_type be sure
        to specify a render class that returns a string.
        """

        if not 'render_type' in initkwargs:
            initkwargs['render_type'] = 'string'

        for key in initkwargs:
            if key in cls.http_method_names:
                raise TypeError(u"You tried to pass in the %s method name as a"
                                u" keyword argument to %s(). Don't do that."
                                % (key, cls.__name__))
            if not hasattr(cls, key):
                raise TypeError(u"%s() received an invalid keyword %r" % (
                    cls.__name__, key))

        def view(request, *args, **kwargs):
            try:
                self = cls(**initkwargs)
                self.request = request
                self.args = args
                self.kwargs = kwargs
                return self.get_as_string(request, *args, **kwargs)
            except http.Http404:
                return ""

        # take name and docstring from class
        update_wrapper(view, cls, updated=())

        return view


class CMSView(BaseView):
    """
    Base class for CMS Views, should be used as the main view
    class for all views that will be registered with a bundle.

    :param base_template: The default base template, gets passed \
    to the main template as 'base'.
    :param default_template: The main template for this view.
    :param object_header_tmpl: The template to render for an object \
    header.
    :param render_type: The render_type, defaults to 'response'.
    :param renders: The dictionary of render views that this view \
    knows how to set. Unless specified otherwise, this will be set \
    to a CMSRender instance 'response' and RenderString instance \
    'string'; both instances are initialized with the `default_template`.
    :param bundle: The bundle that this view instance is attached \
    to. Set by the bundle on initialization.
    :param can_submit: Does this instance support form submission. \
    Set to false by bundle when necessary.
    :param required_groups: Groups that are required in order to render \
    this view. Defaults to None, may be set by bundle.
    """

    object_header_tmpl = "cms/object_header.html"

    render_type = 'response'

    base_template = 'cms/base_bundle_view.html'

    renders = {}

    bundle = None

    can_submit = True

    required_groups = None

    ORIGIN_ARGUMENT = 'o'

    name = None

    def __init__(self, *args, **kwargs):
        self.extra_render_data = {}
        self.changed_kwargs = kwargs
        super(CMSView, self).__init__(*args, **kwargs)
        if not self.renders:
            self.renders = {
                'response': renders.CMSRender(template=self.default_template,
                               base=self.base_template),
                'string': renders.RenderString(template=self.default_template,
                               base=self.base_template)
            }

    def customized_return_url(self, default_url):
        redirect_url = self.request.GET.get(self.ORIGIN_ARGUMENT)
        if redirect_url:
            base = self.request.path.split('/')
            if len(base) > 1 and redirect_url.startswith('/%s' % base[1]):
                return redirect_url

        return default_url

    def get_navigation(self):
        """
        Hook for overiding navigation per view.
        Defaults to calling get_navigation on the
        bundle.
        """
        return self.bundle.get_navigation(self.request, **self.kwargs)

    def add_to_render_data(self, **kwargs):
        """
        Any keyword arguments provided will be passed to
        the renderer when this view is rendered.
        """
        self.extra_render_data.update(kwargs)

    def get_tags(self, view_object=None):
        """
        This method return a list of tags to use in the template
        :return: list of tags
        """
        tags = [force_unicode(self.bundle.get_title())]
        back_bundle = self.get_back_bundle()
        if back_bundle and back_bundle != self.bundle:
            tags.append(force_unicode(back_bundle.get_title()))
        if view_object:
            tags.append(force_unicode(view_object))

        return tags

    def get_back_bundle(self, start_bundle=None):
        if not start_bundle:
            start_bundle = self.bundle

        if getattr(start_bundle, 'main_list', None):
            main_list = start_bundle.main_list
            bundle = main_list.get_bundle(start_bundle, {}, self.kwargs)
            return bundle
        return None

    def get_render_data(self, **kwargs):
        """
        Returns all data that should be passed to the renderer.
        By default adds the following arguments:

        * **bundle** - The bundle that is attached to this view instance.
        * **url_params** - The url keyword arguments. i.e.: self.kwargs.
        * **user** - The user attached to this request.
        * **base** - Unless base was already specified this gets set to \
        'self.base_template'.
        * **navigation** - The navigation bar for the page
        * **object_header_tmpl** - The template to use for the \
        object_header. Set to `self.object_header_tmpl`.
        * **back_bundle** - The back_back bundle is bundle that is linked to \
        from the object header as part of navigation. If there is an 'obj' \
        argument in the context to render, this will be set to the bundle \
        pointed to by the `main_list` attribute of this view's bundle. \
        If this is not set, the template's back link will point to the \
        admin_site's home page.
        """

        obj = getattr(self, 'object', None)
        data = dict(self.extra_render_data)
        data.update(kwargs)
        data.update({
            'bundle': self.bundle,
            'navigation': self.get_navigation(),
            'url_params': self.kwargs,
            'user': self.request.user,
            'object_header_tmpl': self.object_header_tmpl,
            'view_tags': tag_handler.tags_to_string(self.get_tags(obj))
        })

        if not 'base' in data:
            data['base'] = self.base_template

        if not 'back_bundle' in data:
            data['back_bundle'] = self.get_back_bundle()

        return super(CMSView, self).get_render_data(**data)

    def _user_in_groups(self, user, allowed_groups):
        groups = getattr(user, 'cached_groups', None)
        if groups is None:
            user.cached_groups = user.groups.all()

        for group in user.cached_groups:
            if group.name in allowed_groups:
                return True
        return False

    def can_view(self, user):
        """
        Returns True if user has permission to render this view.

        At minimum this requires an active staff user. If the required_groups
        attribute is not empty then the user must be a member of at least one
        of those groups. If there are no required groups set for the view but
        required groups are set for the bundle then the user must be a member
        of at least one of those groups. If there are no groups to check this
        will return True.
        """

        if user.is_staff and user.is_active:
            if user.is_superuser:
                return True
            elif self.required_groups:
                return self._user_in_groups(user, self.required_groups)
            elif self.bundle.required_groups:
                return self._user_in_groups(user, self.bundle.required_groups)
            else:
                return True

        return False

    def get_url_kwargs(self, request_kwargs=None, **kwargs):
        """
        Get the kwargs needed to reverse this url.

        :param request_kwargs: The kwargs from the current request. \
        These keyword arguments are only retained if they are present \
        in this bundle's known url_parameters.
        :param kwargs: Keyword arguments that will always be kept.
        """

        if not request_kwargs:
            request_kwargs = getattr(self, 'kwargs', {})

        for k in self.bundle.url_params:
            if k in request_kwargs and not k in kwargs:
                kwargs[k] = request_kwargs[k]
        return kwargs

    def customize_form_widgets(self, form_class, fields=None):
        """
        Hook for customizing widgets for a form_class. This is needed
        for forms that specify their own fields causing the
        default db_field callback to not be run for that field.

        Default implementation checks for APIModelChoiceWidgets
        or APIManyChoiceWidgets and runs the update_links method
        on them. Passing the admin_site and request being used.

        Returns a new class that contains the field with the initialized
        custom widget.
        """
        attrs = {}
        if fields:
            fields = set(fields)

        for k, f in form_class.base_fields.items():
            if fields and not k in fields:
                continue

            if isinstance(f.widget, widgets.APIModelChoiceWidget) \
                    or isinstance(f.widget, widgets.APIManyChoiceWidget):
                field = copy.deepcopy(f)
                field.widget.update_links(self.request, self.bundle.admin_site)
                attrs[k] = field

        if attrs:
            form_class = type(form_class.__name__, (form_class,), attrs)

        return form_class

    @method_decorator(csrf_protect)
    def dispatch(self, request, *args, **kwargs):
        """
        Overrides the custom dispatch method to raise a Http404
        if the current user does not have view permissions.
        """
        self.request = request
        self.args = args
        self.kwargs = kwargs

        if not self.can_view(request.user):
            raise http.Http404

        return super(CMSView, self).dispatch(request, *args, **kwargs)

    def as_string(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)

class ModelCMSMixin(object):
    """
    Mixin for use with all cms views that interact with database models.

    :param parent_field: The name of the field on the model \
    that points a parent that must be present. This should either be \
    a foreign key or a many to many field. Defaults to None.
    :param parent_lookups: A list of field names to use when constructing \
    the query for the parent object. If `parent_field` is present defaults \
    to ('pk',) otherwise default is None.
    :param slug_field: The name of the field on the model that should \
    be used as the keyword argument when looking up an object. Used in \
    combination with `slug_url_kwarg`. Defaults to 'pk'
    :param slug_url_kwarg: The name of the URLConf keyword argument \
    that contains the value to filter on. Used in combination with \
    `slug_field`. Defaults to 'pk'.
    :param base_filter_kwargs: Attribute to provide a dictionary of \
    default keyword arguments for the base queryset.
    """

    parent_lookups = None
    parent_field = None

    slug_field = 'pk'
    slug_url_kwarg = 'pk'

    base_filter_kwargs = {}

    def get_formfield_overrides(self):
        """
        Hook for specifying the default arguments when
        creating a form field for a db field.

        By default adds DateWidget for date fields,
        TimeChoiceWidget for time fields, SplitDateTime
        for datetime fields, and APIChoiceWidget for
        foreign keys.
        """
        return helpers.FORMFIELD_FOR_DBFIELD_DEFAULTS

    def formfield_for_dbfield(self, db_field, **kwargs):
        """
        Hook for specifying the form Field instance for a given
        database Field instance. If kwargs are given, they're
        passed to the form Field's constructor.

        Default implementation uses the overrides returned by
        `get_formfield_overrides`. If a widget is an instance
        of APIChoiceWidget this will do lookup on the current
        admin site for the bundle that is registered for that
        module as the primary bundle for that one model. If a
        match is found then this will call update_links on that
        widget to store the appropriate urls for the javascript
        to call. Otherwise the widget is removed and the default
        select widget will be used instead.
        """

        overides = self.get_formfield_overrides()

        # If we've got overrides for the formfield defined, use 'em. **kwargs
        # passed to formfield_for_dbfield override the defaults.
        for klass in db_field.__class__.mro():
            if klass in overides:
                kwargs = dict(overides[klass], **kwargs)
                break

        # Our custom widgets need special init
        mbundle = None
        extra = kwargs.pop('widget_kwargs', {})
        widget = kwargs.get('widget')
        if kwargs.get('widget'):
            if widget and isinstance(widget, type) and \
                            issubclass(widget, widgets.APIChoiceWidget):
                mbundle = self.bundle.admin_site.get_bundle_for_model(
                                                db_field.rel.to)
                if mbundle:
                    widget = widget(db_field.rel, **extra)
                else:
                    widget = None

        if getattr(self, 'prepopulated_fields', None) and \
                        not getattr(self, 'object', None) and \
                        db_field.name in self.prepopulated_fields:
            extra = kwargs.pop('widget_kwargs', {})
            attr = extra.pop('attrs', {})
            attr['data-source-fields'] = self.prepopulated_fields[db_field.name]
            extra['attrs'] = attr
            if not widget:
                from django.forms.widgets import TextInput
                widget = TextInput(**extra)
            elif widget and isinstance(widget, type):
                widget = widget(**extra)

        kwargs['widget'] = widget

        field = db_field.formfield(**kwargs)
        if mbundle:
            field.widget.update_links(self.request, self.bundle.admin_site)
        return field

    def log_action(self, instance, action, action_date=None, url="",
                   update_parent=True):
        """
        Store an action in the database using the CMSLog model.
        The following attributes are calculated and set on the log entry:

         * **model_repr** - A unicode representation of the instance.
         * **object_repr** - The verbose_name of the instance model class.
         * **section** - The name of ancestor bundle that is directly \
         attached to the admin site.

        :param instance: The instance that this action was performed \
        on.
        :param action: The action type. Must be one of the options \
        in CMSLog.ACTIONS.
        :param action_date: The datetime the action occurred.
        :param url: The url that the log entry should point to, \
        Defaults to an empty string.
        :param update_parent: If true this will update the last saved time \
        on the object pointed to by this bundle's object_view. \
        Defaults to True.
        """

        section = None
        if self.bundle:
            bundle = self.bundle
            while bundle.parent:
                bundle = bundle.parent
            section = bundle.name

        # if we have a object view that comes from somewhere else
        # save it too to update it.
        changed_object = instance
        bundle = self.bundle
        while bundle.object_view == bundle.parent_attr:
            bundle = bundle.parent

        if update_parent and changed_object.__class__ != bundle._meta.model:
            object_view, name = bundle.get_initialized_view_and_name(
                                    bundle.object_view, kwargs=self.kwargs)

            changed_object = object_view.get_object()
            changed_object.save()

        if not section:
            section = ""

        if url:
            url = urlparse.urlparse(url).path

        rep = unicode(instance)
        if rep:
            rep = rep[:255]

        log = CMSLog(action=action, url=url, section=section,
                     model_repr=instance._meta.verbose_name,
                     object_repr=rep,
                     user_name=self.request.user.username,
                     action_date=action_date)
        log.save()

    def get_filter(self, **filter_kwargs):
        """
        Returns a list of Q objects that can be passed
        to an queryset for filtering.

        Default implementation returns a Q
        object for `base_filter_kwargs` and any
        passed in keyword arguments.
        """
        filter_kwargs.update(self.base_filter_kwargs)
        if filter_kwargs:
            return [models.Q(**filter_kwargs)]
        return []

    def get_queryset(self, **filter_kwargs):
        """
        Get the list of items for this view. This will
        call the `get_parent_object` method before doing
        anything else to ensure that a valid parent object
        is present. If a parent_object is returned it gets
        set to `self.parent_object`.

        If a queryset has been set then that queryset will be used.
        Otherwise the default manager for the provided
        model will be used.

        Once we have a queryset, the `get_filter` method
        is called and added to the queryset which is then
        returned.
        """
        self.parent_object = self.get_parent_object()

        if self.queryset is not None:
            queryset = self.queryset
            if hasattr(queryset, '_clone'):
                queryset = queryset._clone()
        elif self.model is not None:
            queryset = self.model._default_manager.filter()
        else:
            raise ImproperlyConfigured(u"'%s' must define 'queryset' or 'model'"
                                       % self.__class__.__name__)

        q_objects = self.get_filter(**filter_kwargs)
        queryset = queryset.filter()
        for q in q_objects:
            queryset = queryset.filter(q)

        return queryset

    def get_parent_object(self):
        """
        Lookup a parent object. If parent_field is None
        this will return None. Otherwise this will try to
        return that object.

        The filter arguments are found by using the known url
        parameters of the bundle, finding the value in the url keyword
        arguments and matching them with the arguments in
        `self.parent_lookups`. The first argument in parent_lookups
        matched with the value of the last argument in the list of bundle
        url parameters, the second with the second last and so forth.

        For example let's say the parent_field attribute is 'gallery'
        and the current bundle knows about these url parameters:

        * adm_post
        * adm_post_gallery

        And the current value for 'self.kwargs' is:

        * adm_post = 2
        * adm_post_gallery = 3

        if parent_lookups isn't set the filter for the queryset
        on the gallery model will be:

        * pk = 3

        if parent_lookups is ('pk', 'post__pk') then the filter
        on the queryset will be:

        * pk = 3
        * post__pk = 2

        The model to filter on is found by finding the relationship
        in self.parent_field and filtering on that model.
        If a match is found, 'self.queryset` is changed to
        filter on the parent as described above and the parent
        object is returned. If no match is found, a Http404 error
        is raised.
        """

        if self.parent_field:
            # Get the model we are querying on
            if getattr(self.model._meta, 'init_name_map', None):
                # pre-django-1.8
                cache = self.model._meta.init_name_map()
                field, mod, direct, m2m = cache[self.parent_field]
            else:
                # 1.10
                if DJANGO_VERSION[1] >= 10:
                    field = self.model._meta.get_field(self.parent_field)
                    m2m = field.is_relation and field.many_to_many
                    direct = not field.auto_created or field.concrete
                else:
                    # 1.8 and 1.9
                    field, mod, direct, m2m = self.model._meta.get_field(self.parent_field)

            to = None
            field_name = None
            if self.parent_lookups is None:
                self.parent_lookups = ('pk',)

            url_params = list(self.bundle.url_params)
            if url_params and getattr(self.bundle, 'delegated', False):
                url_params = url_params[:-1]

            offset = len(url_params) - len(self.parent_lookups)
            kwargs = {}
            for i in range(len(self.parent_lookups) - 1):
                k = url_params[offset + i]
                value = self.kwargs[k]
                kwargs[self.parent_lookups[i + 1]] = value

            main_arg = self.kwargs[url_params[-1]]
            main_key = self.parent_lookups[0]

            if m2m:
                rel = getattr(self.model, self.parent_field)
                kwargs[main_key] = main_arg
                if direct:
                    to = rel.field.rel.to
                    field_name = self.parent_field
                else:
                    try:
                        from django.db.models.fields.related import (
                            ForeignObjectRel)
                        if isinstance(rel.rel, ForeignObjectRel):
                            to = rel.rel.related_model
                        else:
                            to = rel.rel.model
                    except ImportError:
                        to = rel.rel.model
                    field_name = rel.rel.field.name
            else:
                to = field.rel.to
                if main_key == 'pk':
                    to_field = field.rel.field_name
                    if to_field == 'vid':
                        to_field = 'object_id'
                else:
                    to_field = main_key
                kwargs[to_field] = main_arg

            # Build the list of arguments
            try:
                obj = to.objects.get(**kwargs)
                if self.queryset is None:
                    if m2m:
                        self.queryset = getattr(obj, field_name)
                    else:
                        self.queryset = self.model.objects.filter(
                                                    **{self.parent_field: obj})
                return obj
            except to.DoesNotExist:
                raise http.Http404
        return None


class ModelCMSView(CMSView):
    """
    Base view for CMS views that interact with models.
    Inherits from CMSView.

    :param custom_model_name: A alternate verbose name for the \
    given model.
    """

    custom_model_name = None
    custom_model_name_plural = None

    def __init__(self, *args, **kwargs):
        super(ModelCMSView, self).__init__(*args, **kwargs)
        self.pk_url_kwarg = None

    def write_message(self, status=messages.INFO, message=None):
        """
        Writes a message to django's messaging framework and
        returns the written message.

        :param status: The message status level. Defaults to \
        messages.INFO.
        :param message: The message to write. If not given, \
        defaults to appending 'saved' to the unicode representation \
        of `self.object`.
        """
        if not message:
                message = u"%s saved" % self.object
        messages.add_message(self.request, status, message)
        return message

    def get_url_kwargs(self, request_kwargs=None, **kwargs):
        """
        If request_kwargs is not specified, self.kwargs is used instead.

        If 'object' is one of the kwargs passed. Replaces it with
        the value of 'self.slug_field' on the given object.
        """

        if not request_kwargs:
            request_kwargs = getattr(self, 'kwargs', {})

        kwargs = super(ModelCMSView, self).get_url_kwargs(request_kwargs,
                                                          **kwargs)
        obj = kwargs.pop('object', None)
        if obj:
            kwargs[self.slug_url_kwarg] = getattr(obj, self.slug_field, None)
        elif self.slug_url_kwarg in request_kwargs:
            kwargs[self.slug_url_kwarg] = request_kwargs[self.slug_url_kwarg]

        return kwargs

    def _model_name(self, plural=False):
        return helpers.model_name(self.model, self.custom_model_name,
                                  self.custom_model_name_plural,
                                  plural=plural)

    @property
    def model_name_plural(self):
        """
        Property for getting the plural verbose name of the given model.
        Returns custom_model_name if present, otherwise returns
        the verbose_name of the model.
        """
        return self._model_name(plural=True)

    @property
    def model_name(self):
        """
        Property for getting the verbose name of the given model.
        Returns custom_model_name if present, otherwise returns
        the verbose_name of the model.
        """
        return self._model_name(plural=False)

    def get_render_data(self, **kwargs):
        """
        Adds the model_name to the context, then calls super.
        """
        kwargs['model_name'] = self.model_name
        kwargs['model_name_plural'] = self.model_name_plural
        return super(ModelCMSView, self).get_render_data(**kwargs)
