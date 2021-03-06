import logging
import zlib

from scrapy.utils.gz import gunzip
from scrapy.http import Response, TextResponse
from scrapy.responsetypes import responsetypes
from scrapy.exceptions import NotConfigured, IgnoreRequest

logger = logging.getLogger(__name__)

ACCEPTED_ENCODINGS = [b'gzip', b'deflate']

try:
    import brotli
    ACCEPTED_ENCODINGS.append(b'br')
except ImportError:
    pass


class HttpCompressionMiddleware(object):
    """This middleware allows compressed (gzip, deflate) traffic to be
    sent/received from web sites"""

    def __init__(self, settings):
        self._max_size = settings.get('MAX_UNCOMPRESSED_SIZE', 0)

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('COMPRESSION_ENABLED'):
            raise NotConfigured
        return cls(crawler.settings)

    def process_request(self, request, spider):
        request.headers.setdefault('Accept-Encoding',
                                   b",".join(ACCEPTED_ENCODINGS))

    def process_response(self, request, response, spider):

        if request.method == 'HEAD':
            return response
        if isinstance(response, Response):
            content_encoding = response.headers.getlist('Content-Encoding')
            if content_encoding:
                encoding = content_encoding.pop()
                decoded_body = self._decode(response.body, encoding.lower())
                if self._max_size and len(decoded_body) > self._max_size:
                    error_msg = ("Cancelling processing of %(url)s: "
                                 "Uncompressed response size %(size)s larger "
                                 "than max allowed size (%(maxsize)s).")
                    error_args = {'url': response.url,
                                  'size': len(decoded_body),
                                  'maxsize': self._max_size}
                    logger.error(error_msg, error_args)
                    raise IgnoreRequest(error_msg % error_args)

                respcls = responsetypes.from_args(headers=response.headers, \
                    url=response.url, body=decoded_body)
                kwargs = dict(cls=respcls, body=decoded_body)
                if issubclass(respcls, TextResponse):
                    # force recalculating the encoding until we make sure the
                    # responsetypes guessing is reliable
                    kwargs['encoding'] = None
                response = response.replace(**kwargs)
                if not content_encoding:
                    del response.headers['Content-Encoding']

        return response

    def _decode(self, body, encoding):
        if encoding == b'gzip' or encoding == b'x-gzip':
            body = gunzip(body)

        if encoding == b'deflate':
            try:
                body = zlib.decompress(body)
            except zlib.error:
                # ugly hack to work with raw deflate content that may
                # be sent by microsoft servers. For more information, see:
                # http://carsten.codimi.de/gzip.yaws/
                # http://www.port80software.com/200ok/archive/2005/10/31/868.aspx
                # http://www.gzip.org/zlib/zlib_faq.html#faq38
                body = zlib.decompress(body, -15)
        if encoding == b'br' and b'br' in ACCEPTED_ENCODINGS:
            body = brotli.decompress(body)

        return body
