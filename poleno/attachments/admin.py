# vim: expandtab
# -*- coding: utf-8 -*-
from django import forms
from django.db import transaction
from django.conf.urls import patterns, url
from django.utils.html import format_html
from django.contrib import admin
from django.contrib.sessions.models import Session
from django.contrib.contenttypes import generic

from poleno.utils.urls import reverse
from poleno.utils.misc import filesize, decorate, try_except
from poleno.utils.admin import admin_obj_format, live_field, AdminLiveFieldsMixin

from . import views as attachments_views
from .models import Attachment

class AttachmentInline(generic.GenericTabularInline):
    model = Attachment
    ct_field = u'generic_type'
    ct_fk_field = u'generic_id'
    extra = 0
    template = u'admin/attachments/attachment/inline.html'

    fields = [
            u'attachment_field',
            u'file_field',
            u'name',
            u'content_type',
            u'created',
            u'size_field',
            ]
    readonly_fields = fields
    ordering = [u'pk']

    @decorate(short_description=u'Attachment')
    def attachment_field(self, attachment):
        return admin_obj_format(attachment)

    @decorate(short_description=u'File')
    def file_field(self, attachment):
        info = attachment._meta.app_label, attachment._meta.model_name
        url = reverse(u'admin:%s_%s_download' % info, args=[attachment.pk])
        res = format_html(u'<a href="{0}">{1}</a>', url, attachment.file.name)
        return res

    @decorate(short_description=u'Size')
    def size_field(self, attachment):
        return filesize(attachment.size) if attachment.size is not None else u'--'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

class AttachmentAdminAddForm(forms.ModelForm):

    def clean(self):
        cleaned_data = super(AttachmentAdminAddForm, self).clean()

        if u'generic_type' in self.cleaned_data and u'generic_id' in self.cleaned_data:
            generic_type = self.cleaned_data[u'generic_type']
            generic_id = self.cleaned_data[u'generic_id']
            try:
                generic_object = generic_type.get_object_for_this_type(pk=generic_id)
            except generic_type.model_class().DoesNotExist:
                self.add_error(u'generic_id', u'This object does not exist.')
            except ValueError:
                self.add_error(u'generic_id', u'Invalid generic id.')
            else:
                self.cleaned_data[u'generic_object'] = generic_object

        return cleaned_data

    def save(self, commit=True):
        assert self.is_valid()

        attachment = Attachment(
                generic_object=self.cleaned_data[u'generic_object'],
                file=self.cleaned_data[u'file'],
                name=self.cleaned_data[u'name'],
                content_type=self.cleaned_data[u'content_type'],
                created=self.cleaned_data[u'created'],
                )

        if commit:
            attachment.save()
        return attachment

    def save_m2m(self):
        pass

class AttachmentAdminChangeForm(forms.ModelForm):
    def clean(self):
        cleaned_data = super(AttachmentAdminChangeForm, self).clean()

        if u'generic_type' in self.cleaned_data and u'generic_id' in self.cleaned_data:
            generic_type = self.cleaned_data[u'generic_type']
            generic_id = self.cleaned_data[u'generic_id']
            try:
                generic_object = generic_type.get_object_for_this_type(pk=generic_id)
            except generic_type.model_class().DoesNotExist:
                self.add_error(u'generic_id', u'This object does not exist.')
            except ValueError:
                self.add_error(u'generic_id', u'Invalid generic id.')
            else:
                self.cleaned_data[u'generic_object'] = generic_object

        return cleaned_data

class AttachmentAdmin(AdminLiveFieldsMixin, admin.ModelAdmin):
    list_display = [
            u'attachment_column',
            u'generic_object_column',
            u'file_column',
            u'name',
            u'content_type',
            u'created',
            u'size_column',
            ]
    list_filter = [
            u'created',
            u'content_type',
            u'generic_type',
            ]
    search_fields = [
            u'=id',
            u'=generic_id',
            u'generic_type__name',
            u'file',
            u'name',
            u'content_type',
            ]
    ordering = [u'-pk']

    @decorate(short_description=u'Attachment')
    @decorate(admin_order_field=u'pk')
    def attachment_column(self, attachment):
        return admin_obj_format(attachment, link=False)

    @decorate(short_description=u'Generic Object')
    @decorate(admin_order_field=u'generic_type__name')
    def generic_object_column(self, attachment):
        generic = attachment.generic_object
        return admin_obj_format(generic)

    @decorate(short_description=u'File')
    @decorate(admin_order_field=u'file')
    def file_column(self, attachment):
        info = attachment._meta.app_label, attachment._meta.model_name
        url = reverse(u'admin:%s_%s_download' % info, args=[attachment.pk])
        res = format_html(u'<a href="{0}">{1}</a>', url, attachment.file.name)
        return res

    @decorate(short_description=u'Size')
    @decorate(admin_order_field=u'size')
    def size_column(self, attachment):
        return filesize(attachment.size)

    form_add = AttachmentAdminAddForm
    form_change = AttachmentAdminChangeForm
    fieldsets = (
            (None, {
                u'classes': [u'wide'],
                u'fields': [
                    u'generic_type',
                    u'generic_id',
                    u'generic_object_live',
                    u'file_column',
                    u'name',
                    u'content_type',
                    u'created',
                    u'size',
                    ],
                }),
            )
    fieldsets_add = (
            (None, {
                u'classes': [u'wide'],
                u'fields': [
                    u'generic_type',
                    u'generic_id',
                    u'generic_object_live',
                    u'file',
                    u'name',
                    u'content_type',
                    u'created',
                    ],
                }),
            )
    live_fields = [
            u'generic_object_live',
            ]
    readonly_fields = live_fields + [
            u'file_column',
            u'size',
            ]
    raw_id_fields = [
            ]

    @decorate(short_description=u'Generic Object')
    @live_field(u'generic_type', u'generic_id')
    def generic_object_live(self, generic_type, generic_id):
        generic = try_except(lambda: generic_type.get_object_for_this_type(pk=generic_id), None)
        return admin_obj_format(generic)

    @transaction.atomic
    def upload_view(self, request):
        session = Session.objects.get(session_key=request.session.session_key)
        info = self.model._meta.app_label, self.model._meta.model_name
        download_url_func = (lambda a: reverse(u'admin:%s_%s_download' % info, args=(a.pk,)))
        return attachments_views.upload(request, session, download_url_func)

    def download_view(self, request, attachment_pk):
        attachment = Attachment.objects.get_or_404(pk=attachment_pk)
        return attachments_views.download(request, attachment)

    def get_queryset(self, request):
        queryset = super(AttachmentAdmin, self).get_queryset(request)
        queryset = queryset.prefetch_related(u'generic_object')
        return queryset

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name
        urls = patterns('',
                url(r'^upload/$', self.admin_site.admin_view(self.upload_view), name=u'%s_%s_upload' % info),
                url(r'^(.+)/download/$', self.admin_site.admin_view(self.download_view), name=u'%s_%s_download' % info),
                )
        return urls + super(AttachmentAdmin, self).get_urls()

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.fieldsets_add
        return super(AttachmentAdmin, self).get_fieldsets(request, obj)

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            self.form = self.form_add
            form = super(AttachmentAdmin, self).get_form(request, obj, **kwargs)
        else:
            self.form = self.form_change
            form = super(AttachmentAdmin, self).get_form(request, obj, **kwargs)
        return form

    def get_formsets(self, request, obj=None):
        if obj is None:
            return []
        return super(AttachmentAdmin, self).get_formsets(request, obj)

admin.site.register(Attachment, AttachmentAdmin)
