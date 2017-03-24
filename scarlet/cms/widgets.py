import datetime
import urllib

from django.forms import widgets
from django.forms.utils import flatatt
from django import forms
from django.utils.encoding import force_unicode, python_2_unicode_compatible, force_text
from django.utils.safestring import mark_safe
from django.utils.html import conditional_escape, html_safe, format_html
from django.core.urlresolvers import reverse
from django.utils.dateparse import parse_time
from django.template.loader import render_to_string
from django.utils import timezone, formats, translation
from django.contrib.admin.widgets import url_params_from_lookup_dict

from . import settings

# NOT EVERYTHING IS SUPPORTED, I DON'T CARE.
TRANSLATION_DICT = {
    # Day
    'd' : 'dd',
    'l' : 'DD',
    'j' : 'oo',
    # Month
    'B' : 'MM',
    'm' : 'mm',
    'b' : 'M',
    # Year
    'Y' : 'yy',
    'y' : 'y',
    # Time
    'p' : 'TT',
    'I' : 'hh',
    'H' : 'HH',
    'M' : 'mm',
    'S' : 'ss',
}


@html_safe
@python_2_unicode_compatible
class SubWidget(object):
    """
    Some widgets are made of multiple HTML elements -- namely, RadioSelect.
    This is a class that represents the "inner" HTML element of a widget.
    """
    def __init__(self, parent_widget, name, value, attrs, choices):
        self.parent_widget = parent_widget
        self.name, self.value = name, value
        self.attrs, self.choices = attrs, choices

    def __str__(self):
        args = [self.name, self.value, self.attrs]
        if self.choices:
            args.append(self.choices)
        return self.parent_widget.render(*args)


@html_safe
@python_2_unicode_compatible
class ChoiceInput(SubWidget):
    """
    An object used by ChoiceFieldRenderer that represents a single
    <input type='$input_type'>.
    """
    input_type = None  # Subclasses must define this

    def __init__(self, name, value, attrs, choice, index):
        self.name = name
        self.value = value
        self.attrs = attrs
        self.choice_value = force_text(choice[0])
        self.choice_label = force_text(choice[1])
        self.index = index
        if 'id' in self.attrs:
            self.attrs['id'] += "_%d" % self.index

    def __str__(self):
        return self.render()

    def render(self, name=None, value=None, attrs=None):
        if self.id_for_label:
            label_for = format_html(' for="{}"', self.id_for_label)
        else:
            label_for = ''
        attrs = dict(self.attrs, **attrs) if attrs else self.attrs
        return format_html(
            '<label{}>{} {}</label>', label_for, self.tag(attrs), self.choice_label
        )

    def is_checked(self):
        return self.value == self.choice_value

    def tag(self, attrs=None):
        attrs = attrs or self.attrs
        final_attrs = dict(attrs, type=self.input_type, name=self.name, value=self.choice_value)
        if self.is_checked():
            final_attrs['checked'] = 'checked'
        return format_html('<input{} />', flatatt(final_attrs))

    @property
    def id_for_label(self):
        return self.attrs.get('id', '')


class RadioChoiceInput(ChoiceInput):
    input_type = 'radio'

    def __init__(self, *args, **kwargs):
        super(RadioChoiceInput, self).__init__(*args, **kwargs)
        self.value = force_text(self.value)


@html_safe
@python_2_unicode_compatible
class ChoiceFieldRenderer(object):
    """
    An object used by RadioSelect to enable customization of radio widgets.
    """

    choice_input_class = None
    outer_html = '<ul{id_attr}>{content}</ul>'
    inner_html = '<li>{choice_value}{sub_widgets}</li>'

    def __init__(self, name, value, attrs, choices):
        self.name = name
        self.value = value
        self.attrs = attrs
        self.choices = choices

    def __getitem__(self, idx):
        return list(self)[idx]

    def __iter__(self):
        for idx, choice in enumerate(self.choices):
            yield self.choice_input_class(self.name, self.value, self.attrs.copy(), choice, idx)

    def __str__(self):
        return self.render()

    def render(self):
        """
        Outputs a <ul> for this set of choice fields.
        If an id was given to the field, it is applied to the <ul> (each
        item in the list will get an id of `$id_$i`).
        """
        id_ = self.attrs.get('id')
        output = []
        for i, choice in enumerate(self.choices):
            choice_value, choice_label = choice
            if isinstance(choice_label, (tuple, list)):
                attrs_plus = self.attrs.copy()
                if id_:
                    attrs_plus['id'] += '_{}'.format(i)
                sub_ul_renderer = self.__class__(
                    name=self.name,
                    value=self.value,
                    attrs=attrs_plus,
                    choices=choice_label,
                )
                sub_ul_renderer.choice_input_class = self.choice_input_class
                output.append(format_html(
                    self.inner_html, choice_value=choice_value,
                    sub_widgets=sub_ul_renderer.render(),
                ))
            else:
                w = self.choice_input_class(self.name, self.value, self.attrs.copy(), choice, i)
                output.append(format_html(self.inner_html, choice_value=force_text(w), sub_widgets=''))
        return format_html(
            self.outer_html,
            id_attr=format_html(' id="{}"', id_) if id_ else '',
            content=mark_safe('\n'.join(output)),
        )


