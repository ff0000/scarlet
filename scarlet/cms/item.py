from django import http
from django.views.generic.edit import ModelFormMixin
from django.views.generic.detail import SingleObjectMixin
from django import forms
from django.forms import models as model_forms
from django.contrib.admin.utils import flatten_fieldsets
from django.db.models.fields import FieldDoesNotExist
from django.db import models
from django.core.exceptions import ValidationError

from . import helpers
from . import renders
from . import transaction
from .forms import LazyFormSetFactory
from .models import CMSLog
from .internal_tags import handler as tag_handler
from .base_views import ModelCMSMixin, ModelCMSView
from .actions import PublishView


class FormView(ModelCMSMixin, ModelFormMixin, ModelCMSView):
    """
    View for adding or editing an object.
    Inherits from ModelCMSMixin, ModelFormMixin, ModelCMSView.
    Adds a 'popup' value to self.renders that is an instance of
    PopupRender that uses the default_template.

    :param default_template: The default template. Defaults to \
    'cms/edit.html'.
    :param force_add: Treat this form as an add form. Defaults \
    to False.
    :param form_class: A ModelForm class to use instead of using \
    model_form_factory.
    :param fieldsets: The view's fieldsets. Use the same format as \
    django admin. Defaults to None.
    :param formsets: A dictionary where the keys are the formset \
    prefixes and the values are LazyFormSetFactory instances. \
    Defaults to an empty dictionary.
    :param redirect_to_view: The name of a view that we will redirect to \
    after a successful save.
    :param cancel_view: The name of a view the cancel links will point to.
    :param force_instance_values: A dictionary of keyword arguments that \
    will be set on every object before save. Defaults to empty dictionary.
    :param combined_formset_defs: A dictionary of keyward arguments for
    AdminFormset used to combine the display of formsets
    """

    default_template = 'cms/edit.html'
    force_add = False

    fieldsets = None
    formsets = {}
    redirect_to_view = "main"
    cancel_view = "main"
    readonly_fields = None
    prepopulated_fields = None
    force_instance_values = {}
    combined_formset_defs = None

    def __init__(self, *args, **kwargs):
        if args:
            super(FormView, self).__init__(*args, **kwargs)
        else:
            super(FormView, self).__init__(**kwargs)

        self.renders['popup'] = renders.PopupRender(
                        template=self.default_template
        )

        if self.formsets:
            for k, v in self.formsets.items():
                if not isinstance(v, LazyFormSetFactory):
                    raise TypeError(
                        '%s must be a LazyFormSetFactory instance' % k)


    def get_readonly_fields(self):
        """
        Hook for specifying custom readonly fields.
        """
        return self.readonly_fields

    def get_force_instance_values(self):
        """
        Returns values that must be set on
        any object before save.

        Defaults to returning `self.force_instance_values`.
        """
        return self.force_instance_values

    def get_object_url(self):
        """
        Returns the url where this object can be edited.
        """

        if self.kwargs.get(self.slug_url_kwarg, False) == \
                    unicode(getattr(self.object, self.slug_field, "")) \
                    and not self.force_add:
            url = self.request.build_absolute_uri()
        else:
            url = self.bundle.get_view_url('edit', self.request.user,
                                           {'object': self.object},
                                           self.kwargs)
        return url

    def get_cancel_url(self):
        """
        Returns the cancel url for this view.

        if `self.cancel_view` is None the current url will
        be used. Otherwise the get_view_url will be called with
        the current bundle using `self.cancel_view` as the
        view name.
        """
        if self.cancel_view:
            url = self.bundle.get_view_url(self.cancel_view,
                                            self.request.user, {},
                                            self.kwargs)
        else:
            url = self.request.build_absolute_uri()

        return self.customized_return_url(url)

    def get_success_url(self):
        """
        Returns the url to redirect to after a successful update.

        if `self.redirect_to_view` is None the current url will
        be used. Otherwise the get_view_url will be called
        on the current bundle using `self.redirect_to_view` as the
        view name. If the name is "main" or "main_list" no object
        will be passed. Otherwise `self.object` will be passed as
        a kwarg.
        """

        if self.redirect_to_view:
            kwargs = {}
            if self.redirect_to_view != 'main' and \
                        self.redirect_to_view != 'main_list':
                kwargs['object'] = self.object
            return self.bundle.get_view_url(self.redirect_to_view,
                                            self.request.user, kwargs,
                                            self.kwargs)
        else:
            return self.request.build_absolute_uri()

    def get_object(self):
        """
        Get the object we are working with. Makes sure
        get_queryset is called even when in add mode.
        """

        if not self.force_add and self.kwargs.get(self.slug_url_kwarg, None):
            return super(FormView, self).get_object()
        else:
            self.queryset = self.get_queryset()

        return None

    def get_fieldsets(self):
        """
        Hook for specifying fieldsets. If 'self.fieldsets' is
        empty this will default to include all the fields in
        the form with a title of None.
        """

        if self.fieldsets:
            return self.fieldsets
        form_class = self.get_form_class()
        form = self.get_form(form_class)
        fields = form.base_fields.keys()

        readonly_fields = self.get_readonly_fields()
        if readonly_fields:
            fields.extend(readonly_fields)

        return [(None, {'fields': fields})]

    def get_form_class(self):
        """
        Returns the form class to use in this view. Makes
        sure that the form_field_callback is set to use
        the `formfield_for_dbfield` method and that any
        custom form classes are prepared by the
        `customize_form_widgets` method.
        """
        if self.fieldsets:
            fields = flatten_fieldsets(self.get_fieldsets())
        else:
            if (self.form_class and
                    getattr(self.form_class, 'Meta', None) and
                    getattr(self.form_class.Meta, 'fields', None)):
                fields = self.form_class.Meta.fields
            else:
                fields = []

        exclude = None
        if self.parent_field:
            exclude = (self.parent_field,)

        readonly_fields = self.get_readonly_fields()
        if readonly_fields:
            if exclude:
                exclude = list(exclude)
            else:
                exclude = []

            for field in readonly_fields:
                try:
                    try:
                        f = self.model._meta.get_field(field)
                        if fields:
                            fields.remove(field)
                        else:
                            exclude.append(field)
                    except models.FieldDoesNotExist:
                        if fields:
                            fields.remove(field)
                except ValueError:
                    pass

        params = {'fields': fields or '__all__',
                  'exclude': exclude,
                  'formfield_callback': self.formfield_for_dbfield}

        if self.form_class:
            if issubclass(self.form_class, forms.ModelForm) and \
                    getattr(self.form_class._meta, 'model', None):
                model = self.form_class.Meta.model
            else:
                model = self.model
            fc = self.customize_form_widgets(self.form_class, fields=fields)
            params['form'] = fc
        else:
            if self.model is not None:
                # If a model has been explicitly provided, use it
                model = self.model
            elif hasattr(self, 'object') and self.object is not None:
                # If this view is operating on a single object, use
                # the class of that object
                model = self.object.__class__
            else:
                # Try to get a queryset and extract the model class
                # from that
                model = self.get_queryset().model

        return model_forms.modelform_factory(model, **params)

    def get_form_kwargs(self):
        """
        Returns the keyword arguments for instantiating the form.
        """
        kwargs = {'initial': self.get_initial(),
                  'instance': self.object}

        if self.request.method in ('POST', 'PUT') and self.can_submit:
            kwargs.update({
                'data': self.request.POST,
                'files': self.request.FILES
            })
        return kwargs

    def get_formsets_dict(self):
        return self.formsets

    def get_formset_parent_object(self, parent_form, saving=False):
        if parent_form.is_valid() and saving:
            obj = parent_form.save(commit=False)
        elif self.object:
            obj = self.object
        else:
            obj = parent_form._meta.model()
        return obj

    def get_formset_queryset(self, key, klass):
        """
        Hook for specifying a custom queryset for
        a particular formset. Returns None by default.

        :param key: The prefix for the formset. This \
        matches with the key of the formset in the \
        self.formsets dictionary.
        :param klass: The FormSet class.
        """
        return None

    def get_formsets(self, parent_form, saving=False):
        fdict = self.get_formsets_dict()
        if not fdict:
            return {}

        obj = self.get_formset_parent_object(parent_form,
                                             saving=saving)

        formsets = {}
        for k, v in fdict.items():
            formsets[k] = self._init_formset(k, v,
                                         obj, saving=saving)
        return formsets

    def get_combined_formset_defs(self):
        return self.combined_formset_defs

    def get_admin_formsets(self, formsets):
        """
        Hook for specifying custom admin formsets
        """
        if formsets:
            return helpers.AdminFormSets(formsets, self.get_combined_formset_defs())
        return None

    def get_admin_form(self, form):
        """
        Hook for specifying custom admin forms
        """
        return helpers.AdminForm(form, self.get_fieldsets())

    def _init_formset(self, key, lazy_klass, obj, saving=False):
        klass = lazy_klass(self.formfield_for_dbfield,
                           self.customize_form_widgets)
        prefix = klass.__name__.lower()
        queryset = self.get_formset_queryset(key, klass)

        if saving:
            ins = klass(self.request.POST, files=self.request.FILES,
                                instance=obj, prefix=prefix,
                                queryset=queryset)
        else:
            ins = klass(instance=obj, prefix=prefix, queryset=queryset)

        return ins

    def form_invalid(self, **context):
        """
        Response for invalid form. Calls the render method
        passing self.request and any passed in keyword arguments.
        """
        return self.render(self.request, **context)

    def save_form(self, form):
        """
        Save a valid form. If there is a parent attribute,
        this will make sure that the parent object is added
        to the saved object. Either as a relationship before
        saving or in the case of many to many relations after
        saving. Any forced instance values are set as well.

        Returns the saved object.
        """

        # Add any force_instance_values
        force = self.get_force_instance_values()
        if force:
            for k, v in force.items():
                setattr(form.instance, k, v)

        # Are we adding to an attr or manager
        should_add = False
        if self.parent_object:
            m2ms = [f.name for f in form.instance._meta.many_to_many]
            m2ms.extend(
                [f.field.rel.related_name for f in
                    [
                        f for f in form.instance._meta.get_fields(include_hidden=True)
                        if f.many_to_many and f.auto_created
                    ]
                ]
            )

            if self.parent_field in m2ms:
                should_add = True
            else:
                try:
                    form.instance._meta.get_field(self.parent_field)
                    setattr(form.instance, self.parent_field,
                            self.parent_object)
                except FieldDoesNotExist:
                    pass

        obj = form.save()
        # Do we need to add this to a m2m
        if should_add:
            getattr(obj, self.parent_field).add(self.parent_object)

        return obj

    def save_formsets(self, form, formsets, auto_tags=None):
        """
        Hook for saving formsets. Loops through
        all the given formsets and calls their
        save method.
        """
        for formset in formsets.values():
            tag_handler.set_auto_tags_for_formset(formset, auto_tags)
            formset.save()

    def form_valid(self, form, formsets):
        """
        Response for valid form. In one transaction this will
        save the current form and formsets, log the action
        and message the user.

        Returns the results of calling the `success_response` method.
        """
        # check if it's a new object before it save the form
        new_object = False
        if not self.object:
            new_object = True

        instance = getattr(form, 'instance', None)
        auto_tags, changed_tags, old_tags = tag_handler.get_tags_from_data(
            form.data, self.get_tags(instance))
        tag_handler.set_auto_tags_for_form(form, auto_tags)

        with transaction.commit_on_success():
            self.object = self.save_form(form)
            self.save_formsets(form, formsets, auto_tags=auto_tags)

            url = self.get_object_url()
            self.log_action(self.object, CMSLog.SAVE, url=url)
            msg = self.write_message()

        # get old and new tags
        if not new_object and changed_tags and old_tags:
            tag_handler.update_changed_tags(changed_tags, old_tags)

        return self.success_response(msg)

    def success_response(self, message=None):
        """
        Returns a 'render redirect' to the result of the
        `get_success_url` method.
        """

        return self.render(self.request,
                           redirect_url=self.get_success_url(),
                           obj=self.object,
                           message=message,
                           collect_render_data=False)

    def render(self, request, **kwargs):
        """
        Renders this view. Adds cancel_url to the context.
        If the request get parameters contains 'popup' then
        the `render_type` is set to 'popup'.
        """
        if request.GET.get('popup'):
            self.render_type = 'popup'
            kwargs['popup'] = 1

        kwargs['cancel_url'] = self.get_cancel_url()
        if not self.object:
            kwargs['single_title'] = True
        return super(FormView, self).render(request, **kwargs)

    def get(self, request, *args, **kwargs):
        """
        Method for handling GET requests.
        Calls the `render` method with the following
        items in context.

        * **adminForm** - The main form wrapped in an helper class \
        that helps with fieldset iteration and html attributes.
        * **obj** - The object being edited.
        * **formsets** - Any attached formsets.
        """

        self.object = self.get_object()
        form_class = self.get_form_class()
        form = self.get_form(form_class)
        formsets = self.get_formsets(form)

        adminForm = self.get_admin_form(form)
        adminFormSets = self.get_admin_formsets(formsets)
        context = {
            'adminForm': adminForm,
            'obj': self.object,
            'formsets': adminFormSets,
        }
        return self.render(request, **context)

    def is_valid(self, form, formsets):
        valid_formsets = True
        for formset in formsets.values():
            if not formset.is_valid():
                valid_formsets = False
                break

        if form.is_valid() and valid_formsets:
            # Add any force_instance_values
            force = self.get_force_instance_values()
            if force:
                for k, v in force.items():
                    setattr(form.instance, k, v)
                try:
                    form.instance.full_clean()
                except ValidationError, e:
                    form._update_errors(e)
                    return False
            return True

        return False

    def post(self, request, *args, **kwargs):
        """
        Method for handling POST requests.
        Validates submitted form and
        formsets. Saves if valid, re displays
        page with errors if invalid.
        """

        self.object = self.get_object()
        form_class = self.get_form_class()
        form = self.get_form(form_class)
        formsets = self.get_formsets(form, saving=True)

        valid_formsets = True
        for formset in formsets.values():
            if not formset.is_valid():
                valid_formsets = False
                break

        if self.is_valid(form, formsets):
            return self.form_valid(form, formsets)
        else:
            adminForm = self.get_admin_form(form)
            adminFormSets = self.get_admin_formsets(formsets)
            context = {
                'adminForm': adminForm,
                'formsets': adminFormSets,
                'obj': self.object,
            }
            return self.form_invalid(form=form, **context)

