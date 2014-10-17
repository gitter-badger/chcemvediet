# vim: expandtab
# -*- coding: utf-8 -*-
import os
import random
import json

from testfixtures import TempDirectory

from django.conf.urls import patterns, url
from django.http import HttpResponseNotModified, CompatibleStreamingHttpResponse
from django.utils.http import urlquote, urlencode, http_date
from django.test import TestCase

from poleno.utils.http import JsonResponse, send_file_response
from poleno.utils.misc import random_string

class JsonResponseTest(TestCase):
    u"""
    Tests ``JsonResponse`` class. Checks that the response has correctly content type and various
    value types are correctly encoded. Also checks that any additional keyword arguments are passed
    directly to ``HttpResponse``.
    """

    def json_view(request):
        return JsonResponse({u'data': [47, u'string', [], {}, True, False, None]})

    def json_view_with_status(request):
        return JsonResponse([1, 2, 3], status=201)

    def json_view_with_empty_dict(request):
        return JsonResponse({})

    def json_view_with_empty_list(request):
        return JsonResponse([])

    def json_view_with_string(request):
        return JsonResponse(u'Text')

    def json_view_with_number(request):
        return JsonResponse(47)

    def json_view_with_float(request):
        return JsonResponse(3.13)

    def json_view_with_true(request):
        return JsonResponse(True)

    urls = patterns(u'',
        url(r'^json_view/$', json_view),
        url(r'^json_view_with_status/$', json_view_with_status),
        url(r'^json_view_with_empty_dict/$', json_view_with_empty_dict),
        url(r'^json_view_with_empty_list/$', json_view_with_empty_list),
        url(r'^json_view_with_string/$', json_view_with_string),
        url(r'^json_view_with_number/$', json_view_with_number),
        url(r'^json_view_with_float/$', json_view_with_float),
        url(r'^json_view_with_true/$', json_view_with_true),
        )

    def _check_response(self, response, klass, status_code, content):
        self.assertIs(type(response), klass)
        self.assertEqual(response.status_code, status_code)
        self.assertEqual(response[u'Content-Type'], u'application/json')
        self.assertEqual(json.loads(response.content), content)

    def test_json_view(self):
        response = self.client.get(u'/json_view/')
        self._check_response(response, JsonResponse, 200, {u'data': [47, u'string', [], {}, True, False, None]})

    def test_json_view_with_status(self):
        response = self.client.get(u'/json_view_with_status/')
        self._check_response(response, JsonResponse, 201, [1, 2, 3])

    def test_json_view_with_empty_dict(self):
        response = self.client.get(u'/json_view_with_empty_dict/')
        self._check_response(response, JsonResponse, 200, {})

    def test_json_view_with_empty_list(self):
        response = self.client.get(u'/json_view_with_empty_list/')
        self._check_response(response, JsonResponse, 200, [])

    def test_json_view_with_string(self):
        response = self.client.get(u'/json_view_with_string/')
        self._check_response(response, JsonResponse, 200, u'Text')

    def test_json_view_with_number(self):
        response = self.client.get(u'/json_view_with_number/')
        self._check_response(response, JsonResponse, 200, 47)

    def test_json_view_with_float(self):
        response = self.client.get(u'/json_view_with_float/')
        self._check_response(response, JsonResponse, 200, 3.13)

    def test_json_view_with_true(self):
        response = self.client.get(u'/json_view_with_true/')
        self._check_response(response, JsonResponse, 200, True)