class RadioFieldRenderer(ChoiceFieldRenderer):
    choice_input_class = RadioChoiceInput


def translate_format(format_string):
    for k, v in TRANSLATION_DICT.items():
        format_string = format_string.replace('%{0}'.format(k), v)
    return format_string


class DateWidget(widgets.DateInput):
    bc = 'date'
    format_key = 'DATE_INPUT_FORMATS'

    def __init__(self, *args, **kwargs):
        super(DateWidget, self).__init__(*args, **kwargs)
        self.attrs['class'] = self.bc
        if not 'format' in kwargs:
            self.format = None

    def get_format(self):
        if self.format:
            return self.format

        if settings.USE_SCARLET_DATE_FORMATS and hasattr(settings, self.format_key):
            return getattr(settings, self.format_key)

        return formats.get_format(self.format_key)[0]

    def _format_value(self, value):
        return formats.localize_input(value, self.get_format())

    def build_attrs(self, *args, **kwargs):
        args = super(DateWidget, self).build_attrs(*args, **kwargs)
        args['data-date-format'] = translate_format(self.get_format())
        args['data-timezone'] = timezone.get_current_timezone_name()
        args['data-locale'] = translation.get_language()
        return args

    def value_from_datadict(self, data, files, name):
        value = super(DateWidget, self).value_from_datadict(data, files, name)
        df = self.get_format()
        if isinstance(value, basestring):
            try:
                return datetime.datetime.strptime(value, df)
            except ValueError:
                pass
        return value


class DateTimeWidget(DateWidget):
    bc = 'datetime'
    format_key = 'DATETIME_INPUT_FORMATS'


class TimeChoiceWidget(widgets.Select):
    """
    Widget for time fields. A select widget that will have a 'now'
    option plus an option for each block of time you want to
    display. By default this will be one item in the drop down for
    every 15 min block of a day.

    :param attrs: HTML attributes for the widget; same as django's.
    :param min_interval: Interval for minutes in your dropdown, \
    should be a number between 1 and 60. Default is 15.
    :param sec_interval: Interval for seconds in your dropdown, \
    should be a number between 1 and 60. Default is 60.
    :param twenty_four_hour: Display time in a 24hr format? \
    Default is False.
    """

    NOW = 'now'

    def __init__(self, attrs=None, min_interval=15, sec_interval=60,
                 twenty_four_hour=False):
        super(TimeChoiceWidget, self).__init__(attrs)
        assert 60 >= min_interval > 0
        assert 60 >= sec_interval > 0

        self.twenty_four_hour = twenty_four_hour
        self.choices = [(self.NOW, 'Now')]
        self.choice_values = set()

        self.repr_format = "%I:%M:%S %p"
        if twenty_four_hour:
            self.repr_format = "%H:%M:%S"

        for hour in range(24):
            for min_v in range(60 / min_interval):
                min_v = min_v * min_interval
                for sec in range(60 / sec_interval):
                    sec = sec * sec_interval
                    t = datetime.time(hour, min_v, sec)
                    self.choices.append((t.strftime("%H:%M:%S"),
                                         t.strftime(self.repr_format)))
                    self.choice_values.add(t.strftime("%H:%M:%S"))

    def value_from_datadict(self, *args):
        data = super(TimeChoiceWidget, self).value_from_datadict(*args)
        if data == self.NOW:
            # Time should be naive, conversion happens later
            data = datetime.datetime.now().strftime("%H:%M:%S")
        return data

    def render(self, name, value, attrs=None, choices=()):
        if value:
            if type(value) == type("") or type(value) == type(u""):
                try:
                    value = parse_time(value)
                except ValueError:
                    value = None

            if value and isinstance(value, datetime.time):
                value_str = value.strftime("%H:%M:%S")
                if not value_str in self.choice_values:
                    choices = list(choices)
                    choices.append((value_str, value.strftime(self.repr_format)))
        return super(TimeChoiceWidget, self).render(name, value, attrs=attrs,
                                                    choices=choices)