class PreviewWrapper(ModelCMSMixin, SingleObjectMixin, ModelCMSView):
    """
    Wrapper View for providing a preview that is based on another view.
    Inherits from ModelCMSMixin, SingleObjectMixin and ModelCMSView.

    :param preview_view: A view class with a as_string method that can be \
    called to return a string for previewing an object.
    :param pass_through_kwarg: The name of keyword argument that the \
    `preview_view` callable expects to identify to object being requested. \
    Defaults to 'slug'.
    :param pass_through_attr: The name of the attribute on the object \
    being previewed that should be the value passed to the `preview_view` \
    to identify the object. Defaults to 'slug'.
    :param default_template: The default template to render. Defaults \
    to 'cms/preview.html'.
    """

    pass_through_kwarg = 'slug'
    pass_through_attr = 'slug'
    preview_view = None

    slug_field = 'pk'
    slug_url_kwarg = 'pk'

    default_template = 'cms/preview.html'

    def get_context_data(self, **kwargs):
        """
        Hook for adding arguments to the context.
        """
        return kwargs

    def get_object(self):
        """
        Get the object for previewing.
        Raises a http404 error if the object is not found.
        """
        obj = super(PreviewWrapper, self).get_object()

        if not obj:
            raise http.Http404

        return obj

    def get_preview_kwargs(self, **kwargs):
        """
        Gets the url keyword arguments to pass to the
        `preview_view` callable. If the `pass_through_kwarg`
        attribute is set the value of `pass_through_attr` will
        be looked up on the object.

        So if you are previewing an item Obj<id=2> and

            ::

                self.pass_through_kwarg = 'object_id'
                self.pass_through_attr = 'pk'

        This will return

            ::

                { 'object_id' : 2 }

        """
        if not self.pass_through_kwarg:
            return {}

        obj = self.get_object()
        return {
            self.pass_through_kwarg: getattr(obj, self.pass_through_attr)
        }

    def get(self, request, *args, **kwargs):
        """
        Method for handling GET requests.
        Sets the renderer to be a RenderResponse instance
        that uses `default_template` as the template.

        The `preview_view` callable is called and passed to `render`
        method as the data keyword argument.
        """

        self.renders = {
            'response': renders.RenderResponse(template=self.default_template),
        }
        kwargs = self.get_preview_kwargs(**kwargs)
        view = self.preview_view.as_string()
        return self.render(request, data=view(request, **kwargs))

