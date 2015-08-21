# vim: expandtab
# -*- coding: utf-8 -*-
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse as django_reverse
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.contrib.sites.models import Site
from django.utils.decorators import available_attrs

def reverse(viewname, urlconf=None, args=None, kwargs=None, prefix=None, current_app=None):
    u"""
    Django resolver may populate some arguments with None when parsing certain urls, but Django
    ``reverse`` fails to reconstuct them if given the same arguments. It breaks on None values.
    None usually means the argument is optional and missing in the url. So we filter out any
    arguments equal to None before calling ``reverse``.
    """
    if args is not None:
        while args and args[-1] is None:
            args = args[:-1]
    if kwargs is not None:
        kwargs = dict((k, v) for k, v in kwargs.iteritems() if v is not None)
    return django_reverse(viewname, urlconf, args, kwargs, prefix, current_app)

def complete_url(path, secure=False):
    u"""
    Returns complete url using given path and current site instance.
    """
    protocol = u'https' if secure else u'http'
    domain = Site.objects.get_current().domain
    return u'{0}://{1}{2}'.format(protocol, domain, path)

def complete_reverse(viewname, *args, **kwargs):
    u"""
    Returns complete url using django ``reverse`` function and current site instance.
    """
    secure = kwargs.pop(u'secure', False)
    anchor = kwargs.pop(u'anchor', u'')
    path = reverse(viewname, *args, **kwargs) + anchor
    return complete_url(path, secure)

def require_ajax(view):
    u"""
    Decorator to make a view only accept AJAX requests

    Example:
        @require_ajax
        def view(request, ...):
            # We can assume now that only AJAX request gets here
    """
    @wraps(view, assigned=available_attrs(view))
    def wrapped_view(request, *args, **kwargs):
        if not request.is_ajax():
            return HttpResponseBadRequest()
        return view(request, *args, **kwargs)
    return wrapped_view

def login_required(view=None, **kwargs):
    u"""
    Decorator for views that checks that the user is logged in, redirecting to the log-in page if
    necessary. If ``raise_exception`` is True, ``PermissionDenied`` is rased instead of
    redirecting.

    Based on: django.contrib.auth.decorators.login_required

    Example:
        @login_required
        def view(request, ...):
            # We can assume now that the user is logged in. If he was not, he was redirected.

        @login_required(raise_exception=True)
        def view(request, ...):
            # We can assume now that the user is logged in. If he was not, he has got PermissionDenied.
    """
    raise_exception = kwargs.pop(u'raise_exception', False)
    def check(user):
        if user.is_authenticated():
            return True
        if raise_exception:
            raise PermissionDenied
        return False
    actual_decorator = user_passes_test(check, **kwargs)
    if view:
        return actual_decorator(view)
    return actual_decorator

def secure_required(view=None, raise_exception=False):
    u"""
    Decorator for views that checks that the request is over HTTPS, redirecting if necessary. If
    ``raise_exception`` is True, ``PermissionDenied`` is rased instead of redirection. Note that
    the HTTPS check is disabled if DEBUG is true.

    Example:
        @secure_required
        def view(request, ...):
            # We can assume now the request is over HTTPS. If it was not, it was redirected.

        @secure_required(raise_exception=True)
        def view(request, ...):
            # We can assume now the request is over HTTPS. If it was not, PermissionDenied was
            # raised.
    """
    def actual_decorator(view):
        @wraps(view, assigned=available_attrs(view))
        def wrapped_view(request, *args, **kwargs):
            if settings.DEBUG or request.is_secure():
                return view(request, *args, **kwargs)
            if raise_exception:
                raise PermissionDenied
            request_url = request.build_absolute_uri(request.get_full_path())
            secure_url = request_url.replace(u'http://', u'https://', 1)
            return HttpResponseRedirect(secure_url)
        return wrapped_view
    if view:
        return actual_decorator(view)
    return actual_decorator