class SplitDateTime(widgets.SplitDateTimeWidget):
    """
    Widget for datetime fields. Uses DateWidget, TimeChoiceWidget.
    """

    def __init__(self, widgets=(DateWidget, TimeChoiceWidget),attrs=None):
        forms.MultiWidget.__init__(self, widgets, attrs)

    def format_output(self, rendered_widgets):
        return mark_safe(u'%s %s' % (rendered_widgets[0], rendered_widgets[1]))

    def value_from_datadict(self, data, files, name):
        d = super(SplitDateTime, self).value_from_datadict(data, files, name)
        if not self.is_required and len(d) and not d[0]:
            return ['', '']
        return d


class DateRadioInput(RadioChoiceInput):
    label_text = "At a specific date and time"

    def render(self, name=None, value=None, attrs=None, choices=()):
        attrs = attrs or self.attrs
        if 'id' in self.attrs:
            label_for = ' for="%s_%s"' % (self.attrs['id'], self.index)
        else:
            label_for = ''
        date_widget = attrs['date_widget']
        return mark_safe(u'<label%s>%s %s: %s</label>' % (
            label_for, self.tag(), self.label_text, date_widget))

    def tag(self):
        final_attrs = {
            'type': 'radio',
            'name': self.name,
            'value': self.choice_value,
        }

        if self.is_checked():
            final_attrs['checked'] = 'checked'
        return mark_safe(u'<input%s />' % flatatt(final_attrs))


class DateRenderer(RadioFieldRenderer):
    def __init__(self, *args, **kwargs):
        self.date_widget = kwargs.pop('date_widget')
        super(DateRenderer, self).__init__(*args, **kwargs)

    def return_choice(self, choice, idx):
        cls = RadioChoiceInput
        attrs = self.attrs.copy()
        if choice[0] == RadioDateTimeWidget.DATE:
            cls = DateRadioInput
            attrs['date_widget'] = self.date_widget

        return cls(self.name, self.value, attrs, choice, idx)

    def __iter__(self):
        for i, choice in enumerate(self.choices):
            yield self.return_choice(choice, i)

    def __getitem__(self, idx):
        choice = self.choices[idx]
        return self.return_choice(choice, idx)


    def render(self):
        return mark_safe(u'<fieldset class="datetime">\n%s\n</fieldset>' % u'\n'.join([u'%s'
                % force_unicode(w) for w in self]))

class RadioDateTimeWidget(widgets.RadioSelect):
    NOW = 'now'
    DATE = 'date'

    def __init__(self, *args, **kwargs):
        self.date_class = kwargs.pop('date_class', DateTimeWidget)
        self.choices = [(self.NOW, 'Now'), (self.DATE, 'Date',)]
        kwargs['choices'] = self.choices
        super(RadioDateTimeWidget, self).__init__(*args, **kwargs)

    def get_radio_key(self, name):
        return "{0}_rdi".format(name)

    def get_renderer(self, date_widget, name, value, attrs=None):
        return DateRenderer(name, value, attrs, self.choices,
                            date_widget=date_widget)

    def render(self, name, value, attrs=None):
        widget = self.date_class()
        date_widget = widget.render(name, value, attrs=attrs)
        return self.get_renderer(date_widget, self.get_radio_key(name),
                                 self.DATE, {}).render()

    def value_from_datadict(self, data, files, name):
        radio_value = data.get(self.get_radio_key(name))
        if radio_value == self.NOW:
            return timezone.now()
        else:
            widget = self.date_class()
            return widget.value_from_datadict(data, files, name)

