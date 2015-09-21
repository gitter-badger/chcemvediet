# vim: expandtab
# -*- coding: utf-8 -*-
from django import forms
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse_lazy
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _

from poleno.utils.misc import cached_method

from .models import Obligee

class ObligeeWidget(forms.TextInput):
    u"""
    TextInput with extra information about the selected Obligee rendered below the inputbox.
    """
    def render(self, name, value, attrs=None):
        obligee = value if isinstance(value, Obligee) else None

        textinput_value = obligee.name if obligee else value
        textinput = super(ObligeeWidget, self).render(name, textinput_value, attrs)

        return render_to_string(u'obligees/widgets/obligee_widget.html', {
                u'name': name,
                u'textinput': textinput,
                u'obligee': obligee,
                })

class ObligeeField(forms.Field):
    u"""
    Form field for Obligee selection with autocomplete functionality. Works with classic
    ``TextInput`` widget and with ``ObligeeWidget`` widget as well. ``ObligeeWidget`` shows
    additional information about selected Obligee below the inputbox.

    Example;
        class MyForm(forms.Form):
            obligee = ObligeeField(
                    label=_(u'Obligee'),
                    )

        class AnotherForm(forms.Form):
            obligee = ObligeeField(
                    label=_(u'Obligee'),
                    widget=ObligeeWidget(),
                    )
    """
    def prepare_value(self, value):
        if isinstance(self.widget, ObligeeWidget):
            # ``ObligeeWidget`` needs ``Obligee`` as its value, but somehow sometimes the given
            # value is just a string containing an obligee name, not the Obligee itself. It's
            # probably taken directly from POST request and not converted by ``to_python`` method.
            if not isinstance(value, Obligee):
                try:
                    value = self.to_python(value)
                except ValidationError:
                    pass
        else:
            if isinstance(value, Obligee):
                value = value.name
        return value

    @cached_method(cached_exceptions=ValidationError)
    def to_python(self, value):
        u""" Returns an Obligee """
        if value in self.empty_values:
            return None
        # FIXME: Should be ``.get(name=value)``, but there are Obligees with duplicate names, yet.
        value = Obligee.objects.pending().filter(name=value).order_by_pk().first()
        if value is None:
            raise ValidationError(_(u'obligees:ObligeeField:invalid_obligee_name'))
        return value

    def widget_attrs(self, widget):
        attrs = super(ObligeeField, self).widget_attrs(widget)
        attrs[u'data-autocomplete-url'] = reverse_lazy(u'obligees:autocomplete')
        attrs[u'class'] = u'autocomplete %s' % widget.attrs[u'class'] if u'class' in widget.attrs else u'autocomplete'
        return attrs
