# vim: expandtab
from django.conf import settings
from django.conf.urls import patterns, include, url
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

import views

admin.autodiscover()

urlpatterns = patterns('',
    url(r'^sitemap[.]xml$', 'django.contrib.sitemaps.views.sitemap'),
)

urlpatterns += i18n_patterns('',
    url(r'^$', views.index, name='index'),
    url(_(r'^about/'), views.about, name='about'),
    url(_(r'^obligees/'), include('chcemvediet.apps.obligees.urls', namespace='obligees')),
    url(_(r'^applications/'), include('chcemvediet.apps.applications.urls', namespace='applications')),
    url(r'^accounts/', include('allauth.urls')),
    url(r'^accounts/', include('chcemvediet.apps.accounts.urls', namespace='accounts')),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^i18n/', include('django.conf.urls.i18n')),
)

if settings.DEBUG:
    urlpatterns = patterns('',
        url(r'^media/(?P<path>.*)$', 'django.views.static.serve', {'document_root': settings.MEDIA_ROOT, 'show_indexes': True}),
        url(r'', include('django.contrib.staticfiles.urls')),
    ) + urlpatterns