class APIChoiceWidget(widgets.Input):
    """
    Widget for selecting a related object. This is used
    as the default widget for ForeignKey fields. Outputs
    text input field that is wrapped in a <div> that contains
    3 data attributes.

    * data-api: The url that can be queried to get the options \
    for this field in json format.
    * data-add: The url that should be called in a popup to add \
    a new item. If not present adding is not supported.
    * data-title: The title of the field.

    In order for this widget to work it needs to know where those urls are and
    if the rendering user has the needed permissions. This is
    accomplished by having the code that prepares the form
    call the `update_links` method. See the method documentation for
    what parameters are needed.

    :param rel: The rel attribute of the foreign key field that \
    this widget is for.
    :param attrs: HTML attributes for this field, same as django's.
    :param using: The database to use. Defaults to None.
    :param view: The string name of the view that will be used for \
    getting the api url. Defaults to 'main'.
    :param api_url: The api url. This is only used if the automatic url \
    discovery fails.
    :param add_view: The string name of the view that will be used for \
    getting the add url. Defaults to 'add'.
    :param add_url: The url for adding a new item. This is only used \
    if the automatic url discovery fails.
    :param extra_query_kwargs: Keyword arguments that you would like \
    passed as part of the query string.
    """

    input_type = 'hidden'
    template = u'<div class="api-select" data-title="%(value)s" data-api="%(link)s" data-add="%(add_link)s">%(input)s</div>'

    def __init__(self, rel, attrs=None, using=None,
                        view="main", api_url='',
                        add_view="add", add_url='',
                        extra_query_kwargs=None):
        super(APIChoiceWidget, self).__init__(attrs=attrs)
        self.rel = rel
        self.model = self.rel.to
        self.db = using

        self.extra_query_kwargs = extra_query_kwargs

        self.view = view
        self.add_view = add_view

        self._api_link = api_url
        self._add_link = add_url


    def render(self, name, value, attrs=None, choices=()):
        data = {
            'input': super(APIChoiceWidget, self).render(name, value,
                                                          attrs=attrs),
            'value': conditional_escape(self.label_for_value(value)),
            'link': self.get_api_link(),
            'add_link' : self.get_add_link()
        }
        return mark_safe(self.template % data)

    def get_qs(self):
        """
        Returns a mapping that will be used to generate
        the query string for the api url. Any values
        in the the `limit_choices_to` specified on the
        foreign key field and any arguments specified on
        self.extra_query_kwargs are converted to a format
        that can be used in a query string and returned as
        a dictionary.
        """

        qs = url_params_from_lookup_dict(self.rel.limit_choices_to)
        if not qs:
            qs = {}

        if self.extra_query_kwargs:
            qs.update(self.extra_query_kwargs)
        return qs

    def _get_bundle_link(self, bundle, view_name, user):
        url = bundle.get_view_url(view_name, user)
        if url:
            return url
        return ''

    def _get_reverse(self, name, url_kwargs):
        return reverse(name, kwargs=url_kwargs)

    def update_links(self, request, admin_site=None):
        """
        Called to update the widget's urls. Tries to find the
        bundle for the model that this foreign key points to and then
        asks it for the urls for adding and listing and sets them on
        this widget instance. The urls are only set if request.user
        has permissions on that url.

        :param request: The request for which this widget is being rendered.
        :param admin_site: If provided, the `admin_site` is used to lookup \
        the bundle that is registered as the primary url for the model \
        that this foreign key points to.
        """

        if admin_site:
            bundle = admin_site.get_bundle_for_model(self.model)

            if bundle:
                self._api_link = self._get_bundle_link(bundle, self.view,
                                                       request.user)
                self._add_link = self._get_bundle_link(bundle, self.add_view,
                                                       request.user)

    def get_api_link(self):
        """
        Adds a query string to the api url. At minimum adds the type=choices
        argument so that the return format is json. Any other filtering
        arguments calculated by the `get_qs` method are then added to the
        url. It is up to the destination url to respect them as filters.
        """

        url = self._api_link
        if url:
            qs = self.get_qs()
            url = "%s?type=choices" % url
            if qs:
                url = "%s&amp;%s" % (url, u'&amp;'.join([u'%s=%s' % (k, urllib.quote(unicode(v).encode('utf8'))) \
                                                        for k, v in qs.items()]))
                url = "%s&amp;%s" % (url, u'&amp;'.join([u'exclude=%s' % x \
                                                        for x in qs.keys()]))
        return url

    def get_add_link(self):
        """
        Appends the popup=1 query string to the url so the
        destination url treats it as a popup.
        """

        url = self._add_link
        if url:
            return "%s?popup=1" % url
        return url

    def label_for_value(self, value, key=None):
        """
        Looks up the current value of the field and returns
        a unicode representation. Default implementation does a lookup
        on the target model and if a match is found calls force_unicode
        on that object. Otherwise a blank string is returned.
        """
        if not key:
            key = self.rel.get_related_field().name

        if value is not None:
            try:
                obj = self.model._default_manager.using(self.db
                                                         ).get(**{key: value})
                return force_unicode(obj)
            except (ValueError, self.model.DoesNotExist):
                return ''
        return ''


