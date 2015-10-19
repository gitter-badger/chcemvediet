# vim: expandtab
# -*- coding: utf-8 -*-
import collections

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from poleno.utils.template import render_to_string
from poleno.utils.misc import cached_method

from .models import Attachment


class AttachmentsWidget(forms.TextInput):

    def __init__(self, *args, **kwargs):
        super(AttachmentsWidget, self).__init__(*args, **kwargs)
        self.upload_url_func = None
        self.download_url_func = None

    def render(self, name, value, attrs=None):
        textinput_value = u',%s,' % u','.join(u'%s' % a.pk for a in value or [])
        textinput_attrs = dict(attrs, type=u'hidden')
        textinput = super(AttachmentsWidget, self).render(name, textinput_value, textinput_attrs)
        return render_to_string(u'attachments/attachments_widget.html', {
                u'name': name,
                u'textinput': textinput,
                u'attachments': value or [],
                u'funcs': {
                    u'upload_url': self.upload_url_func,
                    u'download_url': self.download_url_func,
                    },
                })

class AttachmentsField(forms.Field):
    widget = AttachmentsWidget

    def __init__(self, *args, **kwargs):
        attached_to = kwargs.pop(u'attached_to', None)
        upload_url_func = kwargs.pop(u'upload_url_func', None)
        download_url_func = kwargs.pop(u'download_url_func', None)
        super(AttachmentsField, self).__init__(*args, **kwargs)

        self._upload_url_func = None
        self._download_url_func = None

        self.attached_to = attached_to
        self.upload_url_func = upload_url_func
        self.download_url_func = download_url_func

    @property
    def upload_url_func(self):
        return self._upload_url_func

    @upload_url_func.setter
    def upload_url_func(self, func):
        self.widget.upload_url_func = self._upload_url_func = func

    @property
    def download_url_func(self):
        return self._download_url_func

    @download_url_func.setter
    def download_url_func(self, func):
        self.widget.download_url_func = self._download_url_func = func

    def prepare_value(self, value):
        if isinstance(value, basestring):
            try:
                return self.to_python(value)
            except ValidationError:
                return None
        return value

    @cached_method(cached_exceptions=ValidationError)
    def to_python(self, value):
        u""" Returns list of Attachments """
        if value is None:
            return []
        keys = [k for k in value.split(u',') if k]
        if not keys:
            return []

        # Only attachments poiting to whitelisted objects may be used by the field.
        if isinstance(self.attached_to, collections.Iterable):
            query_set = Attachment.objects.attached_to(*self.attached_to)
        else:
            query_set = Attachment.objects.attached_to(self.attached_to)

        try:
            attachments = query_set.filter(pk__in=keys).order_by_pk()
        except ValueError:
            raise ValidationError(_(u'attachments:AttachmentsField:error:invalid'))
        if len(attachments) != len(keys):
            raise ValidationError(_(u'attachments:AttachmentsField:error:invalid'))
        return attachments
