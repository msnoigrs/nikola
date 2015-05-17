# -*- coding: utf-8 -*-

# Copyright © 2015 IGARASHI Masanao

# Permission is hereby granted, free of charge, to any
# person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the
# Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the
# Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice
# shall be included in all copies or substantial portions of
# the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
# PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
# OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os
try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin  # NOQA
import io
import uuid
from datetime import datetime
import dateutil.tz
import lxml.html
from lxml.html import fragment_fromstring
import lxml.etree
import html5lib
from feedgen.feed import FeedGenerator

from nikola import utils
from nikola.nikola import _enclosure

xml_dec_line = '<?xml version="1.0" encoding="utf-8"?>\n'
xsl_line = '<?xml-stylesheet type="text/xsl" href="{0}" media="all"?>\n'

class FeedUtil(object):

    def __init__(self, site):
        self.site = site

    def atom_renderer(self, fg, output_path, atom_path, xsl_stylesheet_href,
                      pretty=True):
        dst_dir = os.path.dirname(output_path)
        utils.makedirs(dst_dir)
        with io.open(output_path, 'w+', encoding='utf-8') as atom_file:
            atom_file.write(xml_dec_line)
            atom_file.write(xsl_line.format(xsl_stylesheet_href))
            atom_file.write(fg.atom_str(pretty=pretty))

    def rss_renderer(self, fg, output_path, rss_path, xsl_stylesheet_href,
                     pretty=True):
        dst_dir = os.path.dirname(output_path)
        utils.makedirs(dst_dir)
        with io.open(output_path, 'w+', encoding='utf-8') as rss_file:
            rss_file.write(xml_dec_line)
            rss_file.write(xsl_line.format(xsl_stylesheet_href))
            rss_file.write(fg.rss_str(pretty=pretty))

    def get_feed_content(self, data, lang, post, enclosure_details,
                         default_image=None):
        try:
            doc = html5lib.html5parser.parse(data, treebuilder='lxml',
                                             namespaceHTMLElements=False)
            doc = fragment_fromstring(lxml.html.tostring(doc), create_parent=True)
            doc.rewrite_links(
                lambda dst: self.site.url_replacer(post.permalink(), dst, lang,
                                                   'absolute'))
            try:
                src = None
                if (enclosure_details and
                    enclosure_details[2].split('/')[0] == 'image'):
                    src = enclosure_details[0]
                else:
                    postdoc = html5lib.html5parser.parse(post.text(lang),
                                                         treebuilder='lxml',
                                                         namespaceHTMLElements=False)
                    #postdoc = html5parser.document_fromstring(
                    #    post.text(lang))
                    #found = postdoc.xpath(
                    #    '//html:img',
                    #    namespaces={'html': 'http://www.w3.org/1999/xhtml'})
                    found = postdoc.xpath('//img')
                    for img in found:
                        src = img.attrib.get('src')
                        if src:
                            break
                    if src is None and default_image:
                        src = default_image
                if src is not None:
                    a = lxml.etree.Element('a')
                    a.attrib['href'] = post.permalink(lang, absolute=True)
                    img = lxml.etree.SubElement(a, 'img')
                    img.attrib['src'] = src
                    img.attrib['alt'] = 'thumbnail'
                    doc.insert(0, a)

                data = (doc.text or '') + ''.join(
                    [lxml.html.tostring(child, encoding='unicode')
                     for child in doc.iterchildren()])
            # No body there, it happens sometimes
            except IndexError:
                data = ''
        except lxml.etree.ParserError as e:
            if str(e) == "Document is empty":
                data = ""
            else:  # let other errors raise
                raise(e)
        return data

    def gen_feed_generator(self, lang, timeline, altlink, title, subtitle,
                           atom_output_name, atom_path, rss_output_name,
                           rss_path):
        config = self.site.config
        base_url = config["BASE_URL"]
        feed_links_append_query = config["FEED_LINKS_APPEND_QUERY"]
        blog_author = config["BLOG_AUTHOR"](lang)
        feed_plain = config["FEED_PLAIN"]
        feed_teasers = config["FEED_TEASERS"]
        feed_push = config["FEED_PUSH"]

        atom_feed_url = urljoin(base_url, atom_path.lstrip('/'))
        if atom_output_name:
            atom_append_query = None
            if feed_links_append_query:
                atom_append_query = feed_links_append_query.format(
                    feedRelUri=atom_path, feedFormat='atom')

        if rss_output_name:
            rss_feed_url = urljoin(base_url, rss_path.lstrip('/'))
            rss_append_query = None
            if feed_links_append_query:
                rss_append_query = feed_links_append_query.format(
                    feedRelUri=rss_path, feedFormat='rss')

        feed_id = 'urn:uuid:{0}'.format(
            uuid.uuid5(uuid.NAMESPACE_URL, atom_feed_url))

        fg = FeedGenerator()
        fg.load_extension('dc', atom=False,rss=True)
        fg.id(feed_id)
        fg.updated(datetime.now(dateutil.tz.tzutc()))
        fg.title(title=title, type=None, cdata=False)
        fg.subtitle(subtitle=subtitle, type=None, cdata=False)
        fg.author({'name': blog_author})
        fg.link([{'href': altlink, 'rel': 'alternate'},
                 {'href': atom_feed_url, 'rel': 'self'}])
        if feed_push:
            fg.link({'href': feed_push, 'rel': 'hub'})
        if rss_output_name:
            fg.rss_atom_link_self(rss_feed_url)

        def tzdatetime(dt):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=self.site.tzinfo)
            return dt.astimezone(dateutil.tz.tzutc())

        for post in timeline:
            entry_date = tzdatetime(post.date)
            entry_updated = tzdatetime(post.updated)

            entry_id = 'urn:uuid:{0}'.format(
                uuid.uuid5(uuid.NAMESPACE_URL,
                           post.permalink(lang, absolute=True)))
            fe = fg.add_entry()
            fe.id(entry_id)
            fe.title(title=post.title(lang), type='text', cdata=False)
            fe.updated(entry_updated)
            fe.published(entry_date)
            if post.author(lang):
                fe.author({'name': post.author(lang)})
            if post.description(lang):
                fe.summary(summary=post.description(lang), type=None,
                           cdata=False)
            categories = set([])
            if post.meta('category'):
                categories.add(post.meta('category'))
            tags = set(post._tags.get(lang, []))
            categories.update(tags)
            if len(categories):
                fe.category([{'term': x} for x in categories])

            #<link href="http://xxxx" rel="related" hreflang="ja"/>

            # enclosure callback returns None if post has no enclosure, or a
            # 3-tuple of (url, length (0 is valid), mimetype)
            enclosure_details = _enclosure(post=post, lang=lang)
            if enclosure_details is not None:
                feed_enclosure = config["FEED_ENCLOSURE"]
                if feed_enclosure == 'link':
                    fe.link([{
                        'href': enclosure_details[0],
                        'length': enclosure_details[1],
                        'type': enclosure_details[2],
                        'rel': 'enclosure'
                    }])
                elif feed_enclosure == 'media':
                    fg.load_extension('media', atom=True, rss=True)
                    fe.media.thumbnail([{
                        'url': enclosure_details[0],
                        #'height': None,
                        #'width': None
                    }])

            if atom_output_name:
                fe.link([{'href': post.permalink(
                    lang, absolute=True, query=atom_append_query),
                          'rel': 'alternate'}])

                data = post.text(
                    lang, teaser_only=feed_teasers,
                    strip_html=feed_plain,
                    feed_read_more_link=True,
                    feed_links_append_query=atom_append_query)
                if data:
                    # Massage the post's HTML (unless plain)
                    if feed_plain:
                        fe.content(content=data, src=None, type='text',
                                   cdata=False)
                    else:
                        data = self.get_feed_content(data, lang, post,
                                                     enclosure_details)
                        fe.content(content=data, src=None, type='html',
                                   cdata=True)

            if rss_output_name:
                fe.rss_link(post.permalink(
                    lang, absolute=True, query=rss_append_query))

                data = post.text(
                    lang, teaser_only=feed_teasers,
                    strip_html=feed_plain,
                    feed_read_more_link=True,
                    feed_links_append_query=rss_append_query)
                if data:
                    # Massage the post's HTML (unless plain)
                    if feed_plain:
                        fe.rss_content(content=data, cdata=False)
                    else:
                        data = self.get_feed_content(data, lang, post,
                                                     enclosure_details)
                        fe.rss_content(content=data, cdata=True)

        if atom_output_name:
            self.atom_renderer(fg, atom_output_name, atom_path,
                               self.site.url_replacer(atom_path,
                                                      "/assets/xml/atom.xsl"))
        if rss_output_name:
            self.rss_renderer(fg, rss_output_name, rss_path,
                              self.site.url_replacer(rss_path,
                                                     "/assets/xml/rss.xsl"))