class APIModelChoiceWidget(APIChoiceWidget):
    """
    Widget for selecting a related object. This is meant to
    be used in forms that specify their own related fields.
    Inherits from APIChoiceWidget but is based on a model
    instead of a foreign key relation.

    :param model: The model that this widget is for.
    :param attrs: HTML attributes for this field, same as django's.
    :param using: The database to use. Defaults to None.
    :param limit_choices_to: Keyword arguments that you would like \
    passed as part of the query string.
    :param view: The string name of the view that will be used for \
    getting the api url. Defaults to 'main'.
    :param api_url: The api url. This is only used if the automatic url \
    discovery fails.
    :param add_view: The string name of the view that will be used for \
    getting the add url. Defaults to 'add'.
    :param add_url: The url for adding a new item. This is only used \
    if the automatic url discovery fails.
    """

    template = u'<div class="api-select" data-title="%(value)s" data-api="%(link)s" data-add="%(add_link)s">%(input)s</div>'

    def __init__(self, model, attrs=None, using=None,
                    limit_choices_to=None,
                    view="main", api_url='',
                    add_view="add", add_url=''):
        super(APIChoiceWidget, self).__init__(attrs=attrs)
        self.limit_choices_to = limit_choices_to
        self.model = model
        self.db = using

        self.view = view
        self.add_view = add_view

        self._api_link = api_url
        self._add_link = add_url


    def get_qs(self):
        return url_params_from_lookup_dict(self.limit_choices_to)

    def label_for_value(self, value):
        return super(APIModelChoiceWidget,
                        self).label_for_value(value, key='pk')



class APIManyChoiceWidget(APIChoiceWidget, widgets.SelectMultiple):
    """
    Widget for selecting a many related objects. This is meant to
    be used in forms that specify their own related fields.
    Inherits from APIChoiceWidget but is based on a model
    instead of a foreign key relation.

    :param model: The model that this widget is for.
    :param attrs: HTML attributes for this field, same as django's.
    :param using: The database to use. Defaults to None.
    :param limit_choices_to: Keyword arguments that you would like \
    passed as part of the query string.
    :param view: The string name of the view that will be used for \
    getting the api url. Defaults to 'main'.
    :param api_url: The api url. This is only used if the automatic url \
    discovery fails.
    :param add_view: The string name of the view that will be used for \
    getting the add url. Defaults to 'add'.
    :param add_url: The url for adding a new item. This is only used \
    if the automatic url discovery fails.
    """

    template = u'<div class="api-select" data-api="%(api_link)s" data-add="%(add_link)s">%(options)s</div>'
    allow_multiple_selected = True

    def __init__(self, model, attrs=None, using=None,
                    limit_choices_to=None,
                    view="main", api_url='',
                    add_view="add", add_url=''):
        super(APIChoiceWidget, self).__init__(attrs=attrs)
        self.limit_choices_to = limit_choices_to
        self.model = model
        self.db = using

        self.view = view
        self.add_view = add_view

        self._api_link = api_url
        self._add_link = add_url

    def get_qs(self):
        return url_params_from_lookup_dict(self.limit_choices_to)


    def update_links(self, request, admin_site=None):
        """
        Called to update the widget's urls. Tries to find the
        bundle for the model that this foreign key points to and then
        asks it for the urls for adding and listing and sets them on
        this widget instance. The urls are only set if request.user
        has permissions on that url.

        :param request: The request for which this widget is being rendered.
        :param admin_site: If provided, the `admin_site` is used to lookup \
        the bundle that is registered as the primary url for the model \
        that this foreign key points to.
        """

        if admin_site:
            bundle = admin_site.get_bundle_for_model(self.model.to)

            if bundle:
                self._api_link = self._get_bundle_link(bundle, self.view,
                                                       request.user)
                self._add_link = self._get_bundle_link(bundle, self.add_view,
                                                       request.user)


    def render(self, name, value, attrs=None, choices=()):
        final_attrs = self.build_attrs(attrs, name=name)
        data = {
            'api_link': self.get_api_link(),
            'add_link' : self.get_add_link(),
            'options' : self.get_options(value, name)
        }
        data.update(final_attrs)
        return mark_safe(self.template % data)

    def get_options(self, value, name, key=None):
        if not key:
            key = self.model.get_related_field().name

        values = []
        if value is not None:
            try:
                kwargs = {'{0}__in'.format(key): value}
                if self.limit_choices_to:
                    kwargs.update(self.limit_choices_to)
                objs = self.model.to._default_manager.using(self.db
                                 ).filter(**kwargs)
                for obj in objs:
                    d = { 'text' : force_unicode(obj),
                          'value' : getattr(obj, key),
                          'name' : name }
                    line = '<input type="hidden" data-multiple data-title="%(text)s" name="%(name)s" value="%(value)s" />' % d
                    values.append(line)
            except ValueError:
                pass

        if not values:
            values = ['<input type="hidden" data-multiple data-title="" name="{0}" value="" />'.format(name)]
        return ''.join(values)