class VersionsList(PublishView):
    """
    View for deleting and reverting to previous versions.
    Inherits from PublishView.

    :param default_template: 'cms/versions.html'.
    :param redirect_to_view: 'edit'.
    """

    default_template = 'cms/versions.html'
    redirect_to_view = "edit"

    def _get_versions(self):
        self.object = self.get_object()
        klass = self.object.get_version_class()
        return klass.normal.filter(object_id=self.object.pk).exclude(
                                state=klass.DRAFT).order_by('-date_published')

    def get(self, request, *args, **kwargs):
        """
        Method for handling GET requests. Passes the
        following arguments to the context:

        * **versions** - The versions available for this object.\
        These will be instances of the inner version class, and \
        will not have access to the fields on the base model.
        * **done_url** - The result of the `get_done_url` method.
        """
        versions = self._get_versions()
        return self.render(request, obj=self.object, versions=versions,
                           done_url=self.get_done_url())

    def revert(self, version, url):
        """
        Set the given version to be the active draft.
        This is done by calling the object's `make_draft` method.
        Logs the revert as a 'save' and messages the user.
        """
        message = "Draft replaced with %s version. This revert has not been published." % version.date_published
        version.make_draft()

        # Log action as a save
        self.log_action(self.object, CMSLog.SAVE, url=url)
        return self.write_message(message=message)

    def delete(self, version):
        """
        Deletes the given version, not the object itself.
        No log entry is generated but the user is notified
        with a message.
        """
        # Shouldn't be able to delete live or draft version
        if version.state != version.DRAFT and \
                      version.state != version.PUBLISHED:
            version.delete()
            message = "%s version deleted." % version.date_published
            return self.write_message(message=message)

    def post(self, request, *args, **kwargs):
        """
        Method for handling POST requests.
        Expects the 'vid' of the version to act on
        to be passed as in the POST variable 'version'.

        If a POST variable 'revert' is present this will
        call the revert method and then return a 'render
        redirect' to the result of the `get_done_url` method.

        If a POST variable 'delete' is present this will
        call the delete method and return a 'render redirect'
        to the result of the `get_done_url` method.

        If this method receives unexpected input, it will
        silently redirect to the result of the `get_done_url`
        method.
        """

        versions = self._get_versions()
        url = self.get_done_url()
        msg = None

        try:
            vid = int(request.POST.get('version', ''))
            version = versions.get(vid=vid)
            if request.POST.get('revert'):
                object_url = self.get_object_url()
                msg = self.revert(version, object_url)
            elif request.POST.get('delete'):
                msg = self.delete(version)
                # Delete should redirect back to itself
                url = self.request.build_absolute_uri()

        # If the give version isn't valid we'll just silently redirect
        except (ValueError, versions.model.DoesNotExist):
            pass

        return self.render(request, redirect_url=url,
                   message=msg,
                   obj=self.object,
                   collect_render_data=False)