class SendFileResponseTest(TestCase):
    u"""
    Tests ``send_file_response()`` function. Checks that regular files are sent correctly, but
    sending non-regular or non-existent files raises an exception. Also checks that if the request
    has ``HTTP_IF_MODIFIED_SINCE`` header, the file is sent only if it was changes since then.
    Finally checks if ``Last-Modified``, ``Content-Disposition`` and ``Content-Length`` headers are
    set correctly.
    """

    def file_view(request):
        path = request.GET[u'path']
        name = request.GET[u'name']
        content_type = request.GET[u'content-type']
        return send_file_response(request, path, name, content_type)

    urls = patterns(u'',
        url(r'^file/$', file_view),
        )

    def setUp(self):
        self.tempdir = TempDirectory()

    def tearDown(self):
        self.tempdir.cleanup()

    def _create_file(self, filename=u'myfile.tmp', content=u'Some text.'):
        self.tempdir.write(filename, content)
        return self.tempdir.getpath(filename)

    def _request_file(self, path, name=u'filename.bin', content_type=u'text/plain', **kwargs):
        params = urlencode({u'path': path, u'name': name, u'content-type': content_type})
        return self.client.get(u'/file/?%s' % params, **kwargs)

    def _check_response(self, response, klass, status_code):
        self.assertIs(type(response), klass)
        self.assertEqual(response.status_code, status_code)

    def _check_content(self, response, path):
        with open(path, 'rb') as f:
            content = f.read()
        self.assertEqual(u''.join(response.streaming_content), content)


    def test_regular_file(self):
        path = self._create_file()
        response = self._request_file(path)
        self._check_response(response, CompatibleStreamingHttpResponse, 200)
        self._check_content(response, path)

    def test_directory_raises_exception(self):
        with self.assertRaisesMessage(OSError, u'Not a regular file: /'):
            response = self._request_file(u'/')

    def test_nonexistent_file_raises_exception(self):
        with self.assertRaisesMessage(OSError, u"[Errno 2] No such file or directory: '/nonexistent.txt'"):
            response = self._request_file(u'/nonexistent.txt')

    def test_random_file(self):
        content = random_string(random.randrange(1000, 2000))
        path = self._create_file(content=content)
        response = self._request_file(path)
        self._check_response(response, CompatibleStreamingHttpResponse, 200)
        self._check_content(response, path)

    def test_if_modified_since_with_modified_file(self):
        u"""
        Checks that if the request has ``HTTP_IF_MODIFIED_SINCE`` header and the file was indeed
        modified since then, the file is sent.
        """
        modified_timestamp = 1413500000
        if_modified_since_timestamp = modified_timestamp + 1000000

        path = self._create_file()
        os.utime(path, (modified_timestamp, modified_timestamp))
        response = self._request_file(path, HTTP_IF_MODIFIED_SINCE=http_date(if_modified_since_timestamp))
        self._check_response(response, HttpResponseNotModified, 304)

    def test_if_modified_since_with_unmodified_file(self):
        u"""
        Checks that if the request has ``HTTP_IF_MODIFIED_SINCE`` header and the file was NOT
        modified since then, the file is not sent.
        """
        modified_timestamp = 1413500000
        if_modified_since_timestamp = modified_timestamp - 1000000

        path = self._create_file()
        os.utime(path, (modified_timestamp, modified_timestamp))
        response = self._request_file(path, HTTP_IF_MODIFIED_SINCE=http_date(if_modified_since_timestamp))
        self._check_response(response, CompatibleStreamingHttpResponse, 200)
        self._check_content(response, path)

    def test_last_modified_response_header(self):
        modified_timestamp = 1413500000

        path = self._create_file()
        os.utime(path, (modified_timestamp, modified_timestamp))
        response = self._request_file(path)
        self.assertEqual(response[u'Last-Modified'], u'Thu, 16 Oct 2014 22:53:20 GMT')

    def test_content_length_header(self):
        path = self._create_file(content=u'1234567890')
        response = self._request_file(path)
        self.assertEqual(response[u'Content-Length'], u'10')

    def test_content_length_header_for_random_file(self):
        content = random_string(random.randrange(1000, 2000))
        path = self._create_file(content=content)
        response = self._request_file(path)
        self.assertEqual(response[u'Content-Length'], str(len(content)))

    def test_content_disposition_header(self):
        path = self._create_file()
        response = self._request_file(path, u'thefile.txt')
        self.assertEqual(response[u'Content-Disposition'], u"attachment; filename*=UTF-8''thefile.txt")

    def test_content_disposition_header_with_space(self):
        path = self._create_file()
        response = self._request_file(path, u'the file.txt')
        self.assertEqual(response[u'Content-Disposition'], u"attachment; filename*=UTF-8''the%20file.txt")

    def test_content_disposition_header_with_diacritic(self):
        path = self._create_file()
        response = self._request_file(path, u'ľťéŠÝÄÚ.txt')
        self.assertEqual(response[u'Content-Disposition'], u"attachment; filename*=UTF-8''%C4%BE%C5%A5%C3%A9%C5%A0%C3%9D%C3%84%C3%9A.txt")

    def test_content_disposition_header_with_random_unicode_junk(self):
        path = self._create_file()
        name = random_string(20, chars=u'BａｃòԉíρｓûϻᏧｏｌｒѕìｔãｍｅéӽѵ߀ɭｐèлｕｉｎ.Iüà,ɦëǥｈƅɢïêｇԁSùúâɑｆäｂƃｄｋϳɰյƙｙáFХ-åɋｗ')
        response = self._request_file(path, name)
        self.assertEqual(response[u'Content-Disposition'], u"attachment; filename*=UTF-8''%s" % urlquote(name))