class HiddenTextInput(widgets.HiddenInput):
    """
    Widget for order fields in lists. Inherits from HiddenInput
    so it is marked as hidden in the form, but uses a 'text' input
    type with a class attribute in the rendered html of
    *orderfield*.
    """

    input_type = 'text'

    def __init__(self, *args, **kwargs):
        super(HiddenTextInput, self).__init__(*args, **kwargs)
        self.attrs['class'] = 'orderfield'

    def is_hidden(self):
        return True


class HTMLWidget(widgets.Textarea):
    """
    WYSIWYG Widget. Adds *widget-wysiwyg* to the class attribute
    in the rendered html.
    """
    template = "cms/toolbar.html"

    def __init__(self, *args, **kwargs):
        super(HTMLWidget, self).__init__(*args, **kwargs)
        classes = ["wysiwyg-textarea"]
        if self.attrs.get('class'):
            classes.append(self.attrs.get('class'))
        self.attrs['class'] = " ".join(classes)

    def render(self, *args, **kwargs):
        text = super(HTMLWidget, self).render(*args, **kwargs)
        return mark_safe(u"<div class=\"widget-wysiwyg\">{1} {0}</div>".format(text, render_to_string(self.template)))


class AnnotatedHTMLWidget(widgets.MultiWidget):
    """
    Combines WYSIWYG with a hidden widget for seperating
    annotation data from annotated text.
    """
    template = "cms/toolbar_annotation.html"

    START_HTML = '<div class="wysiwyg-annotation-data">'
    END_HTML = '</div>'

    def __init__(self, attrs=None):
        _widgets = (
            widgets.Textarea(attrs={'class': "wysiwyg-textarea"}),
            widgets.Textarea(attrs={'class': "wysiwyg-annotations"}),
        )
        super(AnnotatedHTMLWidget, self).__init__(_widgets, attrs=attrs)

    def decompress(self, value):
        if value:
            parts = value.rpartition(self.START_HTML)
            if parts[1]:
                annotation = parts[2]
                if annotation.endswith(self.END_HTML):
                    annotation = annotation[:-len(self.END_HTML)]
                return parts[0], annotation
            return [value, ""]
        return ["", ""]

    def format_output(self, rendered_widgets):
        return mark_safe(u"<div class=\"widget-wysiwyg annotation\">{0} {1} {2}</div>".format(
                    render_to_string(self.template),
                    *rendered_widgets))

    def value_from_datadict(self, data, files, name):
        data = [
            widget.value_from_datadict(data, files, name + '_%s' % i)
            for i, widget in enumerate(self.widgets)]
        if data and data[1]:
            data[1] = self.START_HTML + data[1] + self.END_HTML
        return data[0] + data[1]
